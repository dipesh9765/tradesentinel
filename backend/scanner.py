"""
Autonomous Continuous Market Opportunity Scanner - TradeSentinel

This module implements the 24/7 background market scanner service that continuously
evaluates live market feeds for high-conviction A+ setups (Confluence Score >= 75/100),
respects market hours, enforces anti-spam cooldowns, and automatically dispatches
multi-channel notifications and real-time WebSocket alerts to the user without manual scanning.
"""

import asyncio
import contextlib
import datetime
import logging
from typing import Any

from app.api.v1.endpoints.websocket import active_connections
from app.core.genConsts import GenConsts
from config import get_watchlist_symbols
from kite_executor import kite_executor
from market_data import market_data_manager
from notifications import notification_service
from quant_strategy import quant_engine
from trade_analyzer import trade_analyzer

logger = logging.getLogger(__name__)

# Strong references so fire-and-forget notification tasks are not garbage collected mid-flight.
_background_tasks: set[asyncio.Task] = set()


class OpportunityScannerService:
    """
    Autonomous Background Market Scanner Service.

    Responsibilities:
        - Continuously polls watched instruments during NSE market hours (09:15 - 15:30 IST).
        - Evaluates closed 5-minute candlestick bars against multi-factor quantitative criteria.
        - Enforces an A+ Confluence Gate (Score >= 75/100) and Capital Preservation filters.
        - Applies anti-spam cooldowns (10 minutes per symbol) to prevent repetitive noise.
        - Automatically creates actionable Trade Proposals and broadcasts real-time alerts.
    """

    def __init__(self, scan_interval_sec: float = 12.0, cooldown_minutes: int = 10):
        self.scan_interval_sec: float = scan_interval_sec
        self.cooldown_minutes: int = cooldown_minutes
        self.last_alert_times: dict[str, datetime.datetime] = {}
        self.is_running: bool = False
        self._task: asyncio.Task | None = None

    def is_market_open(self) -> bool:
        """
        Checks if current time is within NSE market trading hours (09:15 AM to 03:30 PM IST, Mon-Fri).
        For testing or paper mode when market is offline, allows simulated continuous scanning if enabled.
        """
        now = datetime.datetime.now()
        # In testing/dev environment with live Kite or Paper data cached, we allow scanning
        if market_data_manager.is_configured() and market_data_manager.candles_data:
            return True

        # Weekday check (0 = Mon, 4 = Fri)
        if now.weekday() >= 5:
            return False

        # NSE market hours in IST
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close

    def is_on_cooldown(self, symbol: str) -> bool:
        """Checks whether an alert for this symbol was recently dispatched."""
        last_time = self.last_alert_times.get(symbol)
        if not last_time:
            return False

        elapsed = (datetime.datetime.now() - last_time).total_seconds() / 60.0
        return elapsed < self.cooldown_minutes

    async def scan_single_symbol(self, symbol: str) -> dict[str, Any] | None:
        """
        Evaluates quantitative setup for a symbol and generates proposal if A+ setup forms.
        """
        if self.is_on_cooldown(symbol):
            return None

        # 1. Single-Loss 45-Minute Lockout Check
        is_locked, remaining = kite_executor.is_in_loss_lockout(symbol, cooldown_minutes=45)
        if is_locked:
            logger.debug(f"{symbol} is in 45-minute Loss Lockout ({remaining}m remaining). Skipping scan.")
            return None

        # Check if symbol already has an open position or pending proposal
        for pos in kite_executor.positions.values():
            if pos.get("symbol") == symbol and pos.get("status") == "OPEN":
                return None  # Already in an active trade for this symbol

        for prop in kite_executor.pending_proposals.values():
            if prop.get("symbol") == symbol and prop.get("status") == GenConsts.STATUS_PENDING_APPROVAL:
                return None  # Already awaiting approval

        quote = market_data_manager.get_quote(symbol)
        candle_df = market_data_manager.candles_data.get(symbol)

        # Attempt to fetch candles if Kite is configured
        if (candle_df is None or candle_df.empty) and market_data_manager.is_configured():
            market_data_manager.get_candles(symbol, limit=60)
            candle_df = market_data_manager.candles_data.get(symbol)

        if candle_df is None or len(candle_df) < 15 or quote.get("ltp", 0) <= 0:
            return None

        # 2. Run Quantitative Multi-Factor Analysis (with 15m ORB filter)
        quant_result = quant_engine.evaluate_quantitative_setup(symbol, quote, candle_df)

        if not quant_result.get("actionable"):
            return None

        confluence_score = quant_result.get("confluence_score", 0)
        if confluence_score < 75:
            return None  # Strict A+ Confluence Gate

        # 3. Bank Nifty Heavyweight Bank Alignment Check
        if "BANK" in symbol.upper():
            hdfc_quote = market_data_manager.get_quote("HDFCBANK")
            icici_quote = market_data_manager.get_quote("ICICIBANK")
            direction = quant_result.get("direction", "NEUTRAL")
            if direction == "BULLISH":
                # For Bullish Bank Nifty, at least one of HDFC or ICICI should not be collapsing (> -0.7%)
                hdfc_chg = hdfc_quote.get("change_pct", 0.0) if hdfc_quote else 0.0
                icici_chg = icici_quote.get("change_pct", 0.0) if icici_quote else 0.0
                if hdfc_chg < -1.0 and icici_chg < -1.0:
                    logger.info(
                        f"Bank Nifty Bullish setup filtered: Heavyweights HDFC ({hdfc_chg}%) and ICICI ({icici_chg}%) are negative."
                    )
                    return None

        # 4. Generate Full Institutional Setup
        signal = trade_analyzer.analyze_market_setup(symbol, quote, candle_df)
        if not signal.get("actionable"):
            return None
        try:
            proposal = kite_executor.create_trade_proposal(signal)
        except ValueError as e:
            logger.info(f"Scanner proposal for {symbol} rejected: {e}")
            return None

        # 5. Update Cooldown
        self.last_alert_times[symbol] = datetime.datetime.now()

        logger.info(
            f"🎯 [AUTO SCANNER ALERT] High-Conviction A+ Setup detected for {symbol}! "
            f"Signal: {proposal['signal_type']} {proposal['instrument']} @ ₹{proposal['entry_price']} "
            f"(Confluence: {confluence_score}%)"
        )

        # 6. Broadcast Real-Time Alert to all connected WebSocket clients
        if active_connections:
            ws_payload = {
                "type": GenConsts.WS_EVENT_PROPOSAL_ALERT,
                "proposal": proposal,
                "message": f"High Conviction A+ Setup spotted on {symbol} ({confluence_score}% Confluence)!",
            }
            for ws in list(active_connections):
                with contextlib.suppress(Exception):
                    await ws.send_json(ws_payload)

        # 7. Dispatch multi-channel notifications (Browser / Telegram / Discord / Slack)
        task = asyncio.create_task(notification_service.notify_trade_proposal(proposal))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return proposal

    async def run_scan_cycle(self) -> None:
        """Executes a single scan cycle across all active watchlist symbols."""
        if not market_data_manager.is_configured():
            return

        # 15:15 IST Auto-Squareoff Check
        now = datetime.datetime.now()
        if now.hour == 15 and now.minute >= 15:
            kite_executor.auto_square_off_mis_positions()

        symbols = get_watchlist_symbols()
        for symbol in symbols:
            try:
                await self.scan_single_symbol(symbol)
                await asyncio.sleep(0.5)  # Small delay between symbols to avoid rate limits
            except Exception as e:
                logger.debug(f"Scanner error on {symbol}: {e}")

    async def start_loop(self) -> None:
        """Continuous background scanning worker loop."""
        self.is_running = True
        logger.info(f"Autonomous Market Scanner started (Polling interval: {self.scan_interval_sec}s).")

        while self.is_running:
            try:
                if self.is_market_open():
                    await self.run_scan_cycle()
            except Exception as e:
                logger.error(f"Error in opportunity scanner cycle: {e}")

            await asyncio.sleep(self.scan_interval_sec)

    def stop(self) -> None:
        """Stops the background scanner loop."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Autonomous Market Scanner stopped.")


# Singleton instance
opportunity_scanner = OpportunityScannerService()
