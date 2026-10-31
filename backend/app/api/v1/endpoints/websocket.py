"""
Real-time WebSocket Streaming Feed Endpoint
"""

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.genConsts import GenConsts
from app.core.security import validate_session_token
from app.market.market_data import market_data_manager
from app.trading.engine import trading_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Streaming"])

active_connections: list[WebSocket] = []


def get_active_connections() -> list[WebSocket]:
    return active_connections


@router.websocket("/ws/live")
async def websocket_live_feed(websocket: WebSocket, token: str | None = Query(None)):
    """
    Protected WebSocket feed: Verifies master password session token before accepting connection.
    Streams market ticks and portfolio updates every 2 seconds.
    """
    if not validate_session_token(token):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    active_connections.append(websocket)
    try:
        await websocket.send_json(
            {
                "type": GenConsts.WS_EVENT_INIT,
                "is_live": market_data_manager.is_live,
                "status_message": market_data_manager.status_message,
                "quotes": market_data_manager.get_all_quotes(),
                "portfolio": trading_engine.get_portfolio_summary(),
                "positions": list(trading_engine.positions.values()),
            }
        )
        while True:
            data = await websocket.receive_text()
            logger.info(f"WebSocket client sent: {data}")
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)
