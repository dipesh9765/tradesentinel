"""
KitePulse AI - Application Entrypoint & Lifespan Orchestrator
FastAPI Enterprise Application Factory
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.router import api_v1_router
from app.api.v1.endpoints.websocket import active_connections
from market_data import market_data_manager
from kite_executor import kite_executor
from app.core.genConsts import GenConsts
from server_logger import RequestResponseLoggingMiddleware, setup_server_logging

# Initialize 3MB rotating server logging with timestamp
setup_server_logging()

logger = logging.getLogger(__name__)


# ==================== BACKGROUND WORKERS & LIFESPAN ====================

async def periodic_30s_token_verification_worker() -> None:
    """
    Periodic 30-second token verification heartbeat worker:
    1. Verifies that active system sessions are valid.
    2. Validates that outgoing Kite request authentication token is correct with Zerodha servers.
    """
    while True:
        try:
            kite_executor.verify_auth_token_now()
        except Exception as e:
            logger.error(f"Error in 30s token verification worker: {e}")
        await asyncio.sleep(30.0)


async def background_market_worker() -> None:
    """
    Continuously syncs authentic market quotes from Zerodha Kite (when configured),
    updates open position P&L, and checks stop-loss / target triggers.
    Enforces strict zero dummy data integrity.
    """
    reconciled_token = None
    while True:
        try:
            # Once per Kite session: compare tracked LIVE positions with the broker's, so anything that
            # closed while this app was offline (e.g. the broker-side stop fired) is booked correctly.
            if (kite_executor.mode == "LIVE" and kite_executor.is_authenticated()
                    and kite_executor.access_token != reconciled_token):
                reconciled_token = kite_executor.access_token
                try:
                    report = await asyncio.to_thread(kite_executor.reconcile_live_positions)
                    logger.info(f"Startup position reconcile: {report}")
                except Exception as e:
                    logger.error(f"Startup position reconcile failed: {e}")

            if market_data_manager.is_configured():
                updated = market_data_manager.refresh_live_quotes()
                if updated:
                    kite_executor.update_positions_pnl(market_data_manager.live_prices)

            # Broadcast live quotes to all connected authenticated WebSocket clients
            if active_connections:
                payload = {
                    "type": GenConsts.WS_EVENT_TICK,
                    "is_live": market_data_manager.is_live,
                    "status_message": market_data_manager.status_message,
                    "quotes": market_data_manager.get_all_quotes(),
                    "portfolio": kite_executor.get_portfolio_summary(),
                    "positions": list(kite_executor.positions.values())
                }
                for ws in list(active_connections):
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        if ws in active_connections:
                            active_connections.remove(ws)
        except Exception as e:
            logger.error(f"Error in background market loop: {e}")
        await asyncio.sleep(float(GenConsts.MARKET_TICK_STREAM_INTERVAL_SEC))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan context manager:
    Initializes background workers on startup and cleanly cancels them on shutdown.
    """
    from scanner import opportunity_scanner

    logger.info("Initializing KitePulse background market sync & P&L monitor...")
    market_task = asyncio.create_task(background_market_worker())
    logger.info("Initializing KitePulse 30-second token verification heartbeat...")
    token_task = asyncio.create_task(periodic_30s_token_verification_worker())
    logger.info("Initializing Autonomous Market Opportunity Scanner...")
    scanner_task = asyncio.create_task(opportunity_scanner.start_loop())

    yield

    logger.info("Shutting down KitePulse background tasks...")
    market_task.cancel()
    token_task.cancel()
    scanner_task.cancel()
    opportunity_scanner.stop()
    await asyncio.gather(market_task, token_task, scanner_task, return_exceptions=True)
    logger.info("KitePulse background tasks terminated.")


tags_metadata = [
    {"name": "Authentication", "description": "Master password, PBKDF2 vault, and Bearer session verification."},
    {"name": "Market Data", "description": "Authentic Zerodha Kite quotes and technical indicator candles."},
    {"name": "Trading Operations", "description": "AI scanning, trade proposals, order approval, and position termination."},
    {"name": "Settings", "description": "Encrypted credentials, Zerodha OAuth session, and trading mode management."},
    {"name": "Streaming", "description": "Low-latency WebSocket tick stream and real-time state synchronization."}
]


def create_app() -> FastAPI:
    """Application factory for KitePulse AI FastAPI REST server."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="High-frequency algorithmic & AI intraday trading execution platform for Indian Equity & Derivatives (NSE Zerodha).",
        openapi_tags=tags_metadata,
        lifespan=lifespan
    )

    # Middleware: Request/Response Auditing & Telemetry
    app.add_middleware(RequestResponseLoggingMiddleware)

    # Middleware: CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000"
        ],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|100\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|.*\.ts\.net)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(api_v1_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
