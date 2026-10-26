"""Reconciles local position state against the broker after restarts or manual exits."""

import logging
import time
from typing import Any

from app.core.server_logger import log_outgoing_request, log_outgoing_response
from app.db import database
from app.trading.state import EngineState

logger = logging.getLogger(__name__)


class ReconciliationMixin(EngineState):
    """Reconciles local position state against the broker after restarts or manual exits.

    Mixed into UnifiedTradingEngine; relies on its shared state (positions, orders_history, ...).
    """

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
