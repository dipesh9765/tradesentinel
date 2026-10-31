"""
Market Data Management & Ingestion Layer - TradeSentinel

This module implements the market data ingestion layer adhering to SOLID principles
and the BaseMarketDataProvider interface. It connects to Zerodha KiteConnect's market quotes
and historical data APIs, caches real-time top-of-book quotes, enriches OHLCV bars with
technical indicators, and enforces zero-dummy data integrity.
"""

import datetime
import logging
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_instrument_lot_sizes, get_kite_instrument_map, get_watchlist_symbols, settings
from app.core.interfaces import BaseMarketDataProvider
from app.core.server_logger import log_outgoing_error, log_outgoing_request, log_outgoing_response
from app.strategy.technical_indicators import enrich_candle_indicators
from app.trading.engine import trading_engine

logger = logging.getLogger(__name__)


# Dynamically loaded from backend/instruments.json for seamless maintainability
KITE_INSTRUMENT_MAP: dict[str, str] = get_kite_instrument_map()
INSTRUMENT_LOT_SIZES: dict[str, int] = get_instrument_lot_sizes()


class MarketDataManager(BaseMarketDataProvider):
    """
    Market Data Provider implementing the BaseMarketDataProvider interface.

    Responsibilities:
        - Ingests authentic top-of-book market quotes from Zerodha Kite Connect API.
        - Caches live prices and derivative ATM option strikes in memory.
        - Retrieves historical 5-minute candlestick bars for technical analysis.
        - Vector-enriches candlestick data with indicators (EMA, RSI, VWAP, ATR).
        - Guarantees zero synthetic or dummy data fabrication when unconfigured.

    Extends:
        core.interfaces.BaseMarketDataProvider

    Uses:
        - trading_engine.UnifiedTradingEngine: Broker authentication and outbound request guards.
        - technical_indicators.enrich_candle_indicators: Quantitative feature engineering.
        - server_logger: Low-overhead outgoing call auditing.
    """

    def __init__(self):
        self.live_prices: dict[str, float] = {}
        self.cached_quotes: dict[str, dict[str, Any]] = {}
        self.candles_data: dict[str, pd.DataFrame] = {}
        self.last_quote_time: datetime.datetime | None = None
        self.is_live: bool = False
        self.status_message: str = "Awaiting Zerodha Kite Connect configuration and authentication."

    def reload_instruments(self) -> None:
        """Reloads instrument mapping, lot sizes, and watchlist from instruments.json."""
        global KITE_INSTRUMENT_MAP, INSTRUMENT_LOT_SIZES
        KITE_INSTRUMENT_MAP = get_kite_instrument_map()
        INSTRUMENT_LOT_SIZES = get_instrument_lot_sizes()
        settings.WATCHLIST_SYMBOLS = get_watchlist_symbols()
        logger.info(f"Reloaded {len(KITE_INSTRUMENT_MAP)} trading instruments from instruments.json.")

    def is_configured(self) -> bool:
        """
        Returns True if Kite is authenticated and ready to fetch authentic market data.

        Returns:
            bool: True if valid Kite session exists, False otherwise.
        """
        return trading_engine.is_authenticated()

    # -------------------------------------------------------------------------
    # Live Quote Refresh Pipeline (SRP decomposed)
    # -------------------------------------------------------------------------

    def _parse_single_quote(
        self, symbol: str, kite_key: str, raw_quotes: dict[str, Any], now_str: str
    ) -> None:
        """Parses and caches an individual instrument quote from Kite payload."""
        if kite_key not in raw_quotes:
            return

        q = raw_quotes[kite_key]
        ltp = float(q.get("last_price", 0.0))
        net_change = float(q.get("net_change", 0.0))
        ohlc = q.get("ohlc", {})
        prev_close = float(ohlc.get("close", ltp))
        change_pct = round(((ltp - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

        self.live_prices[symbol] = ltp
        self.cached_quotes[symbol] = {
            "symbol": symbol,
            "ltp": ltp,
            "change": round(net_change, 2),
            "change_pct": change_pct,
            "lot_size": INSTRUMENT_LOT_SIZES.get(symbol, 1),
            "instrument_token": q.get("instrument_token"),
            "volume": q.get("volume", 0),
            "high": ohlc.get("high", ltp),
            "low": ohlc.get("low", ltp),
            "open": ohlc.get("open", ltp),
            "configured": True,
            "timestamp": now_str,
        }

    def refresh_live_quotes(self) -> bool:
        """
        Fetches authentic live market quotes from Zerodha Kite Connect API.

        Strict data integrity: No synthetic or dummy data is ever fabricated.

        Returns:
            bool: True if quotes were successfully fetched and cached, False otherwise.
        """
        if not self.is_configured():
            self.is_live = False
            self.status_message = "Zerodha Kite Connect credentials or daily OAuth session required."
            return False

        try:
            trading_engine.verify_outgoing_kite_request()
        except PermissionError as pe:
            self.is_live = False
            self.status_message = str(pe)
            logger.warning(f"Kite quote call blocked by authentication check: {pe}")
            return False

        try:
            kite = trading_engine.kite_client
            instruments = list(KITE_INSTRUMENT_MAP.values())

            # Dynamically include active position instruments for real-time derivative tick pricing
            for pos in trading_engine.positions.values():
                inst = pos.get("instrument", "").replace(" MIS", "").replace(" CNC", "").strip()
                if inst:
                    clean_tag = inst.replace(" ", "")
                    if "CE" in clean_tag or "PE" in clean_tag:
                        nfo_key = f"NFO:{clean_tag}"
                        if nfo_key not in instruments:
                            instruments.append(nfo_key)

            call_start = datetime.datetime.now()
            log_outgoing_request("Zerodha Kite", "quote", {"instruments_count": len(instruments)})
            raw_quotes = kite.quote(instruments)
            dur = round((datetime.datetime.now() - call_start).total_seconds() * 1000, 2)
            log_outgoing_response("Zerodha Kite", "quote", {"received_symbols": list(raw_quotes.keys())}, dur)

            now_str = datetime.datetime.now().strftime("%H:%M:%S")

            for symbol, kite_key in KITE_INSTRUMENT_MAP.items():
                self._parse_single_quote(symbol, kite_key, raw_quotes, now_str)

            # Store raw quote prices for direct instrument lookup
            for k, q in raw_quotes.items():
                ltp = float(q.get("last_price", 0.0))
                if ltp > 0:
                    self.live_prices[k] = ltp
                    short_k = k.split(":")[-1] if ":" in k else k
                    self.live_prices[short_k] = ltp

            self.is_live = True
            self.status_message = "Live data connected from Zerodha Kite."
            self.last_quote_time = datetime.datetime.now()
            return True
        except Exception as e:
            logger.error(f"Failed to fetch live quotes from Kite: {e}")
            log_outgoing_error("Zerodha Kite", "quote", e, 0.0)
            self.is_live = False
            self.status_message = f"Kite error: {e!s}"
            return False

    def get_quote(self, symbol: str) -> dict[str, Any]:
        """
        Returns cached market quote for an underlying symbol, or awaiting-configuration status.

        Args:
            symbol: Underlying instrument ticker (e.g. 'NIFTY 50').

        Returns:
            Dictionary containing LTP, net change, lot size, and provider state.
        """
        if symbol in self.cached_quotes:
            return self.cached_quotes[symbol]

        return {
            "symbol": symbol,
            "ltp": 0.0,
            "change": 0.0,
            "change_pct": 0.0,
            "lot_size": INSTRUMENT_LOT_SIZES.get(symbol, 1),
            "configured": self.is_configured(),
            "status": "CONFIG_REQUIRED" if not self.is_configured() else "FETCHING",
            "message": self.status_message,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        }

    def get_all_quotes(self) -> list[dict[str, Any]]:
        """
        Returns latest quotes for all watched instruments.

        Returns:
            List of quote dictionaries.
        """
        return [self.get_quote(s) for s in KITE_INSTRUMENT_MAP]

    def get_candles(self, symbol: str, interval: str = "5minute", limit: int = 60) -> list[dict[str, Any]]:
        """
        Convenience method returning candlestick bar records.

        Args:
            symbol: Underlying instrument ticker.
            limit: Maximum count of recent bars to return.

        Returns:
            List of candle dictionaries enriched with technical indicators.
        """
        meta = self.get_candles_meta(symbol, limit)
        return meta["candles"]

    # -------------------------------------------------------------------------
    # Candlestick Retrieval & Enrichment (SRP decomposed)
    # -------------------------------------------------------------------------

    def _check_kite_session_prerequisites(self) -> dict[str, Any] | None:
        """Checks whether Kite credentials, token, and session are properly configured."""
        if not trading_engine.api_key:
            return {
                "candles": [],
                "status": "KITE_SESSION_NOT_INITIALIZED",
                "message": "Zerodha Kite API credentials not configured.",
                "error_detail": "Please add your Kite API Key and Secret in Settings.",
            }

        if not trading_engine.access_token:
            return {
                "candles": [],
                "status": "KITE_SESSION_NOT_INITIALIZED",
                "message": "Zerodha Kite daily session is not initialized.",
                "error_detail": "Please click 'Authenticate Kite Session' in Settings to log in.",
            }

        if not self.is_configured():
            return {
                "candles": [],
                "status": "KITE_SESSION_NOT_INITIALIZED",
                "message": "Zerodha Kite session is inactive or security vault is locked.",
                "error_detail": "Please log in with master password and ensure Kite daily session is active.",
            }

        return None

    def _resolve_instrument_token(self, symbol: str) -> int | None:
        """Resolves Kite instrument token from cached quotes, refreshing if necessary."""
        quote = self.cached_quotes.get(symbol)
        instrument_token = quote.get("instrument_token") if quote else None

        if not instrument_token:
            self.refresh_live_quotes()
            quote = self.cached_quotes.get(symbol)
            instrument_token = quote.get("instrument_token") if quote else None

        return instrument_token

    def _fetch_raw_kite_candles(
        self, symbol: str, instrument_token: int
    ) -> tuple[pd.DataFrame | None, str | None]:
        """Fetches 5-minute historical candle bars from Zerodha Kite Connect."""
        try:
            trading_engine.verify_outgoing_kite_request()
            now = datetime.datetime.now()
            from_date = now - datetime.timedelta(days=5)
            candles_raw = trading_engine.kite_client.historical_data(
                instrument_token=instrument_token, from_date=from_date, to_date=now, interval="5minute"
            )

            if candles_raw:
                df = pd.DataFrame(candles_raw)
                if "date" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
                enriched_df = enrich_candle_indicators(df)
                self.candles_data[symbol] = enriched_df
                return enriched_df, None
            else:
                self.candles_data[symbol] = pd.DataFrame()
                return pd.DataFrame(), None
        except Exception as e:
            err_str = str(e)
            logger.error(f"Zerodha Kite historical data error for {symbol}: {err_str}")
            log_outgoing_error("Zerodha Kite", "historical_data", e, 0.0)
            return None, err_str

    def _format_candle_records(self, df: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
        """Extracts tail slice from DataFrame and formats into JSON-serializable records."""

        def _safe_float(val: Any, fallback: float = 0.0) -> float:
            if val is None or pd.isna(val) or np.isnan(val) or np.isinf(val):
                return fallback
            return float(val)

        tail = df.tail(limit).copy()
        records = []
        for _, row in tail.iterrows():
            close_price = _safe_float(row.get("close"), 0.0)
            records.append(
                {
                    "time": row.get("timestamp", str(row.get("date", ""))),
                    "open": _safe_float(row.get("open"), close_price),
                    "high": _safe_float(row.get("high"), close_price),
                    "low": _safe_float(row.get("low"), close_price),
                    "close": close_price,
                    "volume": int(row.get("volume", 0) if not pd.isna(row.get("volume", 0)) else 0),
                    "ema_9": _safe_float(row.get("ema_9"), close_price),
                    "ema_21": _safe_float(row.get("ema_21"), close_price),
                    "vwap": _safe_float(row.get("vwap"), close_price),
                    "rsi": _safe_float(row.get("rsi_14"), 50.0),
                }
            )
        return records

    def fetch_history_df(self, symbol: str, days: int) -> pd.DataFrame:
        """Raw 5-minute OHLCV history for backtesting. Raises ValueError with a user-facing reason."""
        prereq = self._check_kite_session_prerequisites()
        if prereq:
            raise ValueError(prereq["message"])
        token = self._resolve_instrument_token(symbol)
        if not token:
            raise ValueError(f"Unknown instrument '{symbol}' or no live quote to resolve its token.")
        trading_engine.verify_outgoing_kite_request()
        now = datetime.datetime.now()
        raw = trading_engine.kite_client.historical_data(
            instrument_token=token,
            from_date=now - datetime.timedelta(days=days),
            to_date=now,
            interval="5minute",
        )
        if not raw:
            raise ValueError(f"Kite returned no candles for {symbol}.")
        df = pd.DataFrame(raw)
        df["timestamp"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        return df

    def get_candles_meta(self, symbol: str, limit: int = 60) -> dict[str, Any]:
        """
        Fetches authentic historical candlestick data from Zerodha Kite with detailed status metadata.

        Decomposed Steps:
            1. Validate Kite prerequisites.
            2. Resolve instrument token.
            3. Fetch raw bars and enrich with indicators.
            4. Format records.

        Args:
            symbol: Target symbol.
            limit: Number of bars.

        Returns:
            Dictionary with 'candles' list, 'status', 'message', and 'error_detail'.
        """
        # 1. Prerequisite verification
        prereq_err = self._check_kite_session_prerequisites()
        if prereq_err:
            return prereq_err

        # 2. Token resolution
        instrument_token = self._resolve_instrument_token(symbol)

        # 3. Remote data retrieval
        kite_broker_error = None
        if instrument_token and trading_engine.kite_client:
            _, kite_broker_error = self._fetch_raw_kite_candles(symbol, instrument_token)

        df = self.candles_data.get(symbol, pd.DataFrame())
        if df.empty:
            if kite_broker_error:
                return {
                    "candles": [],
                    "status": "KITE_BROKER_ERROR",
                    "message": f"Zerodha Kite returned an error while fetching {symbol} candles.",
                    "error_detail": kite_broker_error,
                }
            return {
                "candles": [],
                "status": "NO_DATA",
                "message": f"No candlestick records available from Zerodha Kite for {symbol}.",
                "error_detail": "Market might be closed or trading is halted for this instrument.",
            }

        # 4. Record formatting
        records = self._format_candle_records(df, limit)

        return {
            "candles": records,
            "status": "OK",
            "message": f"Successfully loaded {len(records)} candles from Zerodha Kite.",
            "error_detail": None,
        }


# Singleton instance
market_data_manager = MarketDataManager()
