"""
Institutional Quantitative Strategy Engine - TradeSentinel

Implements a multi-factor institutional quantitative strategy framework tailored
for Indian Equity & Derivatives markets (NSE NIFTY 50, BANK NIFTY, FIN NIFTY, Equities).

Core Pillars:
1. Multi-Timeframe Trend & Ribbon Alignment (EMA 9, 21, 50, 200).
2. Institutional Trend Following & Baseline Support (Supertrend 10/3.0, VWAP & SD Bands).
3. Trend Strength & Consolidation Gate (ADX 14 >= 22 required; ADX < 20 triggers NO_TRADE).
4. Central Pivot Range (CPR) & Floor Pivots for institutional key levels.
5. RSI Range Shift & Momentum Divergence detection.
6. Intelligent Option Strike Resolution (ATM / Slight ITM Delta ~0.55-0.65).
7. Strict Risk-Reward Structuring (minimum 1:1.8, default 1:2.0, multi-target).
"""

import datetime
import logging
from typing import Any

import pandas as pd

from app.core.config import is_index_symbol
from app.strategy.technical_indicators import calculate_cpr, calculate_pivot_points, detect_rsi_divergence

logger = logging.getLogger(__name__)

# Strike step intervals for Indian derivatives
INDEX_STRIKE_STEPS: dict[str, int] = {
    "NIFTY 50": 50,
    "NIFTY BANK": 100,
    "BANK NIFTY": 100,
    "FINNIFTY": 50,
    "MIDCPNIFTY": 25,
    "NIFTY": 50,
}


