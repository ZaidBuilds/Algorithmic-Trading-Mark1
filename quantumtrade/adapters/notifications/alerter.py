"""
Alertmanager integration for QuantumTrade.

Formats and forwards alerts from Alertmanager to notification channels.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Alerter:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook_url: Optional[str] = None,
        email_smtp_host: Optional[str] = None,
        email_smtp_port: int = 587,
        email_user: Optional[str] = None,
        email_password: Optional[str] = None,
        email_to: Optional[str] = None,
    ):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook_url = discord_webhook_url
        self.email_smtp_host = email_smtp_host
        self.email_smtp_port = email_smtp_port
        self.email_user = email_user
        self.email_password = email_password
        self.email_to = email_to or email_user

    def format_alert(self, alert: dict) -> str:
        status = alert.get("status", "firing")
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        severity = labels.get("severity", "unknown")

        emoji = "🔴" if severity == "critical" else "⚠️"
        status_emoji = "✅" if status == "resolved" else emoji

        name = labels.get("alertname", "Unknown Alert")
        summary = annotations.get("summary", name)
        description = annotations.get("description", "")

        result = f"{status_emoji} *{name}*\n"
        result += f"   Severity: {severity.upper()}\n"
        result += f"   Status: {status}\n"
        if summary:
            result += f"   {summary}\n"
        if description:
            result += f"   {description}\n"

        return result

    def send_to_telegram(self, message: str) -> bool:
        if not self.telegram_token or not self.telegram_chat_id:
            return False
        try:
            import requests
            response = requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            return False

    def send_to_discord(self, message: str) -> bool:
        if not self.discord_webhook_url:
            return False
        try:
            import requests
            response = requests.post(
                self.discord_webhook_url,
                json={"content": message},
                timeout=10,
            )
            return response.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")
            return False

    def process_alertmanager_webhook(self, payload: dict) -> None:
        alerts = payload.get("alerts", [])
        for alert in alerts:
            message = self.format_alert(alert)
            self.send_to_telegram(message)
            self.send_to_discord(message)

    def handle_alert(self, alert_name: str, severity: str, summary: str, description: str = "") -> None:
        alert = {
            "status": "firing",
            "labels": {"alertname": alert_name, "severity": severity},
            "annotations": {"summary": summary, "description": description},
        }
        self.process_alertmanager_webhook({"alerts": [alert]})