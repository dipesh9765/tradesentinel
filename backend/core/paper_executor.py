"""
Paper Execution Engine - TradeSentinel

Provides an isolated, risk-free simulated execution broker adhering to SOLID principles
and the Strategy Pattern. Models realistic order fills, virtual balance management,
unrealized/realized P&L tracking, and position lifecycle without sending outbound
HTTP/WebSocket requests to actual brokerage endpoints.
"""

import datetime
import uuid
import logging
from typing import Dict, List, Optional, Any, Tuple

from config import settings
import database
from core.interfaces import BaseOrderExecutor, OrderStatus

logger = logging.getLogger(__name__)


class PaperExecutionEngine(BaseOrderExecutor):
    """
    Virtual Execution Engine for Simulated Paper Trading.

    Responsibilities:
        - Implements BaseOrderExecutor to simulate broker order fills in a local sandbox.
        - Manages virtual trading capital (default: ₹1,00,000) with realistic mark-to-market.
        - Persists simulated positions and orders to SQLite database for historical tracking.
        - Evaluates Stop-Loss and Target levels against live incoming market quotes.

    Extends:
        core.interfaces.BaseOrderExecutor

    Uses:
        - database: SQLite persistence for simulated orders and open/closed positions.
        - config.settings: Default virtual capital and risk parameters.
    """

    def __init__(self, initial_balance: Optional[float] = None):
        self._mode = "PAPER"
        self.paper_balance: float = initial_balance or settings.INITIAL_PAPER_CAPITAL
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders_history: List[Dict[str, Any]] = []

    @property
    def mode(self) -> str:
        """Returns 'PAPER' execution mode."""
        return self._mode

    def verify_session(self) -> Dict[str, Any]:
        """
        Validates the health and readiness of the paper execution environment.
        
        Returns:
            Dict containing valid state and current virtual capital balance.
        """
        return {
            "valid": True,
            "mode": "PAPER",
            "error": None,
            "virtual_balance": self.paper_balance
        }

    # -------------------------------------------------------------------------
    # Order Simulation (SRP decomposed)
    # -------------------------------------------------------------------------

    def _create_position_record(
        self,
        pos_id: str,
        order_id: str,
        proposal: Dict[str, Any],
        lot_size: int,
        entry_price: float,
        timestamp: str
    ) -> Dict[str, Any]:
        """Constructs a simulated position entity and stores it in memory & SQLite."""
        position: Dict[str, Any] = {
            "position_id": pos_id,
            "proposal_id": proposal.get("proposal_id"),
            "order_id": order_id,
            "symbol": proposal["symbol"],
            "instrument": proposal["instrument"],
            "signal_type": proposal["signal_type"],
            "quantity": lot_size,
            "buy_price": entry_price,
            "current_ltp": entry_price,
            "stop_loss": float(proposal["stop_loss"]),
            "target_1": float(proposal["target_1"]),
            "target_2": float(proposal["target_2"]),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "pnl_pct": 0.0,
            "opened_at": timestamp,
            "status": "OPEN",
            "mode": "PAPER"
        }
        self.positions[pos_id] = position
        database.save_position(position)
        return position

    def _create_order_record(
        self,
        order_id: str,
        proposal: Dict[str, Any],
        lot_size: int,
        entry_price: float,
        timestamp: str
    ) -> Dict[str, Any]:
        """Constructs a simulated order audit log and persists it to SQLite."""
        order_record: Dict[str, Any] = {
            "order_id": order_id,
            "instrument": proposal["instrument"],
            "type": "BUY" if "BUY" in proposal["signal_type"] else "SELL",
            "quantity": lot_size,
            "price": entry_price,
            "status": OrderStatus.EXECUTED,
            "status_message": "Paper Sandbox Simulation (Zero financial risk)",
            "mode": "PAPER",
            "timestamp": timestamp
        }
        self.orders_history.insert(0, order_record)
        database.save_order(order_record, proposal.get("proposal_id"))
        return order_record

    def execute_order(self, proposal: Dict[str, Any], lot_size: int) -> Dict[str, Any]:
        """
        Simulates execution of a trade proposal within the paper sandbox.

        Args:
            proposal: Trade proposal dictionary containing instrument, entry price, SL, TP.
            lot_size: Number of lots to simulate.

        Returns:
            Dictionary containing order record, position details, mode, and execution message.
        """
        order_id = f"SIM-{uuid.uuid4().hex[:6].upper()}"
        pos_id = f"POS-{uuid.uuid4().hex[:6].upper()}"
        entry_price = float(proposal["entry_price"])
        now_str = datetime.datetime.now().strftime("%H:%M:%S")

        # 1. Create simulated position
        position = self._create_position_record(
            pos_id, order_id, proposal, lot_size, entry_price, now_str
        )

        # 2. Create simulated order log
        order_record = self._create_order_record(
            order_id, proposal, lot_size, entry_price, now_str
        )

        logger.info(
            f"[PAPER ENGINE] Executed {order_record['type']} {lot_size} lot(s) "
            f"{proposal['instrument']} @ ₹{entry_price}"
        )

        return {
            "order": order_record,
            "position": position,
            "mode": "PAPER",
            "message": "Order executed in Paper Sandbox (Virtual Simulation)."
        }

    # -------------------------------------------------------------------------
    # Position Square-Off & Accounting (SRP decomposed)
    # -------------------------------------------------------------------------

    def _calculate_realized_pnl(
        self,
        position: Dict[str, Any],
        exit_price: float
    ) -> Tuple[float, float, int]:
        """Calculates direction-aware realized P&L and return percentage."""
        buy_price = float(position["buy_price"])
        qty = int(position.get("quantity", 1))
        is_long = "BUY" in position.get("signal_type", "BUY")
        multiplier = 1.0 if is_long else -1.0

        realized_pnl = round((exit_price - buy_price) * qty * multiplier, 2)
        pnl_pct = round(((exit_price - buy_price) / buy_price) * 100 * multiplier, 2) if buy_price > 0 else 0.0
        return realized_pnl, pnl_pct, qty

    def _persist_closed_position(
        self,
        position_id: str,
        position: Dict[str, Any],
        exit_price: float,
        realized_pnl: float,
        pnl_pct: float,
        reason: str
    ) -> None:
        """Updates simulated position fields and commits them to SQLite."""
        position["status"] = "CLOSED"
        position["exit_price"] = exit_price
        position["realized_pnl"] = realized_pnl
        position["unrealized_pnl"] = 0.0
        position["pnl_pct"] = pnl_pct
        position["close_reason"] = reason
        position["closed_at"] = datetime.datetime.now().strftime("%H:%M:%S")

        database.update_position_status(
            position_id=position_id,
            status="CLOSED",
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            close_reason=reason
        )

    def _record_offsetting_order(
        self,
        position: Dict[str, Any],
        exit_price: float,
        quantity: int,
        realized_pnl: float,
        reason: str
    ) -> Dict[str, Any]:
        """Creates an offsetting virtual order record."""
        is_long = "BUY" in position.get("signal_type", "BUY")
        offsetting_order = {
            "order_id": f"SIM-EXIT-{uuid.uuid4().hex[:4].upper()}",
            "instrument": position["instrument"],
            "type": "SELL" if is_long else "BUY",
            "quantity": quantity,
            "price": exit_price,
            "status": OrderStatus.EXECUTED,
            "status_message": f"Closed via {reason}",
            "mode": "PAPER",
            "pnl": realized_pnl,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
        }
        self.orders_history.insert(0, offsetting_order)
        database.save_order(offsetting_order, position.get("proposal_id"))
        return offsetting_order

    def close_position(self, position_id: str, reason: str = "MANUAL_EXIT") -> Dict[str, Any]:
        """
        Closes an active simulated position and calculates final realized P&L.

        Args:
            position_id: Position ID to terminate.
            reason: Closure trigger ('MANUAL_EXIT', 'TRIGGERED_SL', 'TRIGGERED_TARGET').

        Returns:
            Dictionary containing closed position details, exit price, and realized P&L.
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found in Paper Engine.")

        exit_price = float(position["current_ltp"])

        # 1. P&L Calculation
        realized_pnl, pnl_pct, qty = self._calculate_realized_pnl(position, exit_price)

        # 2. Update virtual capital balance
        self.paper_balance += realized_pnl

        # 3. Persist closed position
        self._persist_closed_position(position_id, position, exit_price, realized_pnl, pnl_pct, reason)

        # 4. Record offsetting order audit log
        self._record_offsetting_order(position, exit_price, qty, realized_pnl, reason)

        # 5. Evict from active positions pool
        del self.positions[position_id]

        logger.info(f"[PAPER ENGINE] Closed position {position_id} ({reason}) with realized P&L: ₹{realized_pnl:+}")

        return {
            "message": "Position closed successfully",
            "position": position,
            "realized_pnl": realized_pnl,
            "exit_price": exit_price,
            "reason": reason
        }

    # -------------------------------------------------------------------------
    # Mark-to-Market & Automated Triggers (SRP decomposed)
    # -------------------------------------------------------------------------

    def _check_sl_tp_triggers(self, position: Dict[str, Any], current_price: float) -> Optional[str]:
        """Evaluates whether current price has triggered Stop-Loss or Take-Profit thresholds."""
        is_long = "BUY" in position.get("signal_type", "BUY")
        sl = float(position["stop_loss"])
        t1 = float(position["target_1"])

        if is_long:
            if current_price <= sl:
                return OrderStatus.TRIGGERED_SL
            if current_price >= t1:
                return OrderStatus.TRIGGERED_TARGET
        else:
            if current_price >= sl:
                return OrderStatus.TRIGGERED_SL
            if current_price <= t1:
                return OrderStatus.TRIGGERED_TARGET

        return None

    def update_pnl(self, live_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Updates unrealized P&L for all active paper positions based on live prices.

        Args:
            live_prices: Mapping of symbol -> latest traded price (LTP).

        Returns:
            List of closed positions if any hit SL or Target.
        """
        closed_positions: List[Dict[str, Any]] = []

        for pos_id, pos in list(self.positions.items()):
            symbol = pos["symbol"]
            current_price = live_prices.get(symbol)
            if current_price is None or current_price <= 0:
                continue

            pos["current_ltp"] = current_price
            buy_price = float(pos["buy_price"])
            qty = int(pos["quantity"])
            is_long = "BUY" in pos.get("signal_type", "BUY")
            multiplier = 1.0 if is_long else -1.0

            unrealized = round((current_price - buy_price) * qty * multiplier, 2)
            pct = round(((current_price - buy_price) / buy_price) * 100 * multiplier, 2) if buy_price > 0 else 0.0
            pos["unrealized_pnl"] = unrealized
            pos["pnl_pct"] = pct

            database.update_position_pnl(pos_id, current_price, unrealized, pct)

            trigger = self._check_sl_tp_triggers(pos, current_price)
            if trigger:
                result = self.close_position(pos_id, reason=trigger)
                closed_positions.append(result)

        return closed_positions
