"""
Liveness and readiness probes (unauthenticated, no sensitive data).

- /healthz: the process is up and the event loop is responsive. Used by container liveness checks.
- /readyz:  the process can also reach its database. Used by orchestrators before routing traffic.
"""

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.db import database

router = APIRouter(tags=["Health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(response: Response) -> dict[str, str]:
    try:
        conn = database.get_db_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "error"}
    return {
        "status": "ready",
        "database": "ok",
        "version": settings.APP_VERSION,
        "mode": settings.TRADING_MODE,
    }
