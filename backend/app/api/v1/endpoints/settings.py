"""
System Settings, Secure Vault & Broker Connectivity Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.ai import ai_providers
from app.ai.trade_analyzer import trade_analyzer
from app.api.deps import require_auth
from app.core.config import load_instruments_data, settings
from app.core.server_logger import log_config_saved
from app.db import database
from app.market.market_data import market_data_manager
from app.models.schemas import KiteSessionRequest, ModeUpdateRequest, SettingsUpdateRequest
from app.services.notifications import notification_service
from app.trading.engine import trading_engine

router = APIRouter(tags=["Settings"])


@router.get("/api/settings", dependencies=[Depends(require_auth)])
def get_settings():
    """Returns masked previews of active configurations from the encrypted vault."""
    k_key = database.get_secure_setting("KITE_API_KEY", "")
    k_sec = database.get_secure_setting("KITE_API_SECRET", "")
    k_tok = database.get_secure_setting("KITE_ACCESS_TOKEN", "")
    g_key = database.get_secure_setting("GEMINI_API_KEY", "")

    def mask_key(val: str) -> str:
        if not val:
            return ""
        if len(val) <= 6:
            return "••••••••"
        return val[:3] + "••••••••" + val[-3:]

    return {
        "has_kite_api_key": bool(k_key),
        "kite_api_key_preview": mask_key(k_key),
        "has_kite_api_secret": bool(k_sec),
        "kite_api_secret_preview": mask_key(k_sec),
        "has_kite_access_token": bool(k_tok),
        "kite_access_token_preview": mask_key(k_tok),
        "has_gemini_api_key": bool(g_key),
        "gemini_api_key_preview": mask_key(g_key),
        "trading_mode": settings.TRADING_MODE,
        "telegram_bot_token": notification_service.config.telegram_bot_token or "",
        "telegram_chat_id": notification_service.config.telegram_chat_id or "",
        "discord_webhook_url": notification_service.config.discord_webhook_url or "",
        "slack_webhook_url": notification_service.config.slack_webhook_url or "",
        "office_mode": notification_service.config.office_mode,
        "gemini_active": bool(trade_analyzer.client),
        "ai_provider": ai_providers.get_active_provider(),
        "ai_active": ai_providers.is_configured(),
        "kite_active": trading_engine.is_authenticated(),
    }


class AIConfigUpdate(BaseModel):
    provider: str | None = None  # provider to make active
    model: str | None = None  # model for `target_provider` (defaults to `provider`)
    target_provider: str | None = None
    api_key: str | None = None  # key for `target_provider`


@router.get("/api/ai/config", dependencies=[Depends(require_auth)])
def get_ai_config():
    """Returns AI provider choices, selected models and which providers have keys (never raw keys)."""
    return ai_providers.describe_config()


@router.post("/api/ai/config", dependencies=[Depends(require_auth)])
def update_ai_config(req: AIConfigUpdate):
    """Saves the active provider, a provider's model and/or its API key to the encrypted vault."""
    target = req.target_provider or req.provider
    if target and target not in ai_providers.PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown AI provider '{target}'."
        )
    modified = []
    try:
        if req.api_key and req.api_key.strip():
            if not target:
                raise ValueError("Specify which provider the API key belongs to.")
            ai_providers.set_api_key(target, req.api_key)
            modified.append(ai_providers.PROVIDERS[target]["key_setting"])
        if req.model and req.model.strip():
            if not target:
                raise ValueError("Specify which provider the model belongs to.")
            ai_providers.set_model(target, req.model)
            modified.append(ai_providers.PROVIDERS[target]["model_setting"])
        if req.provider:
            ai_providers.set_active_provider(req.provider)
            modified.append(ai_providers.AI_PROVIDER_SETTING)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    log_config_saved("api/ai/config", modified)
    return {"success": True, **ai_providers.describe_config()}


@router.post("/api/ai/test", dependencies=[Depends(require_auth)])
def test_ai_provider(req: AIConfigUpdate):
    """Makes one tiny live call to verify a provider/model/key combination works."""
    provider = req.target_provider or req.provider or ai_providers.get_active_provider()
    if provider not in ai_providers.PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown AI provider '{provider}'."
        )
    try:
        ai_providers.generate_json(
            'Reply with exactly this JSON: {"ok": true}',
            provider=provider,
            model=(req.model or "").strip() or None,
            api_key=(req.api_key or "").strip() or None,
        )
    except ai_providers.AIProviderError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"success": True, "provider": provider}


@router.post("/api/notifications/test", dependencies=[Depends(require_auth)])
async def test_notifications_endpoint():
    """Sends a test alert across all configured communication channels."""
    test_symbol = settings.WATCHLIST_SYMBOLS[0] if settings.WATCHLIST_SYMBOLS else "TEST"
    test_proposal = {
        "symbol": test_symbol,
        "instrument": f"{test_symbol} TEST 25000 CE",
        "signal_type": "BUY_CALL",
        "entry_price": 125.0,
        "stop_loss": 105.0,
        "target_1": 165.0,
        "risk_reward": "1:2.0",
        "confidence": 95,
        "verbal_pitch": f"Test notification for {test_symbol} from TradeSentinel",
        "technical_rationale": "System verification of webhook channels",
    }
    await notification_service.notify_trade_proposal(test_proposal)
    return {"success": True, "message": "Test alert dispatched to configured notification channels."}


