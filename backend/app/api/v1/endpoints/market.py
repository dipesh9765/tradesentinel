"""
Market Data & Quantitative Technical Analysis Endpoints
"""

import math
from typing import Any
from fastapi import APIRouter, Depends, Query
from app.config import settings
from app.api.deps import require_auth
from market_data import market_data_manager
from kite_executor import kite_executor
from gemini_analyzer import gemini_analyzer
from notifications import notification_service

router = APIRouter(tags=["Market Data"])


@router.get("/api/status", dependencies=[Depends(require_auth)])
def get_system_status():
    """Returns general connectivity, trading mode, and broker status."""
    return {
        "status": "ONLINE",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": settings.TRADING_MODE,
        "trading_mode": settings.TRADING_MODE,
        "default_lot_size": settings.DEFAULT_LOT_SIZE,
        "kite_connected": kite_executor.is_authenticated(),
        "kite_active": kite_executor.is_authenticated(),
        "kite_verified": getattr(kite_executor.kite_engine, "_is_token_verified", False),
        "gemini_active": bool(gemini_analyzer.client),
        "vault_unlocked": True,
        "is_market_live": market_data_manager.is_live,
        "market_status_message": market_data_manager.status_message,
        "portfolio": kite_executor.get_portfolio_summary(),
        "office_mode": notification_service.config.office_mode
    }


@router.get("/api/market/quotes", dependencies=[Depends(require_auth)])
def get_quotes():
    """Returns authentic quotes for all tracked symbols. Zero dummy data is fabricated."""
    return market_data_manager.get_all_quotes()


@router.get("/api/market/candles", dependencies=[Depends(require_auth)])
def get_candles_by_query(symbol: str = Query(None), limit: int = Query(60)):
    """
    Returns authentic historical candlestick data from Zerodha Kite via query parameter.
    Includes technical indicators (EMA 9, EMA 21, VWAP, RSI 14).
    """
    target_symbol = symbol or (settings.WATCHLIST_SYMBOLS[0] if settings.WATCHLIST_SYMBOLS else "")
    meta = market_data_manager.get_candles_meta(target_symbol, limit)
    meta["symbol"] = target_symbol
    meta["is_configured"] = market_data_manager.is_configured()
    return meta


@router.get("/api/market/candles/{symbol}", dependencies=[Depends(require_auth)])
def get_candles_by_path(symbol: str, limit: int = 60):
    """Path parameter alias for historical candlestick data."""
    meta = market_data_manager.get_candles_meta(symbol, limit)
    meta["symbol"] = symbol
    meta["is_configured"] = market_data_manager.is_configured()
    return meta


@router.get("/api/market/evaluate-today")
async def evaluate_today_endpoint():
    """
    Evaluates today's authentic Kite data for active symbols using the Institutional Quant Engine.
    """
    import asyncio
    from quant_strategy import quant_engine
    import database

    if not database.is_vault_unlocked():
        return {
            "success": False,
            "error": "Security vault is locked. Please unlock with master password first."
        }

    def _run_eval():
        results = {}
        market_data_manager.refresh_live_quotes()
        
        symbols = ["BANK NIFTY", "TATAMOTORS"]
        for sym in symbols:
            quote = market_data_manager.get_quote(sym)
            meta = market_data_manager.get_candles_meta(sym, limit=100)
            candles = meta.get("candles", [])
            
            df = market_data_manager.candles_data.get(sym)
            if df is not None and not df.empty:
                setup = quant_engine.evaluate_quantitative_setup(sym, quote, df)
                results[sym] = {
                    "symbol": sym,
                    "quote": quote,
                    "candles_count": len(candles),
                    "candle_status": meta.get("status"),
                    "candle_message": meta.get("message"),
                    "actionable": setup.get("actionable", False),
                    "instrument_to_trade": setup.get("instrument_to_trade", sym),
                    "signal_type": setup.get("signal_type", "NO_TRADE"),
                    "direction": setup.get("direction", "NEUTRAL"),
                    "confluence_score": setup.get("confluence_score", 0),
                    "is_a_plus_setup": setup.get("confluence_score", 0) >= 75,
                    "entry_price": setup.get("entry_price", 0.0),
                    "stop_loss": setup.get("stop_loss", 0.0),
                    "target_1": setup.get("target_1", 0.0),
                    "target_2": setup.get("target_2", 0.0),
                    "risk_reward_ratio": setup.get("risk_reward", "1:2.0"),
                    "technical_rationale": setup.get("technical_rationale", ""),
                    "indicators": setup.get("indicators", {})
                }
            else:
                results[sym] = {
                    "symbol": sym,
                    "quote": quote,
                    "candles_count": 0,
                    "candle_status": meta.get("status"),
                    "candle_message": meta.get("message"),
                }
        return results

    def _sanitize_val(val: Any) -> Any:
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return val
        elif isinstance(val, dict):
            return {k: _sanitize_val(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [_sanitize_val(v) for v in val]
        return val

    eval_results = await asyncio.to_thread(_run_eval)
    return _sanitize_val({
        "success": True,
        "is_vault_unlocked": database.is_vault_unlocked(),
        "is_kite_authenticated": kite_executor.is_authenticated(),
        "results": eval_results
    })