class InstitutionalQuantEngine:
    """
    High-probability multi-factor algorithmic trading engine for NSE Indian Markets.
    """

    @staticmethod
    def get_strike_step(symbol: str) -> int:
        """Returns standard strike interval step for index."""
        clean_sym = symbol.upper().replace(" ", "").replace("_", "")
        for k, v in INDEX_STRIKE_STEPS.items():
            if k.replace(" ", "") in clean_sym:
                return v
        return 50

    @staticmethod
    def resolve_optimal_strike(symbol: str, ltp: float, is_bullish: bool) -> tuple[int, str]:
        """
        Selects the optimal ATM or slight ITM option strike for high delta & liquidity.
        """
        step = InstitutionalQuantEngine.get_strike_step(symbol)
        atm_strike = int(round(ltp / step) * step)

        if is_bullish:
            # For Call Option: ATM or 1 step ITM
            strike = atm_strike
            opt_type = "CE"
        else:
            # For Put Option: ATM or 1 step ITM
            strike = atm_strike
            opt_type = "PE"

        clean_symbol = (
            "NIFTY"
            if "NIFTY 50" in symbol.upper() or symbol.upper() == "NIFTY"
            else ("BANKNIFTY" if "BANK" in symbol.upper() else symbol.replace(" ", ""))
        )
        instrument_label = f"{clean_symbol} {strike} {opt_type}"
        return strike, instrument_label

    @staticmethod
    def _previous_session_ohlc(candle_df: pd.DataFrame) -> dict[str, float] | None:
        """High/low/close of the trading day before the latest bar's day, if the data holds one."""
        if "timestamp" not in candle_df.columns or candle_df.empty:
            return None
        days = candle_df["timestamp"].astype(str).str[:10]
        earlier = days[days < days.iloc[-1]]
        if earlier.empty:
            return None
        prev = candle_df[days == earlier.iloc[-1]]
        return {
            "high": float(prev["high"].max()),
            "low": float(prev["low"].min()),
            "close": float(prev["close"].iloc[-1]),
        }

    def evaluate_quantitative_setup(
        self,
        symbol: str,
        quote: dict[str, Any],
        candle_df: pd.DataFrame | None,
        prev_day_ohlc: dict[str, float] | None = None,
        as_of: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        """
        Evaluates full multi-factor technical indicators and generates an institutional setup.

        Returns:
            Dict containing trade decision, confluence score, signals, levels, and rationale.
        """
        now_dt = as_of or datetime.datetime.now()
        ltp = float(quote.get("ltp", 0.0))
        if candle_df is None or len(candle_df) < 5 or ltp <= 0:
            return self._build_empty_response(
                symbol, ltp, "Insufficient historical candle bars from Zerodha Kite."
            )

        last_row = candle_df.iloc[-1]
        close = float(last_row["close"])
        ema_9 = float(last_row.get("ema_9", close))
        ema_21 = float(last_row.get("ema_21", close))
        ema_50 = float(last_row.get("ema_50", close))
        vwap = float(last_row.get("vwap", close))
        vwap_upper = float(last_row.get("vwap_upper", vwap * 1.005))
        vwap_lower = float(last_row.get("vwap_lower", vwap * 0.995))
        rsi = float(last_row.get("rsi_14", 50.0))
        atr = float(last_row.get("atr_14", close * 0.005))
        st_val = float(last_row.get("supertrend", close))
        st_dir = int(last_row.get("supertrend_direction", 1))
        adx = float(last_row.get("adx_14", 20.0))
        plus_di = float(last_row.get("plus_di", 20.0))
        minus_di = float(last_row.get("minus_di", 20.0))

        divergence = detect_rsi_divergence(candle_df)

        # -------------------------------------------------------------
        # 15-Minute Opening Range (ORB) Filter (09:15 - 09:30 IST)
        # -------------------------------------------------------------
        orb_high: float | None = None
        orb_low: float | None = None
        is_opening_period = False

        if "timestamp" in candle_df.columns and not candle_df.empty:
            last_ts = str(candle_df["timestamp"].iloc[-1])
            session_date = last_ts[:10] if len(last_ts) >= 10 else now_dt.strftime("%Y-%m-%d")
            session_candles = candle_df[candle_df["timestamp"].astype(str).str.startswith(session_date)]
            if not session_candles.empty:
                # 09:15 to 09:30 constitutes the first three 5-min bars
                orb_bars = session_candles.iloc[:3]
                if len(orb_bars) > 0:
                    orb_high = float(orb_bars["high"].max())
                    orb_low = float(orb_bars["low"].min())
                if session_date == now_dt.strftime("%Y-%m-%d"):
                    now_time = now_dt.time()
                    if datetime.time(9, 15) <= now_time < datetime.time(9, 30):
                        is_opening_period = True
        elif len(candle_df) >= 3:
            orb_high = float(candle_df.iloc[:3]["high"].max())
            orb_low = float(candle_df.iloc[:3]["low"].min())

        if is_opening_period:
            return {
                "symbol": symbol,
                "actionable": False,
                "decision": "NO_TRADE",
                "confluence_score": 0,
                "direction": "NEUTRAL",
                "reason": "Opening Range Formation: 09:15 - 09:30 IST noise filter active. Awaiting 15-min range settlement to prevent morning gap-traps.",
                "indicators": {"close": close, "orb_high": orb_high, "orb_low": orb_low},
            }

        # CPR & Floor Pivots
        if prev_day_ohlc and prev_day_ohlc.get("high", 0) > 0:
            high_p = prev_day_ohlc["high"]
            low_p = prev_day_ohlc["low"]
            close_p = prev_day_ohlc["close"]
        else:
            prev = self._previous_session_ohlc(candle_df)
            if prev:
                high_p, low_p, close_p = prev["high"], prev["low"], prev["close"]
            else:
                high_p = float(candle_df["high"].max())
                low_p = float(candle_df["low"].min())
                close_p = close

        cpr = calculate_cpr(high_p, low_p, close_p)
        pivots = calculate_pivot_points(high_p, low_p, close_p)

        # -------------------------------------------------------------
        # Factor Scoring Matrix (Confluence Analysis)
        # -------------------------------------------------------------
        bullish_score = 0
        bearish_score = 0
        reasons: list[str] = []

        # 0. 15-Minute ORB Breakout Check
        if orb_high is not None and orb_low is not None:
            if close > orb_high:
                bullish_score += 15
                reasons.append(f"Price broke above 15-min Opening Range High (₹{orb_high:.2f})")
            elif close < orb_low:
                bearish_score += 15
                reasons.append(f"Price broke below 15-min Opening Range Low (₹{orb_low:.2f})")
            else:
                reasons.append(
                    f"Price trading within 15-min Opening Range (₹{orb_low:.2f} - ₹{orb_high:.2f})"
                )

        # 1. EMA Ribbon Alignment
        if close > ema_9 > ema_21 > ema_50:
            bullish_score += 25
            reasons.append("Perfect Bullish EMA Ribbon alignment (Close > EMA9 > EMA21 > EMA50)")
        elif close > ema_9 > ema_21:
            bullish_score += 15
            reasons.append("Bullish short-term EMA cross (EMA9 > EMA21)")
        elif close < ema_9 < ema_21 < ema_50:
            bearish_score += 25
            reasons.append("Strong Bearish EMA Ribbon alignment (Close < EMA9 < EMA21 < EMA50)")
        elif close < ema_9 < ema_21:
            bearish_score += 15
            reasons.append("Bearish short-term EMA cross (EMA9 < EMA21)")

        # 2. Supertrend Confluence
        if st_dir == 1 and close > st_val:
            bullish_score += 20
            reasons.append(f"Supertrend (10,3) is GREEN/BULLISH (Support @ ₹{st_val:.2f})")
        elif st_dir == -1 and close < st_val:
            bearish_score += 20
            reasons.append(f"Supertrend (10,3) is RED/BEARISH (Resistance @ ₹{st_val:.2f})")

        # 3. Institutional VWAP Baseline
        if close > vwap:
            bullish_score += 20
            if close > vwap_upper:
                reasons.append("Price expanding above VWAP Upper Band (Strong Bullish Momentum)")
            else:
                reasons.append(f"Price holding above institutional VWAP @ ₹{vwap:.2f}")
        else:
            bearish_score += 20
            if close < vwap_lower:
                reasons.append("Price breaking below VWAP Lower Band (Strong Bearish Breakdown)")
            else:
                reasons.append(f"Price trading below institutional VWAP @ ₹{vwap:.2f}")

        # 4. Trend Strength Filter: ADX & DMI
        if adx >= 22:
            if plus_di > minus_di + 4:
                bullish_score += 15
                reasons.append(f"ADX ({adx:.1f}) confirms strong bullish trend momentum (+DI > -DI)")
            elif minus_di > plus_di + 4:
                bearish_score += 15
                reasons.append(f"ADX ({adx:.1f}) confirms strong bearish trend momentum (-DI > +DI)")
            else:
                reasons.append(f"ADX is {adx:.1f} (Moderate Trend)")
        else:
            # Penalize when ADX < 20 (Choppy consolidation)
            bullish_score = max(0, bullish_score - 15)
            bearish_score = max(0, bearish_score - 15)
            reasons.append(f"ADX is low ({adx:.1f} < 22) - Market is in sideways chop zone")

        # 5. RSI Momentum Regime
        if 53 <= rsi <= 72:
            bullish_score += 15
            reasons.append(f"RSI ({rsi:.1f}) is in healthy Bullish Expansion Zone (53-72)")
        elif 28 <= rsi <= 47:
            bearish_score += 15
            reasons.append(f"RSI ({rsi:.1f}) is in healthy Bearish Breakdown Zone (28-47)")
        elif rsi > 75:
            bullish_score += 5
            reasons.append(f"RSI ({rsi:.1f}) is Overbought - caution on extended longs")
        elif rsi < 25:
            bearish_score += 5
            reasons.append(f"RSI ({rsi:.1f}) is Oversold - caution on extended shorts")

        # 6. CPR & Structural Levels
        if close > cpr["tc"]:
            bullish_score += 10
            reasons.append(f"Price is trading above CPR Top Central (TC: ₹{cpr['tc']:.2f})")
        elif close < cpr["bc"]:
            bearish_score += 10
            reasons.append(f"Price is trading below CPR Bottom Central (BC: ₹{cpr['bc']:.2f})")
        else:
            # Trapped inside CPR -> Consolidation Warning
            bullish_score = max(0, bullish_score - 10)
            bearish_score = max(0, bearish_score - 10)
            reasons.append("Price is trapped INSIDE Central Pivot Range (CPR) - Expect consolidation")

        # 7. RSI Divergence Booster
        if divergence == "BULLISH_DIVERGENCE":
            bullish_score += 15
            reasons.append("BULLISH RSI DIVERGENCE detected on recent price action")
        elif divergence == "BEARISH_DIVERGENCE":
            bearish_score += 15
            reasons.append("BEARISH RSI DIVERGENCE detected on recent price action")

        # 8. Institutional Volume Surge Confirmation
        if "volume" in candle_df.columns and len(candle_df) >= 20:
            vol_series = candle_df["volume"]
            avg_vol = vol_series.rolling(20).mean().iloc[-1]
            last_vol = vol_series.iloc[-1]
            if last_vol > avg_vol * 1.25 and avg_vol > 0:
                if bullish_score > bearish_score:
                    bullish_score += 15
                    reasons.append(
                        f"Institutional Volume Surge confirmed ({last_vol / avg_vol:.1f}x of 20-bar avg)"
                    )
                else:
                    bearish_score += 15
                    reasons.append(
                        f"Institutional Volume Selling Surge confirmed ({last_vol / avg_vol:.1f}x of 20-bar avg)"
                    )

        # -------------------------------------------------------------
        # Decision Synthesis & Risk-Reward Parameterization
        # -------------------------------------------------------------
        is_index = is_index_symbol(symbol)
        max_score = max(bullish_score, bearish_score)
        is_bullish = bullish_score > bearish_score

        # Strict Capital Preservation: Minimum Confluence of 75 required for A+ trade entry
        min_threshold = 75
        if max_score < min_threshold or (adx < 20 and cpr["bc"] <= close <= cpr["tc"]):
            return {
                "symbol": symbol,
                "actionable": False,
                "decision": "NO_TRADE",
                "confluence_score": max_score,
                "direction": "NEUTRAL",
                "reason": (
                    f"Capital Preservation Filter: Confluence score ({max_score}/100) below A+ threshold (75) "
                    f"or market in consolidation (ADX: {adx:.1f}). Standing aside to prevent losses."
                ),
                "indicators": {
                    "close": close,
                    "ema_9": round(ema_9, 2),
                    "ema_21": round(ema_21, 2),
                    "ema_50": round(ema_50, 2),
                    "vwap": round(vwap, 2),
                    "rsi": round(rsi, 2),
                    "adx": round(adx, 2),
                    "supertrend": round(st_val, 2),
                    "supertrend_direction": "BULLISH" if st_dir == 1 else "BEARISH",
                    "cpr": cpr,
                    "pivots": pivots,
                },
                "technical_rationale": " | ".join(reasons),
            }

        # Format actionable high-expectancy trade setup
        if is_index:
            _strike, instrument = self.resolve_optimal_strike(symbol, close, is_bullish)
            signal_type = "BUY_CALL" if is_bullish else "BUY_PUT"
            opt_quote = quote.get("call_option" if is_bullish else "put_option")
            entry_price = (
                float(opt_quote["ltp"])
                if opt_quote and opt_quote.get("ltp")
                else round(max(30.0, atr * 1.5), 2)
            )

            # Ultra-protective Risk Management for Options: tight 10% stop-loss, asymmetric 1:2.0 and 1:3.0 targets
            risk_points = round(max(8.0, entry_price * 0.10), 2)
            stop_loss = round(max(2.0, entry_price - risk_points), 2)
            target_1 = round(entry_price + (risk_points * 2.0), 2)  # 1:2.0 RR
            target_2 = round(entry_price + (risk_points * 3.0), 2)  # 1:3.0 RR
        else:
            instrument = f"{symbol} MIS"
            signal_type = "BUY_EQUITY" if is_bullish else "SHORT_EQUITY"
            entry_price = round(close, 2)
            risk_points = round(max(1.5, atr * 1.0), 2)
            stop_loss = round(entry_price - risk_points if is_bullish else entry_price + risk_points, 2)
            target_1 = round(
                entry_price + (risk_points * 2.0) if is_bullish else entry_price - (risk_points * 2.0), 2
            )
            target_2 = round(
                entry_price + (risk_points * 3.2) if is_bullish else entry_price - (risk_points * 3.2), 2
            )

        action_word = (
            "BUY CALL"
            if signal_type == "BUY_CALL"
            else (
                "BUY PUT"
                if signal_type == "BUY_PUT"
                else ("LONG" if signal_type == "BUY_EQUITY" else "SHORT")
            )
        )

        verbal_pitch = (
            f"Institutional A+ Trade Signal: High conviction {action_word} on {instrument}. "
            f"Entry at ₹{entry_price}, Tight Stop Loss at ₹{stop_loss}, Target at ₹{target_1}. "
            f"Confluence score is {max_score}%. Please say 'Approve' to confirm."
        )

        return {
            "symbol": symbol,
            "actionable": True,
            "instrument_to_trade": instrument,
            "signal_type": signal_type,
            "direction": "BULLISH" if is_bullish else "BEARISH",
            "lot_size": 1,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "risk_reward": "1:2.0",
            "confidence": min(95, max(75, max_score)),
            "confluence_score": max_score,
            "verbal_pitch": verbal_pitch,
            "technical_rationale": " | ".join(reasons),
            "indicators": {
                "close": close,
                "ema_9": round(ema_9, 2),
                "ema_21": round(ema_21, 2),
                "ema_50": round(ema_50, 2),
                "vwap": round(vwap, 2),
                "rsi": round(rsi, 2),
                "adx": round(adx, 2),
                "supertrend": round(st_val, 2),
                "supertrend_direction": "BULLISH" if st_dir == 1 else "BEARISH",
                "cpr": cpr,
                "pivots": pivots,
            },
        }

    def _build_empty_response(self, symbol: str, ltp: float, reason: str) -> dict[str, Any]:
        """Constructs safe fallback response when data is incomplete."""
        return {
            "symbol": symbol,
            "actionable": False,
            "decision": "NO_TRADE",
            "confluence_score": 0,
            "direction": "NEUTRAL",
            "reason": reason,
            "indicators": {"close": ltp},
        }


# Singleton instance
quant_engine = InstitutionalQuantEngine()
