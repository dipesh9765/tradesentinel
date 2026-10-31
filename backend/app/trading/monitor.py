"""Mark-to-market P&L, trailing stops, exit triggers and the portfolio summary."""

import logging
from typing import Any

from app.core.config import settings
from app.db import database
from app.strategy.exit_rules import check_exit_triggers
from app.strategy.trade_validation import is_option_instrument
from app.trading.state import EngineState

logger = logging.getLogger(__name__)


class PositionMonitorMixin(EngineState):
    """Mark-to-market P&L, trailing stops, exit triggers and the portfolio summary.

    Mixed into UnifiedTradingEngine; relies on its shared state (positions, orders_history, ...).
    """

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
