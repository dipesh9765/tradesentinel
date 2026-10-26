"""
Authentication & Cryptographic Vault Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.ai.trade_analyzer import trade_analyzer
from app.api.deps import require_auth, security_scheme
from app.core.security import (
    clear_login_failures,
    create_session_token,
    invalidate_session_token,
    login_lockout_remaining,
    register_login_failure,
    validate_session_token,
)
from app.db import database
from app.models.schemas import LoginRequest, SetupRequest
from app.trading.engine import trading_engine

router = APIRouter(tags=["Authentication"])


@router.get("/api/auth/status")
def get_auth_status(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)):
    """Checks whether master password is configured, and whether client has valid session."""
    is_init = database.is_master_password_set()
    token = credentials.credentials if credentials else None
    is_auth = validate_session_token(token) if token else False
    is_vault = database.is_vault_unlocked()
    return {"is_initialized": is_init, "is_authenticated": is_auth, "is_vault_unlocked": is_vault}


@router.post("/api/auth/setup")
def setup_master_password_endpoint(req: SetupRequest):
    """One-time initial master password configuration."""
    if database.is_master_password_set():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already initialized with a master password. Please use login.",
        )
    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Master password must be at least 6 characters."
        )
    database.setup_master_password(req.password)
    trading_engine.load_credentials()
    trade_analyzer.load_credentials()
    token = create_session_token()
    return {
        "success": True,
        "token": token,
        "message": "Master password successfully created. Security vault is unlocked.",
    }


@router.post("/api/auth/login")
def login_master_password(req: LoginRequest, request: Request):
    """Authenticates against PBKDF2 hash and unlocks encrypted Fernet vault."""
    if not database.is_master_password_set():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System not initialized. Master password setup required.",
        )
    client_key = request.client.host if request.client else "unknown"
    wait = login_lockout_remaining(client_key)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )
    is_valid = database.verify_and_unlock_master_password(req.password)
    if not is_valid:
        register_login_failure(client_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect master password.")
    clear_login_failures(client_key)
    trading_engine.load_credentials()
    trade_analyzer.load_credentials()
    token = create_session_token()
    return {"success": True, "token": token, "message": "Master password verified. Security vault unlocked."}


@router.post("/api/auth/logout")
def logout_endpoint(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)):
    """Revokes session token and securely locks the cryptographic vault."""
    if credentials:
        invalidate_session_token(credentials.credentials)
    database.lock_vault()
    return {"success": True, "message": "Logged out successfully. Security vault locked."}


@router.get("/api/auth/verify", dependencies=[Depends(require_auth)])
def verify_auth_token_endpoint():
    """Returns real-time verification of session and 30-second Kite token check status."""
    token_status = trading_engine.verify_auth_token_now()
    return {"authenticated": True, "session_valid": True, "kite_token_check": token_status}
