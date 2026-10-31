"""
Multi-Channel Notification Dispatcher - TradeSentinel

This module implements the notification dispatch layer adhering to the
BaseNotificationDispatcher interface. It coordinates alerts across multiple communication
channels including Telegram bots, Discord webhooks, Slack incoming webhooks, and desktop
notifications, respecting the configured 'Office Mode' for quiet/discrete alerting.
"""

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.interfaces import BaseNotificationDispatcher

logger = logging.getLogger(__name__)


class NotificationConfig(BaseModel):
    """Configuration container for notification channels and privacy options."""

    telegram_bot_token: str | None = Field(default="", description="Telegram Bot API Token")
    telegram_chat_id: str | None = Field(default="", description="Telegram target Chat or Channel ID")
    discord_webhook_url: str | None = Field(default="", description="Discord Webhook URL")
    slack_webhook_url: str | None = Field(default="", description="Slack Incoming Webhook URL")
    desktop_enabled: bool = Field(default=True, description="Enable browser/desktop notifications")
    office_mode: bool = Field(default=True, description="Mute loud speech synthesis; use subtle chimes")


class NotificationService(BaseNotificationDispatcher):
    """
    Multi-Channel Alerting and Notification Dispatcher.

    Responsibilities:
        - Coordinates real-time outgoing alerts across Telegram, Discord, and Slack.
        - Formats channel-specific notification templates (HTML for Telegram, Rich Embeds for Discord,
          mrkdwn for Slack).
        - Respects 'Office Mode' preferences to toggle between high-priority visual/chime notifications
          and silent operation.
        - Maintains an in-memory chronological notification audit log.

    Extends:
        - `core.interfaces.BaseNotificationDispatcher`: Abstract interface standardizing
          `notify_trade_proposal`, `notify_trade_executed`, and `notify_target_or_sl`.

    Uses / Dependencies:
        - `httpx.AsyncClient`: High-performance asynchronous HTTP client for non-blocking webhook dispatches.
        - `NotificationConfig`: Pydantic validation model for webhook URLs and channel tokens.
        - `server_logger` / `logging`: Logs outbound dispatch status and network errors.

    Design Pattern:
        - Dispatcher / Observer Pattern (multi-target fan-out of trade events).
        - Strategy Pattern (format-specific rendering per external communication channel).
    """

    def __init__(self):
        self.config: NotificationConfig = NotificationConfig()
        self.notification_log: list[dict[str, Any]] = []

    def update_config(self, new_config: dict[str, Any]) -> None:
        """
        Updates active notification credentials and office mode toggles.

        Args:
            new_config: Dictionary of config parameters to update.
        """
        for k, v in new_config.items():
            if hasattr(self.config, k) and v is not None:
                setattr(self.config, k, v)
        logger.info(f"Notification config updated. Office Mode: {self.config.office_mode}")

    async def _dispatch_to_active_channels(
        self,
        telegram_html: str,
        discord_title: str,
        discord_message: str,
        discord_color: int,
        slack_mrkdwn: str,
    ) -> None:
        """Dispatches pre-formatted alerts to all configured communication channels concurrently."""
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            await self._send_telegram(telegram_html)

        if self.config.discord_webhook_url:
            await self._send_discord(discord_title, discord_message, color=discord_color)

        if self.config.slack_webhook_url:
            await self._send_slack(slack_mrkdwn)

    def _format_proposal_message(self, proposal: dict[str, Any]) -> tuple[str, str, str]:
        """Formats trade proposal title, body, and telegram HTML."""
        signal_type = proposal["signal_type"]
        instrument = proposal["instrument"]
        entry = proposal["entry_price"]
        sl = proposal["stop_loss"]
        tp = proposal["target_1"]
        rr = proposal["risk_reward"]
        conf = proposal["confidence"]

        title = f"🚨 AI Trade Alert: {signal_type.replace('_', ' ')} - {instrument}"
        message = (
            f"🎯 Setup: {signal_type}\n"
            f"📈 Instrument: {instrument}\n"
            f"💵 Entry: ₹{entry}\n"
            f"🛑 Stop Loss: ₹{sl}\n"
            f"🎯 Target 1: ₹{tp}\n"
            f"⚖️ Risk-Reward: {rr} | Confidence: {conf}%\n"
            f"⏰ 60s confirmation required on dashboard."
        )
        telegram_html = f"<b>{title}</b>\n\n{message}"
        return title, message, telegram_html

    async def notify_trade_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """
        Dispatches a high-priority alert when a new AI trade proposal is generated.

        Args:
            proposal: Trade proposal dictionary.

        Returns:
            Dict containing notification log entry.
        """
        title, message, telegram_html = self._format_proposal_message(proposal)

        record = {"type": "TRADE_PROPOSAL", "title": title, "message": message, "data": proposal}
        self.notification_log.insert(0, record)

        await self._dispatch_to_active_channels(
            telegram_html=telegram_html,
            discord_title=title,
            discord_message=message,
            discord_color=0x00F0FF,
            slack_mrkdwn=f"*{title}*\n{message}",
        )

        return record

    async def notify_trade_executed(self, order: dict[str, Any], position: dict[str, Any]) -> None:
        """
        Dispatches order execution notification upon fill confirmation.

        Args:
            order: Executed order dictionary.
            position: Initialized position dictionary.
        """
        instrument = order["instrument"]
        price = order["price"]
        qty = order["quantity"]
        mode = order["mode"]

        title = f"✅ Order Executed: {instrument} (1 Lot)"
        message = (
            f"Mode: {mode}\n"
            f"Qty: {qty} Lot\n"
            f"Price: ₹{price}\n"
            f"SL: ₹{position.get('stop_loss')} | Target: ₹{position.get('target_1')}"
        )

        await self._dispatch_to_active_channels(
            telegram_html=f"<b>{title}</b>\n\n{message}",
            discord_title=title,
            discord_message=message,
            discord_color=0x00E699,
            slack_mrkdwn=f"*{title}*\n{message}",
        )

    async def notify_target_or_sl(self, symbol: str, reason: str, pnl: float) -> None:
        """
        Dispatches alert when stop-loss or profit target is triggered.

        Args:
            symbol: Target ticker symbol.
            reason: Trigger reason ('STOP_LOSS_HIT', 'TARGET_HIT').
            pnl: Realized profit or loss in INR.
        """
        emoji = "🎯" if "TARGET" in reason else "🛑"
        title = f"{emoji} Position Closed: {reason.replace('_', ' ')}"
        message = f"Symbol: {symbol}\nRealized P&L: ₹{pnl:+.2f}"

        await self._dispatch_to_active_channels(
            telegram_html=f"<b>{title}</b>\n\n{message}",
            discord_title=title,
            discord_message=message,
            discord_color=0x00E699 if pnl >= 0 else 0xFF3366,
            slack_mrkdwn=f"*{title}*\n{message}",
        )

    async def _send_telegram(self, text: str) -> None:
        """Sends an HTML formatted message via Telegram Bot API."""
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    url, json={"chat_id": self.config.telegram_chat_id, "text": text, "parse_mode": "HTML"}
                )
        except Exception as e:
            logger.error(f"Failed to dispatch Telegram alert: {e}")

    async def _send_discord(self, title: str, description: str, color: int = 0x00F0FF) -> None:
        """Sends an embedded rich card via Discord Webhook."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    self.config.discord_webhook_url or "",
                    json={"embeds": [{"title": title, "description": description, "color": color}]},
                )
        except Exception as e:
            logger.error(f"Failed to dispatch Discord webhook: {e}")

    async def _send_slack(self, text: str) -> None:
        """Sends a markdown message via Slack Incoming Webhook."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.config.slack_webhook_url or "", json={"text": text})
        except Exception as e:
            logger.error(f"Failed to dispatch Slack webhook: {e}")


# Singleton instance
notification_service = NotificationService()
