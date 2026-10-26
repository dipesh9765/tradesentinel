"""
Trading Operations, AI Proposal Evaluation & Order Management Endpoints
"""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

import database
from app.api.deps import require_auth
from app.models.schemas import ApproveRequest, ClosePositionRequest, RejectRequest, ScanRequest
from config import get_watchlist_symbols
from kite_executor import kite_executor
from market_data import market_data_manager
from notifications import notification_service
from trade_analyzer import trade_analyzer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Trading Operations"])


@router.post("/api/ai/scan", dependencies=[Depends(require_auth)])
@router.post("/api/trade/scan", dependencies=[Depends(require_auth)])
async def scan_symbol_endpoint(req: ScanRequest, background_tasks: BackgroundTasks):
    """
    Triggers AI Quantitative Market Scan.
    Requires connected Zerodha Kite session for authentic data feeds.
    """
    if not kite_executor.api_key or not kite_executor.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zerodha Kite Connect is not configured or daily session is inactive. Please configure in Settings.",
        )

    symbol = req.symbol or get_watchlist_symbols()[0]
    quote = market_data_manager.get_quote(symbol)
    candle_df = market_data_manager.candles_data.get(symbol)

    signal = trade_analyzer.analyze_market_setup(symbol, quote, candle_df)
    if not signal.get("actionable"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No trade: {signal.get('reason', 'no qualifying setup')}",
        )
    try:
        proposal = kite_executor.create_trade_proposal(signal)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"No trade: {e}") from e

    background_tasks.add_task(notification_service.notify_trade_proposal, proposal)
    return {"proposal": proposal, **proposal}


@router.post("/api/trades/approve", dependencies=[Depends(require_auth)])
@router.post("/api/trade/approve", dependencies=[Depends(require_auth)])
async def approve_trade(req: ApproveRequest, background_tasks: BackgroundTasks):
    """
    User confirms an AI trade proposal (LIVE or PAPER mode).
    Enforces risk guardrail of max 1 lot during initial phase.
    """
    try:
        # Live entries poll the broker for fills; keep that off the event loop.
        executed_trade = await asyncio.to_thread(kite_executor.approve_trade, req.proposal_id)
        if executed_trade and "order" in executed_trade and "position" in executed_trade:
            background_tasks.add_task(
                notification_service.notify_trade_executed,
                executed_trade["order"],
                executed_trade["position"],
            )
        return {"success": True, "executed_trade": executed_trade}
    except Exception as e:
        logger.error(f"Trade approval failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/api/trades/reject", dependencies=[Depends(require_auth)])
@router.post("/api/trade/reject", dependencies=[Depends(require_auth)])
def reject_trade(req: RejectRequest):
    """Records user rejection of an AI trade proposal."""
    try:
        rejected = kite_executor.reject_trade(req.proposal_id, req.reason or "User declined")
        return {"success": True, "proposal": rejected}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/api/positions", dependencies=[Depends(require_auth)])
@router.get("/api/trade/positions", dependencies=[Depends(require_auth)])
def get_positions():
    """Returns active positions with real-time unrealized P&L."""
    return {
        "positions": list(kite_executor.positions.values()),
        "summary": kite_executor.get_portfolio_summary(),
    }


@router.post("/api/positions/close", dependencies=[Depends(require_auth)])
@router.post("/api/trade/close-position", dependencies=[Depends(require_auth)])
def close_position(req: ClosePositionRequest):
    """Manually terminates an active position and books realized P&L."""
    try:
        res = kite_executor.close_position(req.position_id, reason="MANUAL_EXIT")
        return {"success": True, "result": res}
    except Exception as e:
        logger.error(f"Manual position close failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/api/trade/reconcile", dependencies=[Depends(require_auth)])
def reconcile_positions():
    """Compares tracked LIVE positions against Zerodha's net positions and books any that are already flat."""
    try:
        return kite_executor.reconcile_live_positions()
    except Exception as e:
        logger.error(f"Position reconcile failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/api/orders", dependencies=[Depends(require_auth)])
@router.get("/api/trade/orders", dependencies=[Depends(require_auth)])
def get_orders():
    """Returns immutable order audit history."""
    return kite_executor.orders_history


@router.get("/api/trade/portfolio", dependencies=[Depends(require_auth)])
def get_portfolio():
    """Returns portfolio P&L aggregation and capital metrics."""
    return kite_executor.get_portfolio_summary()


@router.get("/api/history", dependencies=[Depends(require_auth)])
@router.get("/api/trade/history", dependencies=[Depends(require_auth)])
def get_trade_history(limit: int = 50):
    """Returns full historical trade suggestion and linked position log from SQLite."""
    return database.get_history_from_db(limit)
