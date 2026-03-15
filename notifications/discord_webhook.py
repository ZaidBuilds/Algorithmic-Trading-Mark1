"""
Discord Webhook Notifier — Send trade alerts to a Discord channel.

Setup:
  1. In Discord: Channel Settings → Integrations → Webhooks → New Webhook
  2. Copy the webhook URL
  3. Set in .env:
     DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
"""

import logging

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Send notifications via Discord webhooks."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str, level: str = "info") -> bool:
        """Send a message to the configured Discord webhook."""
        try:
            import requests

            # Color codes for embed sidebar
            colors = {
                "trade": 0x00FF00,   # Green
                "warning": 0xFFAA00, # Orange
                "error": 0xFF0000,   # Red
                "info": 0x0099FF,    # Blue
            }

            payload = {
                "embeds": [
                    {
                        "title": f"QuantumTrade Alert",
                        "description": message,
                        "color": colors.get(level, 0x0099FF),
                    }
                ]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )

            if response.status_code in (200, 204):
                logger.debug("Discord message sent")
                return True
            else:
                logger.error(
                    f"Discord webhook error: {response.status_code}"
                )
                return False

        except ImportError:
            logger.error("requests library not installed")
            return False
        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return False
