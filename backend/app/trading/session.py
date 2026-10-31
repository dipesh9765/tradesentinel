"""Broker credential lifecycle: vault load, login URL, session exchange, margins."""

import datetime
import logging
import time
from typing import Any

from app.core.config import settings
from app.core.security import has_active_session
from app.core.server_logger import log_outgoing_error, log_outgoing_request, log_outgoing_response
from app.db import database
from app.trading.state import EngineState

logger = logging.getLogger(__name__)


class BrokerSessionMixin(EngineState):
    """Broker credential lifecycle: vault load, login URL, session exchange, margins.

    Mixed into UnifiedTradingEngine; relies on its shared state (positions, orders_history, ...).
    """

    @property
    def kite_client(self):
        """Exposes underlying KiteConnect client for backward compatibility."""
        return self.kite_engine.kite_client

    @kite_client.setter
    def kite_client(self, client):
        self.kite_engine.kite_client = client

    def _init_kite(self) -> None:
        """Initializes or re-initializes Zerodha KiteConnect instance on kite_engine."""
        self.kite_engine.api_key = self.api_key
        self.kite_engine.api_secret = self.api_secret
        self.kite_engine.access_token = self.access_token
        self.kite_engine._init_kite()

    def load_credentials(self) -> None:
        """Loads Kite credentials from encrypted vault or environment settings."""
        db_key = database.get_secure_setting("KITE_API_KEY", "")
        db_secret = database.get_secure_setting("KITE_API_SECRET", "")
        db_token = database.get_secure_setting("KITE_ACCESS_TOKEN", "")
        db_mode = database.get_secure_setting("TRADING_MODE", "")

        self.api_key = db_key or settings.KITE_API_KEY
        self.api_secret = db_secret or settings.KITE_API_SECRET
        self.access_token = db_token or settings.KITE_ACCESS_TOKEN
        if db_mode in ["PAPER", "LIVE"]:
            self.mode = db_mode
            settings.TRADING_MODE = db_mode

        # Update Kite Engine credentials
        self.kite_engine.api_key = self.api_key
        self.kite_engine.api_secret = self.api_secret
        self.kite_engine.access_token = self.access_token
        self.kite_engine._init_kite()

    def verify_auth_token_now(self) -> dict[str, Any]:
        """Actively verifies system session and Kite token validity via Kite Engine."""
        return self.kite_engine.verify_session()

    def verify_outgoing_kite_request(self) -> bool:
        """Enforces pre-flight authentication checks prior to Kite outbound calls."""
        return self.kite_engine.verify_outgoing_kite_request()

    def is_authenticated(self) -> bool:
        """Returns True if Kite client is initialized, access token is set, and system session is active."""
        return bool(
            self.kite_engine.kite_client
            and self.kite_engine.access_token
            and has_active_session()
            and database.is_vault_unlocked()
        )

    def get_login_url(self) -> str:
        """Returns the Zerodha OAuth login URL for user authentication."""
        if not self.api_key:
            raise ValueError("Kite API Key is required to generate OAuth login URL.")
        if self.kite_engine.kite_client:
            return self.kite_engine.kite_client.login_url()
        return "https://kite.zerodha.com/connect/login?v=3&api_key=" + self.api_key

    def set_session(self, request_token: str) -> dict[str, Any]:
        """Exchanges Kite OAuth request token for access token and saves to encrypted vault."""
        if not self.kite_engine.kite_client or not self.api_secret:
            raise ValueError("Kite API Key and Secret are required.")
        call_start = time.time()
        log_outgoing_request("Zerodha Kite", "generate_session", {"request_token": request_token})
        try:
            session_data = self.kite_engine.kite_client.generate_session(
                request_token, api_secret=self.api_secret
            )
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_response(
                "Zerodha Kite",
                "generate_session",
                {"user_id": session_data.get("user_id"), "status": "success"},
                dur,
            )
        except Exception as e:
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_error("Zerodha Kite", "generate_session", e, dur)
            raise e

        self.access_token = session_data["access_token"]
        self.kite_engine.access_token = self.access_token
        self.kite_engine.kite_client.set_access_token(self.access_token)
        try:
            database.save_secure_setting("KITE_ACCESS_TOKEN", self.access_token)
        except Exception as e:
            logger.warning(f"Could not persist access token to vault: {e}")
        return session_data

    def get_kite_margins(self) -> dict[str, Any]:
        """
        Retrieves formatted Zerodha Kite account margins including available balance and utilised funds.

        Returns:
            Dict with 'connected', 'equity', 'commodity', 'timestamp', and optional 'error'.
        """
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        if not self.is_authenticated():
            return {
                "connected": False,
                "error": "Zerodha Kite is not connected or daily session is inactive.",
                "timestamp": now_iso,
            }

        try:
            raw_margins = self.kite_engine.get_margins()
            equity = raw_margins.get("equity", {})
            equity_avail = equity.get("available", {})
            equity_util = equity.get("utilised", {})

            # Zerodha live_balance represents real usable intraday cash
            available_cash = float(equity_avail.get("live_balance", equity_avail.get("cash", 0.0)) or 0.0)
            total_net = float(equity.get("net", available_cash) or available_cash)
            utilised_margin = float(equity_util.get("debits", 0.0) or 0.0)
            opening_bal = float(equity_avail.get("opening_balance", 0.0) or 0.0)

            commodity = raw_margins.get("commodity", {})
            comm_avail = commodity.get("available", {})
            comm_util = commodity.get("utilised", {})
            comm_available_cash = float(comm_avail.get("live_balance", comm_avail.get("cash", 0.0)) or 0.0)

            result = {
                "connected": True,
                "equity": {
                    "net": round(total_net, 2),
                    "available_cash": round(available_cash, 2),
                    "available_margin": round(available_cash, 2),
                    "utilised": round(utilised_margin, 2),
                    "opening_balance": round(opening_bal, 2),
                },
                "commodity": {
                    "enabled": bool(commodity.get("enabled", False)),
                    "net": round(float(commodity.get("net", 0.0) or 0.0), 2),
                    "available_cash": round(comm_available_cash, 2),
                    "utilised": round(float(comm_util.get("debits", 0.0) or 0.0), 2),
                },
                "timestamp": now_iso,
            }
            self._last_kite_margins = result
            return result
        except Exception as e:
            logger.error(f"Failed to fetch Kite margins: {e}")
            return {"connected": False, "error": str(e), "timestamp": now_iso}
