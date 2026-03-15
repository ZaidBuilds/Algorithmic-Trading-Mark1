"""
Notification system for real-time trade alerts.

Supported channels:
  - Telegram Bot
  - Discord Webhooks
  - Email (SMTP)

Usage:
    from notifications import NotificationManager
    notifier = NotificationManager()
    notifier.send("🚀 BUY AAPL @ $175.50", level="trade")
"""

from .telegram_bot import TelegramNotifier
from .discord_webhook import DiscordNotifier
from .email_notifier import EmailNotifier

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Unified notification manager — sends alerts to all configured channels.
    Channels that aren't configured are silently skipped.
    """

    def __init__(
        self,
        telegram_token: str = "",
        telegram_chat_id: str = "",
        discord_webhook_url: str = "",
        email_smtp_host: str = "",
        email_smtp_port: int = 587,
        email_user: str = "",
        email_password: str = "",
        email_to: str = "",
    ):
        self._channels = []

        # Telegram
        if telegram_token and telegram_chat_id:
            self._channels.append(
                TelegramNotifier(token=telegram_token, chat_id=telegram_chat_id)
            )
            logger.info("📱 Telegram notifications enabled")

        # Discord
        if discord_webhook_url:
            self._channels.append(
                DiscordNotifier(webhook_url=discord_webhook_url)
            )
            logger.info("🎮 Discord notifications enabled")

        # Email
        if email_smtp_host and email_user:
            self._channels.append(
                EmailNotifier(
                    smtp_host=email_smtp_host,
                    smtp_port=email_smtp_port,
                    username=email_user,
                    password=email_password,
                    to_email=email_to or email_user,
                )
            )
            logger.info("📧 Email notifications enabled")

        if not self._channels:
            logger.warning("No notification channels configured")

    def send(self, message: str, level: str = "info") -> None:
        """
        Send a notification to all configured channels.

        Args:
            message: The notification text
            level: "info", "trade", "warning", "error"
        """
        for ch in self._channels:
            try:
                ch.send(message, level=level)
            except Exception as e:
                logger.error(f"Notification failed on {ch.__class__.__name__}: {e}")

    def send_trade_alert(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        strategy: str = "",
        pnl: Optional[float] = None,
    ) -> None:
        """Send a formatted trade alert."""
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        msg = (
            f"{emoji} **{side.upper()} {symbol}**\n"
            f"📊 Qty: {quantity}  |  💰 Price: ${price:,.2f}\n"
        )
        if strategy:
            msg += f"🎯 Strategy: {strategy}\n"
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            msg += f"{pnl_emoji} P&L: ${pnl:+,.2f}\n"

        self.send(msg, level="trade")

    @property
    def channel_count(self) -> int:
        return len(self._channels)


__all__ = [
    "NotificationManager",
    "TelegramNotifier",
    "DiscordNotifier",
    "EmailNotifier",
]
