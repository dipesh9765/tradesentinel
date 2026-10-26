"""
TradeSentinel - Trading Execution Engine & Broker Abstraction Layer

This module provides the core execution layer for TradeSentinel, adhering to SOLID principles,
the Strategy Pattern, and the Adapter Pattern. It cleanly separates low-level broker execution
(Zerodha KiteConnect SDK) from virtual sandbox execution (Paper Engine), orchestrated through
a unified trading engine facade.

SOLID Architectural Principles Applied:
- Single Responsibility Principle (SRP): Each class and helper method encapsulates exactly one
  domain responsibility (e.g. order preparation, network dispatch, fill reconciliation, state persistence).
- Open/Closed Principle (OCP): New broker adapters (e.g., Angel One, Dhan, Upstox) can implement
  BaseOrderExecutor without modifying the orchestrator.
- Liskov Substitution Principle (LSP): Both KiteExecutionEngine and PaperExecutionEngine fully
  honor the BaseOrderExecutor contract.
- Interface Segregation Principle (ISP): Clean, minimal interfaces defined in core.interfaces.
- Dependency Inversion Principle (DIP): High-level trading orchestration depends on abstract base
  classes rather than concrete broker implementations.
"""

import datetime
import logging
import re
import threading
import time
import uuid
from typing import Any

import database
from config import get_tradingsymbol_map, settings
from core.interfaces import BaseOrderExecutor, OrderStatus
from core.paper_executor import PaperExecutionEngine
from exit_rules import check_exit_triggers
from security import has_active_session
from server_logger import log_outgoing_error, log_outgoing_request, log_outgoing_response
from trade_validation import is_option_instrument, validate_signal

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
        self.kite_client = None
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
        status = (final or {}).get("status")
        if status == "COMPLETE":
            return float(final.get("average_price") or 0.0), order_id
        if status in ("REJECTED", "CANCELLED"):
            pos["exit_order_id"] = None
            raise RuntimeError(f"Exit order {status}: {(final or {}).get('status_message')}")
        raise RuntimeError(f"Exit order {order_id} not confirmed within {self.EXIT_FILL_TIMEOUT:.0f}s.")

    def close_live(self, pos: dict[str, Any]) -> tuple[float, str]:
        """
        Flattens a live position at the broker. If the protective stop already filled, its fill is
        used and no new order is sent; otherwise the stop is cancelled (and confirmed) before exiting.
        Returns (exit_price, order_id). Raises RuntimeError if the position could not be flattened.
        """
        sl_id = pos.get("sl_order_id")
        if sl_id:
            state = self._latest_order(sl_id)
            status = (state or {}).get("status")
            if status == "COMPLETE":
                return float(state.get("average_price") or 0.0), sl_id
            if status not in ("CANCELLED", "REJECTED"):
                self._cancel_quietly(sl_id)
                final = self._await_terminal(sl_id, 5.0)
                fstatus = (final or {}).get("status")
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


