"""
FastAPI Security & Context Dependencies
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import database
from security import validate_session_token

security_scheme = HTTPBearer(auto_error=False)


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)) -> str:
    """
    Strict security barrier dependency:
    Requires system to be initialized with a master password,
    and requires an active validated session token.
    """
    if not database.is_master_password_set():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System not initialized. Master password setup required.",
        )
    if not credentials or not validate_session_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Master password authentication required.",
        )
    return credentials.credentials
