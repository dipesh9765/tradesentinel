"""
V1 API Router Aggregator
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, backtest, market, settings, trades, websocket

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router)
api_v1_router.include_router(market.router)
api_v1_router.include_router(trades.router)
api_v1_router.include_router(settings.router)
api_v1_router.include_router(websocket.router)
api_v1_router.include_router(backtest.router)
