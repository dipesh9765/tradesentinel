"""
Pydantic Request & Response Data Transfer Objects (DTOs)
"""

from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    password: str = Field(..., description="Master password to initialize secure vault")


class LoginRequest(BaseModel):
    password: str = Field(..., description="Master password to authenticate session")


class ScanRequest(BaseModel):
    symbol: str | None = Field(
        default=None,
        description="Underlying symbol to scan. Defaults dynamically to the first configured watchlist instrument if omitted.",
    )


class ApproveRequest(BaseModel):
    proposal_id: str = Field(..., description="Proposal ID to approve for execution")


class RejectRequest(BaseModel):
    proposal_id: str = Field(..., description="Proposal ID to reject")
    reason: str | None = Field(default="User declined", description="Rejection rationale")


class ClosePositionRequest(BaseModel):
    position_id: str = Field(..., description="Position ID to close")


class SettingsUpdateRequest(BaseModel):
    kite_api_key: str | None = None
    kite_api_secret: str | None = None
    kite_access_token: str | None = None
    gemini_api_key: str | None = None
    trading_mode: str | None = None  # "PAPER" or "LIVE"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None
    slack_webhook_url: str | None = None
    office_mode: bool | None = None


class ModeUpdateRequest(BaseModel):
    trading_mode: str = Field(..., description="'PAPER' or 'LIVE'")


class KiteSessionRequest(BaseModel):
    request_token: str = Field(..., description="OAuth request token from Zerodha login redirect")
