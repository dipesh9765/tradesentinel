"""
Market Data & Quantitative Technical Analysis Endpoints
"""

from fastapi import APIRouter, Depends, Query

from app.ai.trade_analyzer import trade_analyzer
from app.api.deps import require_auth
from app.core.config import settings
from app.market.market_data import market_data_manager
from app.services.notifications import notification_service
from app.trading.engine import trading_engine

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
        "kite_connected": trading_engine.is_authenticated(),
        "kite_active": trading_engine.is_authenticated(),
        "kite_verified": getattr(trading_engine.kite_engine, "_is_token_verified", False),
        "gemini_active": bool(trade_analyzer.client),
        "vault_unlocked": True,
        "is_market_live": market_data_manager.is_live,
        "market_status_message": market_data_manager.status_message,
        "portfolio": trading_engine.get_portfolio_summary(),
        "office_mode": notification_service.config.office_mode,
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