class UnifiedTradingEngine:
    """
    Unified Trading Orchestrator & Portfolio Strategy Facade.

    Responsibilities:
        - Orchestrates execution strategy routing between Paper Sandbox and Live Kite broker.
        - Manages pending proposals with strict 60-second human approval countdowns.
        - Recalculates real-time mark-to-market P&L and option delta adjustments.
        - Evaluates dynamic Stop-Loss and Take-Profit triggers for automatic square-off.
        - Provides backward-compatible interface (KiteTradingExecutor) for API and tests.

    Extends:
        Acts as a Strategy Facade coordinating BaseOrderExecutor implementations.

    Uses:
        - PaperExecutionEngine: Virtual portfolio sandbox engine.
        - KiteExecutionEngine: Production Zerodha broker engine.
        - database: Persistent SQLite storage for orders, positions, and suggestions.
        - config.settings: Application-wide parameters and lot size guardrails.
    """

    def __init__(self):
        self.mode: str = settings.TRADING_MODE  # "PAPER" or "LIVE"
        self.api_key: str = ""
        self.api_secret: str = ""
        self.access_token: str = ""

        # Sub-engines
        self.paper_engine = PaperExecutionEngine(initial_balance=settings.INITIAL_PAPER_CAPITAL)
        self.kite_engine = KiteExecutionEngine()

        # Shared portfolio state
        self.positions: dict[str, dict[str, Any]] = {}
        self.orders_history: list[dict[str, Any]] = []
        self.pending_proposals: dict[str, dict[str, Any]] = {}
        self.last_loss_times: dict[str, datetime.datetime] = {}
        self._last_kite_margins: dict[str, Any] | None = None
        self._lock = threading.RLock()  # serialises approvals/closes so one exit order is ever in flight

        self.load_credentials()
        self.load_open_positions()

    def is_in_loss_lockout(self, symbol: str, cooldown_minutes: int = 45) -> tuple[bool, int]:
        """Checks whether symbol is in a mandatory loss lockout cooldown after a stop-loss hit."""
        last_time = self.last_loss_times.get(symbol)
        if not last_time:
            return False, 0
        elapsed = (datetime.datetime.now() - last_time).total_seconds() / 60.0
        if elapsed < cooldown_minutes:
            remaining = int(cooldown_minutes - elapsed)
            return True, remaining
        return False, 0

    def auto_square_off_mis_positions(self) -> list[dict[str, Any]]:
        """
        Executes automated square-off for all open MIS positions at 15:15 IST
        to protect against Zerodha RMS penalty charges (₹50+GST) at 15:20 IST.
        """
        closed_records = []
        for pid, pos in list(self.positions.items()):
            if pos.get("status") == "OPEN":
                rec = self.close_position(pid, reason="INTRADAY_AUTO_SQUAREOFF_1515")
                closed_records.append(rec)
                logger.warning(
                    f"Auto-squared off open position {pid} ({pos.get('instrument')}) for 15:15 IST protection."
                )
        return closed_records

    # -------------------------------------------------------------------------
    # Backward Compatibility Properties & Delegates
    # -------------------------------------------------------------------------

    @property
    def paper_balance(self) -> float:
        """Exposes paper balance for backward compatibility."""
        return self.paper_engine.paper_balance

    @paper_balance.setter
    def paper_balance(self, value: float) -> None:
        self.paper_engine.paper_balance = value

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

    # -------------------------------------------------------------------------
    # State Synchronization & Credentials
    # -------------------------------------------------------------------------

    def load_open_positions(self) -> None:
        """Restores any active open positions from the persistent SQLite database."""
        try:
            open_pos = database.get_open_positions_from_db()
            for pid, pos in open_pos.items():
                if pid not in self.positions:
                    self.positions[pid] = pos
                    if pos.get("mode") == "PAPER":
                        self.paper_engine.positions[pid] = pos
            if open_pos:
                logger.info(f"Restored {len(open_pos)} active open positions from SQLite database.")
        except Exception as e:
            logger.warning(f"Could not load open positions from DB: {e}")

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

    # -------------------------------------------------------------------------

    # Proposal Lifecycle Management
    # -------------------------------------------------------------------------

    def create_trade_proposal(self, signal: dict[str, Any]) -> dict[str, Any]:
        """
        Creates a pending trade proposal awaiting human verbal or click confirmation.

        Strict Guardrail: No trade is executed until approve_trade() is explicitly called!

        Args:
            signal: Generated technical/AI trade setup.

        Returns:
            Dict containing proposal payload with 60s expiration and PENDING status.
        """
        problems = validate_signal(signal)
        if problems:
            raise ValueError("Trade signal rejected: " + " ".join(problems))

        proposal_id = str(uuid.uuid4())[:8]
        proposal = {
            "proposal_id": proposal_id,
            "symbol": signal["symbol"],
            "instrument": signal["instrument_to_trade"],
            "signal_type": signal["signal_type"],
            "direction": signal["direction"],
            "lot_size": settings.DEFAULT_LOT_SIZE,  # Strictly 1 lot
            "quantity": 1,
            "entry_price": float(signal["entry_price"]),
            "stop_loss": float(signal["stop_loss"]),
            "target_1": float(signal["target_1"]),
            "target_2": float(signal["target_2"]),
            "risk_reward": signal["risk_reward"],
            "confidence": int(signal["confidence"]),
            "verbal_pitch": signal["verbal_pitch"],
            "technical_rationale": signal["technical_rationale"],
            "status": OrderStatus.PENDING_APPROVAL,
            "created_at": datetime.datetime.now().strftime("%H:%M:%S"),
            "expires_in_seconds": 60,
            "created_ts": time.time(),
        }
        self.pending_proposals[proposal_id] = proposal
        database.save_suggestion(proposal)
        return proposal

    PROPOSAL_EXPIRY_GRACE_SECONDS = 5

    def _check_trading_limits(self) -> None:
        """
        Discipline limits, counted from the database so they survive restarts:
        a cap on trades per day and a timed pause after a streak of consecutive losses.
        """
        today = datetime.date.today().strftime("%Y-%m-%d")
        closed = database.get_closed_positions_on(today, self.mode)
        open_count = sum(1 for p in self.positions.values() if p.get("mode", "PAPER") == self.mode)

        if len(closed) + open_count >= settings.MAX_TRADES_PER_DAY:
            raise ValueError(
                f"Daily trade limit reached ({settings.MAX_TRADES_PER_DAY} trades today). "
                "No more entries until tomorrow; overtrading is the fastest way to lose money."
            )

        streak = 0
        for row in closed:
            if (row.get("realized_pnl") or 0.0) < 0:
                streak += 1
            else:
                break
        if streak >= settings.MAX_CONSECUTIVE_LOSSES and closed:
            try:
                last_close = datetime.datetime.strptime(closed[0]["closed_at"], "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                last_close = datetime.datetime.now()
            pause = datetime.timedelta(minutes=settings.LOSS_STREAK_PAUSE_MINUTES)
            resume_at = last_close + pause
            if datetime.datetime.now() < resume_at:
                raise ValueError(
                    f"Trading paused after {streak} consecutive losses. "
                    f"New entries resume at {resume_at.strftime('%H:%M')}. Use the time to review, not to chase."
                )

    MAX_ENTRY_DRIFT_PCT_EQUITY = 1.0
    MAX_ENTRY_DRIFT_PCT_OPTION = 5.0

    def _check_entry_drift(self, proposal: dict[str, Any]) -> None:
        """Blocks the trade if the instrument's price has moved too far from the proposed entry."""
        expected = float(proposal.get("entry_price") or 0.0)
        if expected <= 0:
            return
        is_option = is_option_instrument(proposal["instrument"])
        live = self.mode == "LIVE"

        if is_option:
            if not live:
                return  # no option quotes in paper mode
            current = self.kite_engine.get_option_ltp(proposal["instrument"])
            limit = self.MAX_ENTRY_DRIFT_PCT_OPTION
        else:
            from market_data import market_data_manager

            current = float(market_data_manager.get_quote(proposal["symbol"]).get("ltp") or 0.0)
            limit = self.MAX_ENTRY_DRIFT_PCT_EQUITY

        if not current or current <= 0:
            if live:
                raise ValueError(
                    "Cannot verify the current price of the instrument; trade blocked for safety."
                )
            return

        drift_pct = abs(current - expected) / expected * 100.0
        if drift_pct > limit:
            raise ValueError(
                f"Slippage guard: price moved {drift_pct:.2f}% from the proposed entry "
                f"(\u20b9{expected} \u2192 \u20b9{current}, limit {limit}%). Scan again for a fresh setup."
            )

    def approve_trade(self, proposal_id: str) -> dict[str, Any]:
        """
        Processes human trade confirmation ('Approve' click or voice command).
        Routes order to either Zerodha Kite (LIVE) or Paper Sandbox (PAPER).

        Guards (all enforced server-side): proposal not expired, daily loss circuit breaker,
        price has not drifted from the proposed entry, and LIVE mode never silently falls back to paper.
        """
        with self._lock:
            proposal = self.pending_proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Trade proposal {proposal_id} not found or expired.")

            if proposal["status"] != OrderStatus.PENDING_APPROVAL:
                raise ValueError(f"Proposal {proposal_id} already processed: {proposal['status']}")

            age = time.time() - float(proposal.get("created_ts", time.time()))
            if age > proposal.get("expires_in_seconds", 60) + self.PROPOSAL_EXPIRY_GRACE_SECONDS:
                proposal["status"] = "EXPIRED"
                database.update_suggestion_status(proposal_id, "EXPIRED")
                raise ValueError(
                    f"Proposal {proposal_id} expired ({int(age)}s old). Scan again for a fresh setup."
                )

            summary = self.get_portfolio_summary()
            daily_pnl = summary.get("total_pnl", 0.0)
            max_daily_loss = float(settings.MAX_DAILY_LOSS)
            if daily_pnl <= -max_daily_loss:
                raise ValueError(
                    f"Daily Loss Circuit Breaker ACTIVATED: Total daily loss reached \u20b9{abs(daily_pnl):.2f} "
                    f"(limit: \u20b9{max_daily_loss:.2f}). To protect your capital, no new trades are allowed today."
                )

            self._check_trading_limits()
            self._check_entry_drift(proposal)

            lot_size = min(proposal.get("lot_size", 1), settings.MAX_LOT_SIZE)

            if self.mode == "LIVE":
                if not (self.kite_engine.kite_client and self.access_token):
                    raise ValueError(
                        "LIVE mode is selected but Zerodha Kite is not connected. "
                        "Refusing to fall back to paper trading silently; reconnect Kite or switch to PAPER."
                    )
                executed_trade = self.kite_engine.execute_order(proposal, lot_size)
            else:
                executed_trade = self.paper_engine.execute_order(proposal, lot_size)

            if "position" in executed_trade:
                pos = executed_trade["position"]
                self.positions[pos["position_id"]] = pos

            if "order" in executed_trade:
                self.orders_history.insert(0, executed_trade["order"])

            if executed_trade.get("rejected"):
                proposal["status"] = OrderStatus.REJECTED
                database.update_suggestion_status(proposal_id, "REJECTED")
            else:
                proposal["status"] = OrderStatus.APPROVED
                database.update_suggestion_status(proposal_id, "APPROVED")
            return executed_trade

    def reject_trade(self, proposal_id: str, reason: str = "User declined") -> dict[str, Any]:
        """Records user rejection ('Reject' click or voice command)."""
        proposal = self.pending_proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Trade proposal {proposal_id} not found.")
        proposal["status"] = OrderStatus.REJECTED
        proposal["rejection_reason"] = reason
        database.update_suggestion_status(proposal_id, "REJECTED")
        return proposal

    # -------------------------------------------------------------------------
    # Position Termination & P&L Calculation (SRP decomposed)
    # -------------------------------------------------------------------------

    def _resolve_position(self, position_id: str) -> dict[str, Any]:
        """Resolves position from active memory or falls back to SQLite database."""
        pos = self.positions.get(position_id)
        if pos:
            return pos

        db_pos = database.get_position_by_id(position_id)
        if not db_pos:
            raise ValueError(f"Position {position_id} not found in active records or database.")

        if db_pos.get("status") == "CLOSED":
            return db_pos

        self.positions[position_id] = db_pos
        return db_pos

    def _calculate_realized_pnl(self, pos: dict[str, Any], exit_price: float, quantity: int) -> float:
        """Calculates direction-aware realized Profit and Loss."""
        buy_price = float(pos.get("buy_price") or exit_price)
        signal_type = str(pos.get("signal_type") or "BUY")

        if "SHORT" in signal_type:
            return round((buy_price - exit_price) * quantity, 2)
        return round((exit_price - buy_price) * quantity, 2)

    def _persist_closed_position(
        self, pos: dict[str, Any], exit_price: float, realized_pnl: float, reason: str, closed_at: str
    ) -> None:
        """Updates position record in memory and SQLite database."""
        pos["status"] = "CLOSED"
        pos["exit_price"] = exit_price
        pos["realized_pnl"] = realized_pnl
        pos["close_reason"] = reason
        pos["closed_at"] = closed_at
        database.update_position_in_db(pos)

    def _record_exit_order(
        self, pos: dict[str, Any], exit_price: float, quantity: int, pnl: float, closed_at: str
    ) -> dict[str, Any]:
        """Creates an offsetting exit order audit record and persists it."""
        signal_type = str(pos.get("signal_type") or "BUY")
        exit_order = {
            "order_id": f"EXIT-{uuid.uuid4().hex[:6].upper()}",
            "instrument": pos.get("instrument", "UNKNOWN"),
            "type": "SELL" if "BUY" in signal_type else "BUY",
            "quantity": quantity,
            "price": exit_price,
            "status": "COMPLETED",
            "mode": pos.get("mode", "PAPER"),
            "pnl": pnl,
            "timestamp": closed_at,
        }
        self.orders_history.insert(0, exit_order)
        database.save_order(exit_order, pos.get("proposal_id"))
        return exit_order

    def _finalize_close(self, pos: dict[str, Any], exit_price: float, reason: str) -> dict[str, Any]:
        """Books a position that is already flat (paper fill or confirmed broker exit)."""
        position_id = pos["position_id"]
        quantity = int(pos.get("quantity") or 1)
        pnl = self._calculate_realized_pnl(pos, exit_price, quantity)
        if pos.get("mode") != "LIVE":
            self.paper_balance += pnl
        closed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._persist_closed_position(pos, exit_price, pnl, reason, closed_at)
        exit_order = self._record_exit_order(pos, exit_price, quantity, pnl, closed_at)

        # Single-Loss 45-Minute Lockout Tracker
        if pnl < 0 or reason == "STOP_LOSS_HIT":
            sym = pos.get("symbol")
            if sym:
                self.last_loss_times[sym] = datetime.datetime.now()
                logger.info(f"Loss recorded on {sym} ({reason}). 45-minute Loss Lockout cooldown active.")

        self.positions.pop(position_id, None)
        self.paper_engine.positions.pop(position_id, None)

        return {
            "message": "Position closed successfully",
            "pnl": pnl,
            "exit_order": exit_order,
            "position": pos,
        }

    def close_position(self, position_id: str, reason: str = "MANUAL_EXIT") -> dict[str, Any]:
        """
        Closes an active position and updates portfolio accounting.

        LIVE positions are flattened at the broker first (using the broker-side stop's fill if it
        already triggered). The position is only marked closed once the broker confirms; if the exit
        cannot be confirmed this raises and the position stays OPEN so it is retried / flagged.
        """
        with self._lock:
            pos = self._resolve_position(position_id)
            if pos.get("status") == "CLOSED":
                return {
                    "message": "Position was already closed.",
                    "pnl": pos.get("realized_pnl", 0.0),
                    "position": pos,
                }

            if pos.get("mode") == "LIVE":
                stop_id = pos.get("sl_order_id")
                try:
                    exit_price, exit_ref = self.kite_engine.close_live(pos)
                except Exception as e:
                    logger.critical(
                        f"LIVE exit for {position_id} ({pos.get('instrument')}) NOT confirmed: {e}"
                    )
                    raise RuntimeError(f"Live exit not confirmed by broker: {e}") from e
                if stop_id and exit_ref == stop_id:
                    reason = "STOP_LOSS_HIT"  # the broker-side stop fired
            else:
                exit_price = float(pos.get("current_ltp") or pos.get("buy_price") or 0.0)

            return self._finalize_close(pos, exit_price, reason)

    # -------------------------------------------------------------------------
    # Mark-to-Market & Trigger Monitoring (SRP decomposed)
    # -------------------------------------------------------------------------

    def sync_live_kite_positions(self) -> set:
        """
        In LIVE mode, fetches authentic MTM P&L and LTP from Zerodha Kite positions and returns the
        set of position ids refreshed this tick (those use the real premium, not a simulated one).
        """
        synced: set = set()
        if self.mode != "LIVE" or not self.is_authenticated():
            return synced

        try:
            self.verify_outgoing_kite_request()
            kite = self.kite_engine.kite_client
            call_start = time.time()
            log_outgoing_request("Zerodha Kite", "positions", {})
            raw_pos = kite.positions()
            dur = round((time.time() - call_start) * 1000, 2)
            log_outgoing_response(
                "Zerodha Kite", "positions", {"net_count": len(raw_pos.get("net", []))}, dur
            )

            for np_item in raw_pos.get("net", []):
                tsym = np_item.get("tradingsymbol", "")
                ltp = float(np_item.get("last_price", 0.0))
                pnl = float(np_item.get("m2m", np_item.get("pnl", 0.0)))

                for pid, pos in self.positions.items():
                    if pos.get("mode") != "LIVE" or pos.get("broker_symbol") != tsym:
                        continue
                    if ltp > 0:
                        pos["current_ltp"] = ltp
                        synced.add(pid)
                    pos["unrealized_pnl"] = round(pnl, 2)
                    buy_val = float(pos.get("buy_price", 1)) * float(pos.get("quantity", 1))
                    pos["pnl_pct"] = round((pnl / buy_val) * 100, 2) if buy_val > 0 else 0.0
                    database.update_position_in_db(pos)
        except Exception as e:
            logger.warning(f"Live Kite positions sync failed: {e}")
        return synced

    def reconcile_live_positions(self) -> dict[str, Any]:
        """
        Compares locally tracked LIVE positions with the broker's net positions.
        Local positions that are flat at the broker (e.g. the stop filled while this app was
        offline) are booked as closed; broker positions this app does not track are only reported.
        """
        if not self.is_authenticated():
            return {"checked": False, "reason": "Kite not connected."}
        with self._lock:
            self.verify_outgoing_kite_request()
            net = {
                p["tradingsymbol"]: int(p.get("quantity", 0))
                for p in self.kite_engine.kite_client.positions().get("net", [])
            }
            report: dict[str, Any] = {
                "checked": True,
                "closed_locally": [],
                "untracked_at_broker": [],
                "ok": [],
            }
            tracked = set()
            for pid, pos in list(self.positions.items()):
                if pos.get("mode") != "LIVE":
                    continue
                symbol = pos.get("broker_symbol")
                tracked.add(symbol)
                if symbol and net.get(symbol, 0) == 0:
                    exit_price = float(pos.get("current_ltp") or pos.get("buy_price") or 0.0)
                    if pos.get("sl_order_id"):
                        state = self.kite_engine._latest_order(pos["sl_order_id"])
                        if state and state.get("status") == "COMPLETE":
                            exit_price = float(state.get("average_price") or exit_price)
                    self._finalize_close(pos, exit_price, "BROKER_RECONCILED")
                    report["closed_locally"].append(pid)
                else:
                    report["ok"].append(pid)
            report["untracked_at_broker"] = [s for s, q in net.items() if q != 0 and s not in tracked]
            if report["untracked_at_broker"]:
                logger.warning(
                    f"Broker holds positions this app does not track: {report['untracked_at_broker']}"
                )
            return report

    def _calculate_effective_price(
        self, symbol: str, instrument: str, pos: dict[str, Any], live_prices: dict[str, float]
    ) -> float:
        """
        Calculates the effective instrument price.
        If instrument is directly in live_prices, returns exact quote.
        For options, models delta movement relative to the underlying's entry price.
        """
        # 1. Direct quote match
        if instrument in live_prices and live_prices[instrument] > 0:
            return live_prices[instrument]

        clean_inst = instrument.replace(" MIS", "").replace(" CNC", "").strip()
        if clean_inst in live_prices and live_prices[clean_inst] > 0:
            return live_prices[clean_inst]

        current_ltp = float(pos.get("current_ltp") or pos.get("buy_price", 0.0))
        underlying_ltp = live_prices.get(symbol)

        # 2. Options Delta Tracking
        if is_option_instrument(instrument) and underlying_ltp:
            entry_underlying = float(pos.get("underlying_entry") or underlying_ltp)
            is_call = instrument.rstrip().endswith("CE") or "BUY_CALL" in pos.get("signal_type", "")
            delta = 0.55  # Standard ATM delta
            underlying_move = (
                (underlying_ltp - entry_underlying) if is_call else (entry_underlying - underlying_ltp)
            )
            entry_price = float(pos.get("buy_price", current_ltp))
            simulated_premium = entry_price + (underlying_move * delta)
            return round(max(2.0, simulated_premium), 2)

        return live_prices.get(symbol, current_ltp)

    def _evaluate_position_pnl(self, pos: dict[str, Any], cur_price: float) -> tuple[float, float]:
        """Calculates unrealized P&L and percentage return for a position."""
        buy_price = float(pos["buy_price"])
        qty = int(pos["quantity"])

        if "BUY" in pos["signal_type"]:
            pnl = round((cur_price - buy_price) * qty, 2)
        else:
            pnl = round((buy_price - cur_price) * qty, 2)

        cost_basis = buy_price * qty
        pnl_pct = round((pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0
        return pnl, pnl_pct

    def _check_exit_triggers(self, pos: dict[str, Any], cur_price: float) -> str | None:
        """Stop-loss / target / trailing evaluation (shared with the backtester via exit_rules)."""
        return check_exit_triggers(pos, cur_price)

    def _sync_trailing_stop(self, pos: dict[str, Any]) -> None:
        """Keeps the broker-side stop in step with the software trailing stop-loss."""
        synced = pos.get("sl_trigger_synced")
        if synced is not None and abs(float(pos["stop_loss"]) - float(synced)) < 0.05:
            return
        try:
            self.kite_engine.modify_protective_stop(pos)
            pos["sl_trigger_synced"] = pos["stop_loss"]
            logger.info(f"Broker stop for {pos.get('position_id')} moved to \u20b9{pos['stop_loss']}")
        except Exception as e:
            logger.error(f"Could not move broker stop for {pos.get('position_id')}: {e}")

    def update_positions_pnl(self, live_prices: dict[str, float]) -> None:
        """
        Recalculates active positions P&L and triggers automatic Stop-Loss or Target exits.

        LIVE positions use the broker's real premium when available, notice when the broker-side
        stop has already filled, and keep that stop in step with the trailing stop-loss.
        """
        synced_ids: set = set()
        broker_orders: dict[str, dict[str, Any]] = {}
        if self.mode == "LIVE":
            synced_ids = self.sync_live_kite_positions()
            if any(p.get("sl_order_id") for p in self.positions.values()):
                try:
                    broker_orders = self.kite_engine.get_order_statuses()
                except Exception as e:
                    logger.warning(f"Could not fetch broker orders to monitor stops: {e}")

        to_close: list[tuple[str, str]] = []

        for pid, pos in list(self.positions.items()):
            symbol = pos["symbol"]
            if pid in synced_ids:
                cur_price = float(pos["current_ltp"])
            else:
                cur_price = self._calculate_effective_price(symbol, pos["instrument"], pos, live_prices)

            pos["current_ltp"] = cur_price
            pnl, pnl_pct = self._evaluate_position_pnl(pos, cur_price)
            pos["unrealized_pnl"] = pnl
            pos["pnl_pct"] = pnl_pct

            trigger_reason = self._check_exit_triggers(pos, cur_price)

            if pos.get("mode") == "LIVE" and pos.get("sl_order_id"):
                broker_stop = broker_orders.get(str(pos["sl_order_id"]))
                if broker_stop and broker_stop.get("status") == "COMPLETE":
                    trigger_reason = "STOP_LOSS_HIT"
                elif not trigger_reason:
                    self._sync_trailing_stop(pos)

            database.update_position_in_db(pos)

            if trigger_reason:
                to_close.append((pid, trigger_reason))

        for pid, reason in to_close:
            try:
                self.close_position(pid, reason)
            except Exception as e:
                logger.error(f"Auto-exit of {pid} ({reason}) failed, will retry next tick: {e}")

    def get_portfolio_summary(self) -> dict[str, Any]:
        """Returns consolidated high-level portfolio balance, P&L, and connectivity summary."""
        total_unrealized_pnl = round(sum(p["unrealized_pnl"] for p in self.positions.values()), 2)
        total_realized_pnl = round(sum(o.get("pnl", 0.0) for o in self.orders_history if "pnl" in o), 2)
        return {
            "mode": self.mode,
            "paper_balance": round(self.paper_balance + total_unrealized_pnl, 2),
            "initial_balance": settings.INITIAL_PAPER_CAPITAL,
            "unrealized_pnl": total_unrealized_pnl,
            "realized_pnl": total_realized_pnl,
            "total_pnl": round(total_unrealized_pnl + total_realized_pnl, 2),
            "open_positions_count": len(self.positions),
            "completed_orders_count": len(self.orders_history),
            "kite_connected": bool(self.access_token and self.kite_client),
            "kite_balance": self._last_kite_margins,
        }


# Export alias for 100% backward compatibility across all imports
KiteTradingExecutor = UnifiedTradingEngine

# Singleton instance
kite_executor = KiteTradingExecutor()
