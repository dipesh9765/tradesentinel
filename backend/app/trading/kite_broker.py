"""Zerodha KiteConnect order-execution adapter (implements BaseOrderExecutor)."""

import datetime
import logging
import re
import time
from typing import Any

from app.core.config import get_tradingsymbol_map
from app.core.interfaces import BaseOrderExecutor
from app.core.security import has_active_session
from app.core.server_logger import log_outgoing_error, log_outgoing_request, log_outgoing_response
from app.db import database
from app.strategy.trade_validation import is_option_instrument

logger = logging.getLogger(__name__)


class KiteExecutionEngine(BaseOrderExecutor):
    """
    Production-Grade Zerodha Kite Connect Execution Adapter.

    Responsibilities:
        - Implements BaseOrderExecutor to encapsulate all Zerodha KiteConnect SDK communications.
        - Enforces the mandatory 30-second token re-validation heartbeat before outbound dispatch.
        - Sanitizes instrument identifiers across NSE Equity and NFO Derivatives.
        - Dispatches regular MIS Intraday market orders and polls Kite order history for fill prices.

    Extends:
        core.interfaces.BaseOrderExecutor

    Uses:
        - kiteconnect.KiteConnect: Official Zerodha SDK client.
        - security.has_active_session: Global session token validator.
        - database: SQLite encrypted vault reader and order/position persistence.
        - server_logger: 3MB rotating log tracing with credential redaction.
    """

    def __init__(self, api_key: str = "", api_secret: str = "", access_token: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.kite_client: Any = None
        self._nfo_cache: dict[str, Any] = {"date": None, "rows": []}

        # 30-Second token verification tracking state
        self._last_token_verification_time: float = 0.0
        self._token_verification_interval: float = 30.0  # Exactly 30 seconds
        self._is_token_verified: bool = False
        self._last_verification_error: str | None = None

        self._init_kite()

    @property
    def mode(self) -> str:
        """Returns the operational execution mode ('LIVE')."""
        return "LIVE"

    def _init_kite(self) -> None:
        """
        Initializes the underlying Zerodha KiteConnect client instance.

        Configures API key and binds access token if available.
        """
        if self.api_key:
            try:
                from kiteconnect import KiteConnect

                self.kite_client = KiteConnect(api_key=self.api_key)
                if self.access_token:
                    self.kite_client.set_access_token(self.access_token)
                    logger.info("Zerodha KiteConnect client successfully initialized with access token.")
            except Exception as e:
                logger.error(f"Failed to initialize Zerodha KiteConnect client: {e}")

    # -------------------------------------------------------------------------
    # Authentication & Heartbeat Verification (SRP decomposed)
    # -------------------------------------------------------------------------

    def _check_system_session(self) -> str | None:
        """Validates that an active, authenticated user session exists in the system."""
        if not has_active_session():
            return "No active authenticated user session exists in system."
        return None

    def _check_vault_unlocked(self) -> str | None:
        """Validates that the master security vault is currently unlocked."""
        if not database.is_vault_unlocked():
            return "Master security vault is locked."
        return None

    def _check_client_configured(self) -> str | None:
        """Validates that Kite access token is present and client is initialized."""
        if not self.access_token or not self.kite_client:
            return "Kite access token missing or client uninitialized."
        return None

    def _verify_remote_kite_session(self, now: float) -> dict[str, Any]:
        """
        Sends an active profile ping to Zerodha Kite servers to confirm token validity.

        Args:
            now: Current epoch timestamp in seconds.

        Returns:
            Dict containing verification status and error/warning details.
        """
        call_start = time.time()
        log_outgoing_request("Zerodha Kite", "profile", {})
        try:
            profile_data = self.kite_client.profile()
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_response(
                "Zerodha Kite", "profile", {"user_id": profile_data.get("user_id"), "status": "active"}, dur
            )
            self._is_token_verified = True
            self._last_verification_error = None
            self._last_token_verification_time = now
            logger.info("30s Verification SUCCESS: System session and Kite token are verified and valid.")
            return {"valid": True, "error": None, "timestamp": now}
        except Exception as e:
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_error("Zerodha Kite", "profile", e, dur)
            err_msg = str(e)
            logger.warning(f"30s Kite token verification check error: {err_msg}")

            if "TokenException" in type(e).__name__ or "403" in err_msg or "401" in err_msg:
                self._is_token_verified = False
                self._last_verification_error = f"Kite token expired/invalid: {err_msg}"
                return {"valid": False, "error": self._last_verification_error, "timestamp": now}

            # Non-auth network glitch, but local session remains valid
            self._last_token_verification_time = now
            self._is_token_verified = True
            return {"valid": True, "warning": err_msg, "timestamp": now}

    def verify_session(self) -> dict[str, Any]:
        """
        Actively verifies system authentication state and Kite token validity.

        Decomposes verification into:
        1. Local session check
        2. Security vault unlock check
        3. Token presence check
        4. Remote Kite server profile handshake

        Returns:
            Dict containing 'valid' (bool), 'error' (Optional[str]), and 'timestamp' (float).
        """
        now = time.time()

        # Step 1: System Level Session Check
        session_err = self._check_system_session()
        if session_err:
            self._is_token_verified = False
            self._last_verification_error = session_err
            logger.warning(f"30s Check: {session_err}")
            return {"valid": False, "error": session_err, "timestamp": now}

        # Step 2: Vault Level Check
        vault_err = self._check_vault_unlocked()
        if vault_err:
            self._is_token_verified = False
            self._last_verification_error = vault_err
            logger.warning(f"30s Check: {vault_err}")
            return {"valid": False, "error": vault_err, "timestamp": now}

        # Step 3: Client & Token Presence Check
        client_err = self._check_client_configured()
        if client_err:
            self._is_token_verified = False
            self._last_verification_error = client_err
            return {"valid": False, "error": client_err, "timestamp": now}

        # Step 4: Active Remote Kite Ping
        return self._verify_remote_kite_session(now)

    def verify_outgoing_kite_request(self) -> bool:
        """
        CRITICAL SECURITY GUARD: Pre-flight validator called before EVERY outbound Kite request.

        Authenticates first whether the active user session exists and vault is unlocked.
        Every 30 seconds, actively re-verifies that the request authentication token is valid.

        Returns:
            bool: True if pre-flight verification succeeds.

        Raises:
            PermissionError: If active user session is missing, vault is locked, or token check fails.
        """
        if not has_active_session():
            raise PermissionError(
                "Outgoing Kite request BLOCKED: No active authenticated system session exists."
            )

        if not database.is_vault_unlocked():
            raise PermissionError("Outgoing Kite request BLOCKED: Master security vault is locked.")

        now = time.time()
        if (now - self._last_token_verification_time) >= self._token_verification_interval:
            verif = self.verify_session()
            if not verif["valid"]:
                raise PermissionError(
                    f"Outgoing Kite request BLOCKED: 30s token verification failed - {verif.get('error')}"
                )

        return True

    def get_margins(self) -> dict[str, Any]:
        """
        Fetches authentic account margins and balance from Zerodha Kite.

        Returns:
            Dict containing raw margin dictionary from Zerodha Kite Connect.
        """
        self.verify_outgoing_kite_request()
        if not self.kite_client:
            raise ValueError("KiteConnect client is not initialized.")

        call_start = time.time()
        log_outgoing_request("Zerodha Kite", "margins", {})
        try:
            margins_data = self.kite_client.margins()
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_response(
                "Zerodha Kite",
                "margins",
                {
                    "status": "success",
                    "equity_enabled": bool(margins_data.get("equity", {}).get("enabled", False)),
                },
                dur,
            )
            return margins_data
        except Exception as e:
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_error("Zerodha Kite", "margins", e, dur)
            raise e

    # -------------------------------------------------------------------------

    # Order Execution Pipeline (SRP decomposed)
    # -------------------------------------------------------------------------

    def _prepare_order_parameters(
        self, proposal: dict[str, Any], lot_size: int
    ) -> tuple[dict[str, Any], str, str]:
        """
        Prepares and sanitizes Kite order parameters according to exchange conventions.

        Options are resolved to a real NFO contract (exact tradingsymbol, true lot size), and the
        order quantity is lots x contract lot size. Prices are rounded to the 0.05 tick.

        Returns:
            Tuple of (order_params_dict, clean_tradingsymbol, exchange_str).
        """
        trans_type = (
            self.kite_client.TRANSACTION_TYPE_BUY
            if "BUY" in proposal["signal_type"]
            else self.kite_client.TRANSACTION_TYPE_SELL
        )

        raw_inst = proposal.get("instrument", "")
        quantity = lot_size
        if is_option_instrument(raw_inst):
            exchange = self.kite_client.EXCHANGE_NFO
            contract = self.resolve_nfo_contract(raw_inst)
            clean_tradingsymbol = contract["tradingsymbol"]
            quantity = lot_size * contract["lot_size"]
        else:
            exchange = self.kite_client.EXCHANGE_NSE
            clean_tradingsymbol = raw_inst.replace(" MIS", "").replace(" CNC", "").replace(" EQ", "").strip()
            if proposal.get("symbol"):
                sym = proposal["symbol"].strip()
                clean_tradingsymbol = get_tradingsymbol_map().get(sym, sym)

        order_params = {
            "variety": self.kite_client.VARIETY_REGULAR,
            "exchange": exchange,
            "tradingsymbol": clean_tradingsymbol,
            "transaction_type": trans_type,
            "quantity": quantity,
            "product": self.kite_client.PRODUCT_MIS,
            "order_type": self.kite_client.ORDER_TYPE_LIMIT,
            "price": self._round_tick(float(proposal.get("entry_price", 0))),
            "tag": "KPENTRY",
        }
        return order_params, clean_tradingsymbol, exchange

    def _dispatch_kite_order(
        self, order_params: dict[str, Any], fallback_limit_price: float | None = None
    ) -> str:
        """
        Dispatches the prepared order to Zerodha Kite Connect with telemetry logging
        and automatic LIMIT order fallback if market protection is enforced.

        Args:
            order_params: Sanitized KiteConnect order parameter dictionary.
            fallback_limit_price: Optional limit price fallback if market orders are restricted.

        Returns:
            str: Broker-assigned order identifier.

        Raises:
            Exception: If order placement encounters an irrecoverable broker failure.
        """
        call_start = time.time()
        log_outgoing_request("Zerodha Kite", "place_order", order_params)
        try:
            order_id = self.kite_client.place_order(**order_params)
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_response("Zerodha Kite", "place_order", {"order_id": str(order_id)}, dur)
            return str(order_id)
        except Exception as pe_err:
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_error("Zerodha Kite", "place_order", pe_err, dur)

            err_msg = str(pe_err).lower()
            if (
                ("market protection" in err_msg or "limit order" in err_msg)
                and fallback_limit_price
                and fallback_limit_price > 0
            ):
                logger.info(
                    f"Retrying Zerodha order as LIMIT @ ₹{fallback_limit_price} due to market order restrictions..."
                )
                fallback_params = dict(order_params)
                fallback_params["order_type"] = self.kite_client.ORDER_TYPE_LIMIT
                fallback_params["price"] = self._round_tick(fallback_limit_price)
                fallback_params.pop("market_protection", None)

                retry_start = time.time()
                log_outgoing_request("Zerodha Kite", "place_order (LIMIT fallback)", fallback_params)
                try:
                    order_id = self.kite_client.place_order(**fallback_params)
                    retry_dur = round((time.time() - retry_start) * 1000, 2)
                    log_outgoing_response(
                        "Zerodha Kite", "place_order (LIMIT fallback)", {"order_id": str(order_id)}, retry_dur
                    )
                    return str(order_id)
                except Exception as retry_err:
                    retry_dur = round((time.time() - retry_start) * 1000, 2)
                    log_outgoing_error("Zerodha Kite", "place_order (LIMIT fallback)", retry_err, retry_dur)
                    raise retry_err

            raise pe_err

    def _reconcile_order_fill(self, order_id: str, default_price: float) -> tuple[str, str, float]:
        """
        Queries Kite order history to determine actual broker status and average fill price.

        Args:
            order_id: Broker order identifier.
            default_price: Fallback entry price from proposal.

        Returns:
            Tuple of (kite_status_str, status_message_str, filled_price_float).
        """
        kite_status = "SUBMITTED"
        status_message = "Order submitted to Zerodha Kite"
        filled_price = default_price

        try:
            h_start = time.time()
            log_outgoing_request("Zerodha Kite", "order_history", {"order_id": order_id})
            history = self.kite_client.order_history(order_id)
            h_dur = round((time.time() - h_start) * 1000, 2)
            log_outgoing_response(
                "Zerodha Kite", "order_history", {"records_count": len(history) if history else 0}, h_dur
            )
            if history:
                latest = history[-1]
                kite_status = latest.get("status", "SUBMITTED")
                status_message = latest.get("status_message") or f"Kite status: {kite_status}"
                if latest.get("average_price") and float(latest.get("average_price")) > 0:
                    filled_price = float(latest["average_price"])
        except Exception as he:
            logger.warning(f"Could not fetch order history from Kite: {he}")

        return kite_status, status_message, filled_price

    def _record_executed_order(
        self,
        order_id: str,
        proposal: dict[str, Any],
        lot_size: int,
        filled_price: float,
        kite_status: str,
        status_message: str,
    ) -> dict[str, Any]:
        """Constructs an immutable order audit record and persists it to SQLite."""
        order_record = {
            "order_id": order_id,
            "instrument": proposal["instrument"],
            "type": "BUY" if "BUY" in proposal["signal_type"] else "SELL",
            "quantity": lot_size,
            "price": filled_price,
            "status": kite_status,
            "status_message": status_message,
            "mode": "LIVE",
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        }
        database.save_order(order_record, proposal.get("proposal_id"))
        return order_record

    def _record_live_position(
        self,
        order_id: str,
        proposal: dict[str, Any],
        lot_size: int,
        filled_price: float,
        broker_symbol: str = "",
        exchange: str = "",
    ) -> dict[str, Any]:
        """Constructs a tracked live position record and persists it to SQLite."""
        pos_id = f"POS-LIVE-{order_id[-6:]}"
        position = {
            "position_id": pos_id,
            "proposal_id": proposal.get("proposal_id"),
            "order_id": order_id,
            "symbol": proposal["symbol"],
            "instrument": proposal["instrument"],
            "signal_type": proposal["signal_type"],
            "quantity": lot_size,
            "buy_price": filled_price,
            "current_ltp": filled_price,
            "stop_loss": float(proposal["stop_loss"]),
            "target_1": float(proposal["target_1"]),
            "target_2": float(proposal["target_2"]),
            "unrealized_pnl": 0.0,
            "pnl_pct": 0.0,
            "opened_at": datetime.datetime.now().strftime("%H:%M:%S"),
            "status": "OPEN",
            "mode": "LIVE",
            "broker_symbol": broker_symbol,
            "exchange": exchange,
            "sl_order_id": None,
            "exit_order_id": None,
        }
        database.save_position(position)
        return position

    # -------------------------------------------------------------------------
    # Live order lifecycle: contract resolution, fills, protective stop, exits
    # -------------------------------------------------------------------------

    TERMINAL_STATUSES = ("COMPLETE", "REJECTED", "CANCELLED")
    ENTRY_FILL_TIMEOUT = 8.0
    EXIT_FILL_TIMEOUT = 10.0
    STOP_LIMIT_BUFFER_PCT = 0.03  # SL order limit price sits 3% beyond the trigger so it fills

    @staticmethod
    def _round_tick(price: float) -> float:
        """Rounds to the NSE 0.05 tick size, which Kite requires for prices and triggers."""
        return round(round(float(price) / 0.05) * 0.05, 2)

    def resolve_nfo_contract(self, label: str) -> dict[str, Any]:
        """
        Maps a display label like 'BANKNIFTY 52000 CE' to a real tradable NFO contract
        (nearest non-expired expiry) with its exchange tradingsymbol and true lot size.
        """
        m = re.match(r"^\s*([A-Za-z&-]+)\s+(\d+(?:\.\d+)?)\s*(CE|PE)\s*$", label or "")
        if not m:
            raise ValueError(
                f"Cannot parse option instrument '{label}' (expected e.g. 'BANKNIFTY 52000 CE')."
            )
        name, strike, opt_type = m.group(1).upper(), float(m.group(2)), m.group(3)

        today = datetime.date.today()
        if self._nfo_cache.get("date") != today:
            self.verify_outgoing_kite_request()
            self._nfo_cache = {"date": today, "rows": self.kite_client.instruments("NFO")}

        def as_date(value):
            return value.date() if isinstance(value, datetime.datetime) else value

        candidates = [
            r
            for r in self._nfo_cache["rows"]
            if r.get("name") == name
            and r.get("instrument_type") == opt_type
            and float(r.get("strike", 0)) == strike
            and r.get("expiry")
            and as_date(r["expiry"]) >= today
        ]
        if not candidates:
            raise ValueError(f"No live NFO contract found for {name} {strike:g} {opt_type}.")
        nearest = min(candidates, key=lambda r: as_date(r["expiry"]))
        return {
            "tradingsymbol": nearest["tradingsymbol"],
            "lot_size": int(nearest["lot_size"]),
            "expiry": as_date(nearest["expiry"]),
        }

    def get_option_ltp(self, label: str) -> float | None:
        """Current premium of the exact contract that would be traded."""
        contract = self.resolve_nfo_contract(label)
        key = f"NFO:{contract['tradingsymbol']}"
        self.verify_outgoing_kite_request()
        data = self.kite_client.ltp([key])
        price = (data.get(key) or {}).get("last_price")
        return float(price) if price else None

    def _latest_order(self, order_id: str) -> dict[str, Any] | None:
        """Latest broker state of an order, or None if it could not be fetched."""
        try:
            history = self.kite_client.order_history(order_id)
        except Exception as e:
            logger.warning(f"Could not fetch order {order_id} from Kite: {e}")
            return None
        return history[-1] if history else None

    def _await_terminal(self, order_id: str, timeout: float, poll: float = 0.5) -> dict[str, Any] | None:
        """Polls until the order is COMPLETE/REJECTED/CANCELLED or the timeout elapses."""
        deadline = time.time() + timeout
        latest = self._latest_order(order_id)
        while (not latest or latest.get("status") not in self.TERMINAL_STATUSES) and time.time() < deadline:
            time.sleep(poll)
            latest = self._latest_order(order_id) or latest
        return latest

    def _cancel_quietly(self, order_id: str) -> None:
        try:
            self.kite_client.cancel_order(variety=self.kite_client.VARIETY_REGULAR, order_id=order_id)
        except Exception as e:
            logger.warning(f"Cancel of order {order_id} failed (may already be terminal): {e}")

    def get_order_statuses(self) -> dict[str, dict[str, Any]]:
        """All of today's orders keyed by order_id, for one-call monitoring of broker-side stops."""
        self.verify_outgoing_kite_request()
        return {str(o["order_id"]): o for o in self.kite_client.orders()}

    def _stop_prices(self, pos: dict[str, Any]) -> tuple[float, float]:
        """(trigger, limit) for the protective SL order; limit sits beyond trigger so it fills."""
        is_long = "BUY" in pos["signal_type"]
        trigger = self._round_tick(pos["stop_loss"])
        buffer = max(0.1, trigger * self.STOP_LIMIT_BUFFER_PCT)
        limit = self._round_tick(trigger - buffer if is_long else trigger + buffer)
        return trigger, max(limit, 0.05)

    def place_protective_stop(self, pos: dict[str, Any]) -> str:
        """Places a broker-side SL order so the position stays protected if this app goes offline."""
        self.verify_outgoing_kite_request()
        is_long = "BUY" in pos["signal_type"]
        trigger, limit = self._stop_prices(pos)
        params = {
            "variety": self.kite_client.VARIETY_REGULAR,
            "exchange": pos["exchange"],
            "tradingsymbol": pos["broker_symbol"],
            "transaction_type": self.kite_client.TRANSACTION_TYPE_SELL
            if is_long
            else self.kite_client.TRANSACTION_TYPE_BUY,
            "quantity": int(pos["quantity"]),
            "product": self.kite_client.PRODUCT_MIS,
            "order_type": self.kite_client.ORDER_TYPE_SL,
            "price": limit,
            "trigger_price": trigger,
            "validity": self.kite_client.VALIDITY_DAY,
            "tag": "KPSL",
        }
        return self._dispatch_kite_order(params)

    def modify_protective_stop(self, pos: dict[str, Any]) -> None:
        """Moves the broker-side stop to the position's current (trailed) stop-loss."""
        self.verify_outgoing_kite_request()
        trigger, limit = self._stop_prices(pos)
        self.kite_client.modify_order(
            variety=self.kite_client.VARIETY_REGULAR,
            order_id=pos["sl_order_id"],
            trigger_price=trigger,
            price=limit,
        )

    def exit_position(self, pos: dict[str, Any]) -> tuple[float, str]:
        """
        Sends a market square-off to the broker and returns (fill_price, order_id).
        Raises RuntimeError if the exit cannot be confirmed. Never places a second exit while
        an earlier one is still unresolved, to avoid flipping into a reverse position.
        """
        self.verify_outgoing_kite_request()
        previous = pos.get("exit_order_id")
        if previous:
            state = self._latest_order(previous)
            if state is None:
                raise RuntimeError(
                    f"Exit order {previous} status unknown; not sending another to avoid a double exit."
                )
            status = state.get("status")
            if status == "COMPLETE":
                return float(state.get("average_price") or 0.0), previous
            if status not in ("REJECTED", "CANCELLED"):
                final = self._await_terminal(previous, self.EXIT_FILL_TIMEOUT)
                if final and final.get("status") == "COMPLETE":
                    return float(final.get("average_price") or 0.0), previous
                raise RuntimeError(f"Exit order {previous} still unresolved ({(final or {}).get('status')}).")
            pos["exit_order_id"] = None

        is_long = "BUY" in pos["signal_type"]
        params = {
            "variety": self.kite_client.VARIETY_REGULAR,
            "exchange": pos["exchange"],
            "tradingsymbol": pos["broker_symbol"],
            "transaction_type": self.kite_client.TRANSACTION_TYPE_SELL
            if is_long
            else self.kite_client.TRANSACTION_TYPE_BUY,
            "quantity": int(pos["quantity"]),
            "product": self.kite_client.PRODUCT_MIS,
            "order_type": self.kite_client.ORDER_TYPE_MARKET,
            "market_protection": -1,
            "tag": "KPEXIT",
        }
        order_id = self._dispatch_kite_order(params)
        pos["exit_order_id"] = order_id
        database.update_position_in_db(pos)

        final = self._await_terminal(order_id, self.EXIT_FILL_TIMEOUT)
        final = final or {}
        status = final.get("status")
        if status == "COMPLETE":
            return float(final.get("average_price") or 0.0), order_id
        if status in ("REJECTED", "CANCELLED"):
            pos["exit_order_id"] = None
            raise RuntimeError(f"Exit order {status}: {final.get('status_message')}")
        raise RuntimeError(f"Exit order {order_id} not confirmed within {self.EXIT_FILL_TIMEOUT:.0f}s.")

    def close_live(self, pos: dict[str, Any]) -> tuple[float, str]:
        """
        Flattens a live position at the broker. If the protective stop already filled, its fill is
        used and no new order is sent; otherwise the stop is cancelled (and confirmed) before exiting.
        Returns (exit_price, order_id). Raises RuntimeError if the position could not be flattened.
        """
        sl_id = pos.get("sl_order_id")
        if sl_id:
            state = self._latest_order(sl_id) or {}
            status = state.get("status")
            if status == "COMPLETE":
                return float(state.get("average_price") or 0.0), sl_id
            if status not in ("CANCELLED", "REJECTED"):
                self._cancel_quietly(sl_id)
                final = self._await_terminal(sl_id, 5.0) or {}
                fstatus = final.get("status")
                if fstatus == "COMPLETE":
                    return float(final.get("average_price") or 0.0), sl_id
                if fstatus not in ("CANCELLED", "REJECTED"):
                    raise RuntimeError(
                        "Could not confirm the protective stop is cancelled; refusing to exit to avoid a double sell."
                    )
            pos["sl_order_id"] = None
        return self.exit_position(pos)

    def execute_order(self, proposal: dict[str, Any], lot_size: int) -> dict[str, Any]:
        """
        Live MIS entry on Zerodha Kite.

        Workflow:
            1. Verify auth/heartbeat, resolve the real contract and quantity.
            2. Place a LIMIT entry at the approved price and wait for the fill.
            3. If unfilled in time, cancel it (no surprise late fills) and report no position.
            4. On a fill, immediately place a broker-side protective stop. If that fails, flatten
               the position at once rather than leave it unprotected.
        """
        self.verify_outgoing_kite_request()
        try:
            order_params, tradingsymbol, exchange = self._prepare_order_parameters(proposal, lot_size)
            quantity = int(order_params["quantity"])
            default_entry = float(proposal["entry_price"])

            order_id = self._dispatch_kite_order(order_params, fallback_limit_price=default_entry)

            latest = self._await_terminal(order_id, self.ENTRY_FILL_TIMEOUT)
            if not latest or latest.get("status") not in self.TERMINAL_STATUSES:
                self._cancel_quietly(order_id)
                latest = self._await_terminal(order_id, 3.0) or latest or {}
            kite_status = latest.get("status", "UNKNOWN")
            status_message = latest.get("status_message") or f"Kite status: {kite_status}"
            filled_qty = int(latest.get("filled_quantity") or 0)
            avg_price = float(latest.get("average_price") or 0.0)
            filled_price = avg_price if avg_price > 0 else default_entry

            order_record = self._record_executed_order(
                order_id, proposal, filled_qty or quantity, filled_price, kite_status, status_message
            )

            if filled_qty <= 0:
                return {
                    "order": order_record,
                    "rejected": True,
                    "status": kite_status,
                    "mode": "LIVE",
                    "message": f"Entry not filled ({kite_status}); order cancelled, no position opened. {status_message}",
                }

            position = self._record_live_position(
                order_id, proposal, filled_qty, filled_price, tradingsymbol, exchange
            )

            try:
                position["sl_order_id"] = self.place_protective_stop(position)
                position["sl_trigger_synced"] = position["stop_loss"]
                database.update_position_in_db(position)
            except Exception as stop_err:
                logger.critical(
                    f"Protective stop FAILED for {tradingsymbol}: {stop_err}. Flattening position."
                )
                try:
                    exit_price, _ = self.exit_position(position)
                    position["status"] = "CLOSED"
                    position["exit_price"] = exit_price
                    position["close_reason"] = "PROTECTIVE_STOP_FAILED"
                    position["closed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    database.update_position_in_db(position)
                    return {
                        "order": order_record,
                        "rejected": True,
                        "status": "REJECTED",
                        "mode": "LIVE",
                        "message": f"Entry filled but the protective stop could not be placed ({stop_err}); position was flattened for safety.",
                    }
                except Exception as exit_err:
                    logger.critical(
                        f"EMERGENCY EXIT FAILED for {tradingsymbol}: {exit_err}. Position is UNPROTECTED at broker."
                    )
                    return {
                        "order": order_record,
                        "position": position,
                        "status": kite_status,
                        "mode": "LIVE",
                        "message": f"WARNING: position is open WITHOUT a broker stop ({stop_err}); exit also failed ({exit_err}). Close it manually in Kite now.",
                    }

            return {
                "order": order_record,
                "position": position,
                "status": kite_status,
                "mode": "LIVE",
                "message": f"Order filled on Zerodha Kite (#{order_id}) with broker-side stop-loss #{position['sl_order_id']}.",
            }
        except Exception as e:
            logger.error(f"Live Kite order placement failed: {e}")
            err_str = str(e)
            if "After Market Order" in err_str or "AMO" in err_str or "market is closed" in err_str.lower():
                raise RuntimeError(
                    "Market is currently closed. Live Intraday (MIS) orders on Zerodha can only be placed during market hours (09:15 AM - 03:30 PM IST). You can switch to Paper Trading mode in Settings to test anytime."
                ) from e
            raise RuntimeError(f"Kite order failed: {err_str}") from e

    def close_position(self, position_id: str, reason: str = "MANUAL_EXIT") -> dict[str, Any]:
        """Interface stub: live exits go through UnifiedTradingEngine.close_position -> close_live."""
        self.verify_outgoing_kite_request()
        return {"position_id": position_id, "reason": reason, "mode": "LIVE"}
