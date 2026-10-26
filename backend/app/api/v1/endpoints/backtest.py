"""
Strategy Backtest Endpoint
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import require_auth
from backtester import run_backtest
from market_data import market_data_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Backtesting"])


class BacktestRequest(BaseModel):
    symbol: str = Field(..., description="Symbol from instruments.json, e.g. 'BANK NIFTY'")
    days: int = Field(default=30, ge=5, le=60, description="Calendar days of 5-minute history to replay")
    lots: int = Field(default=1, ge=1, le=10)


@router.post("/api/backtest", dependencies=[Depends(require_auth)])
async def backtest_endpoint(req: BacktestRequest):
    """
    Replays recent Kite 5-minute history through the live rules engine and exit rules, charging
    realistic costs and slippage. Requires an active Kite session for historical data.
    """
    try:
        df = await asyncio.to_thread(market_data_manager.fetch_history_df, req.symbol, req.days)
        return await asyncio.to_thread(run_backtest, df, req.symbol, req.lots)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Backtest failed: {e}"
        ) from e
