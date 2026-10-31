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
import threading
import time
import uuid
from typing import Any

from app.core.config import settings
from app.core.interfaces import OrderStatus
from app.db import database
from app.strategy.trade_validation import validate_signal
from app.trading.kite_broker import KiteExecutionEngine
from app.trading.monitor import PositionMonitorMixin
from app.trading.paper_executor import PaperExecutionEngine
from app.trading.reconciliation import ReconciliationMixin
from app.trading.risk import RiskMixin
from app.trading.session import BrokerSessionMixin

logger = logging.getLogger(__name__)


class UnifiedTradingEngine(RiskMixin, BrokerSessionMixin, ReconciliationMixin, PositionMonitorMixin):
    """
    Unified Trading Orchestrator & Portfolio Strategy Facade.

    Responsibilities:
        - Orchestrates execution strategy routing between Paper Sandbox and Live Kite broker.
        - Manages pending proposals with strict 60-second human approval countdowns.
        - Recalculates real-time mark-to-market P&L and option delta adjustments.
        - Evaluates dynamic Stop-Loss and Take-Profit triggers for automatic square-off.
        - Provides backward-compatible interface (UnifiedTradingEngine) for API and tests.

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

    MAX_ENTRY_DRIFT_PCT_EQUITY = 1.0
    MAX_ENTRY_DRIFT_PCT_OPTION = 5.0

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


# Singleton instance
trading_engine = UnifiedTradingEngine()
