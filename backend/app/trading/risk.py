"""Pre-trade risk controls: loss lockout, daily limits and entry-price drift."""

import datetime
import logging
from typing import Any

from app.core.config import settings
from app.db import database
from app.strategy.trade_validation import is_option_instrument
from app.trading.state import EngineState

logger = logging.getLogger(__name__)


class RiskMixin(EngineState):
    """Pre-trade risk controls: loss lockout, daily limits and entry-price drift.

    Mixed into UnifiedTradingEngine; relies on its shared state (positions, orders_history, ...).
    """

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
            from app.market.market_data import market_data_manager

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