@router.post("/api/settings", dependencies=[Depends(require_auth)])
def update_settings(req: SettingsUpdateRequest):
    """Saves sensitive API keys and secrets encrypted in the SQLite secure vault."""
    if req.gemini_api_key:
        clean_key = req.gemini_api_key.strip()
        database.save_secure_setting("GEMINI_API_KEY", clean_key)
        settings.GEMINI_API_KEY = clean_key
        trade_analyzer.update_api_key(clean_key)

    if req.kite_api_key:
        clean_api_key = req.kite_api_key.strip()
        database.save_secure_setting("KITE_API_KEY", clean_api_key)
        settings.KITE_API_KEY = clean_api_key
        trading_engine.api_key = clean_api_key
        trading_engine._init_kite()

    if req.kite_api_secret:
        clean_secret = req.kite_api_secret.strip()
        database.save_secure_setting("KITE_API_SECRET", clean_secret)
        settings.KITE_API_SECRET = clean_secret

    if req.kite_access_token:
        clean_token = req.kite_access_token.strip()
        database.save_secure_setting("KITE_ACCESS_TOKEN", clean_token)
        settings.KITE_ACCESS_TOKEN = clean_token
        trading_engine.access_token = clean_token
        trading_engine.kite_engine.access_token = clean_token
        if trading_engine.kite_client:
            trading_engine.kite_client.set_access_token(clean_token)
        elif trading_engine.api_key:
            trading_engine._init_kite()

    if req.trading_mode in ["PAPER", "LIVE"]:
        settings.TRADING_MODE = req.trading_mode
        trading_engine.mode = req.trading_mode
        database.save_secure_setting("TRADING_MODE", req.trading_mode)

    notification_service.update_config(
        {
            "telegram_bot_token": req.telegram_bot_token,
            "telegram_chat_id": req.telegram_chat_id,
            "discord_webhook_url": req.discord_webhook_url,
            "slack_webhook_url": req.slack_webhook_url,
            "office_mode": req.office_mode,
        }
    )

    modified_keys = []
    if req.gemini_api_key:
        modified_keys.append("GEMINI_API_KEY")
    if req.kite_api_key:
        modified_keys.append("KITE_API_KEY")
    if req.kite_api_secret:
        modified_keys.append("KITE_API_SECRET")
    if req.kite_access_token:
        modified_keys.append("KITE_ACCESS_TOKEN")
    if req.trading_mode:
        modified_keys.append("TRADING_MODE")
    if any(
        [
            req.telegram_bot_token,
            req.telegram_chat_id,
            req.discord_webhook_url,
            req.slack_webhook_url,
            req.office_mode is not None,
        ]
    ):
        modified_keys.append("NOTIFICATIONS")
    log_config_saved("api/settings", modified_keys, req.trading_mode)

    return {
        "success": True,
        "mode": trading_engine.mode,
        "gemini_active": bool(trade_analyzer.client),
        "kite_active": trading_engine.is_authenticated(),
        "office_mode": notification_service.config.office_mode,
    }


@router.get("/api/kite/login-url", dependencies=[Depends(require_auth)])
def get_kite_login_url():
    """Generates Zerodha OAuth login URL."""
    return {"login_url": trading_engine.get_login_url()}


@router.post("/api/kite/session", dependencies=[Depends(require_auth)])
def generate_kite_session(req: KiteSessionRequest):
    """Exchanges OAuth request token for Zerodha daily access token and stores in vault."""
    try:
        session = trading_engine.set_session(req.request_token)
        log_config_saved("api/kite/session", ["KITE_ACCESS_TOKEN"])
        market_data_manager.refresh_live_quotes()
        return {"success": True, "session": session}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/api/kite/balance", dependencies=[Depends(require_auth)])
def get_kite_balance():
    """
    Fetches real-time authentic Zerodha Kite account margins and remaining balance.
    Returns available cash, margin, utilised funds, and connection status.
    """
    return trading_engine.get_kite_margins()


@router.post("/api/settings/mode", dependencies=[Depends(require_auth)])
def update_trading_mode(req: ModeUpdateRequest):
    """Instant switch between PAPER Sandbox and Zerodha Kite LIVE with persistent database storage."""
    if req.trading_mode not in ["PAPER", "LIVE"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid mode. Must be 'PAPER' or 'LIVE'."
        )
    settings.TRADING_MODE = req.trading_mode
    trading_engine.mode = req.trading_mode
    database.save_secure_setting("TRADING_MODE", req.trading_mode)
    log_config_saved("api/settings/mode", ["TRADING_MODE"], req.trading_mode)
    return {"success": True, "trading_mode": req.trading_mode}


@router.get("/api/instruments", dependencies=[Depends(require_auth)])
def get_instruments_list():
    """Returns list of all configured trading instruments from instruments.json."""
    return load_instruments_data()


@router.post("/api/instruments/reload", dependencies=[Depends(require_auth)])
def reload_instruments_endpoint():
    """Hot-reloads instruments from instruments.json without server restart."""
    market_data_manager.reload_instruments()
    market_data_manager.refresh_live_quotes()
    return {
        "success": True,
        "message": "Successfully hot-reloaded instruments from instruments.json.",
        "instruments": market_data_manager.get_all_quotes(),
    }
