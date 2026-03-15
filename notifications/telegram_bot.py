"""
Telegram Bot Notifier — Send trade alerts via Telegram.

Setup:
  1. Message @BotFather on Telegram → /newbot → get token
  2. Send a message to your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your chat_id
  3. Set in .env:
     TELEGRAM_BOT_TOKEN=your_token
     TELEGRAM_CHAT_ID=your_chat_id
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram Bot API."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._api_url = f"https://api.telegram.org/bot{token}"

    def send(self, message: str, level: str = "info") -> bool:
        """
        Send a message to the configured Telegram chat.

        Returns True if sent successfully.
        """
        try:
            import requests

            # Level-based emoji prefix
            prefixes = {
                "trade": "💹",
                "warning": "⚠️",
                "error": "🚨",
                "info": "ℹ️",
            }
            prefix = prefixes.get(level, "")
            full_message = f"{prefix} {message}" if prefix else message

            response = requests.post(
                f"{self._api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": full_message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )

            if response.status_code == 200:
                logger.debug("Telegram message sent")
                return True
            else:
                logger.error(
                    f"Telegram API error: {response.status_code} — {response.text}"
                )
                return False

        except ImportError:
            logger.error("requests library not installed")
            return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
