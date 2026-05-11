"""
Email Notifier — Send trade alerts via SMTP email.

Setup (Gmail example):
  1. Enable 2FA on your Google account
  2. Generate an App Password: https://myaccount.google.com/apppasswords
  3. Set in .env:
     EMAIL_SMTP_HOST=smtp.gmail.com
     EMAIL_SMTP_PORT=587
     EMAIL_USER=your_email@gmail.com
     EMAIL_PASSWORD=your_app_password
     EMAIL_TO=recipient@example.com
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send notifications via SMTP email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        to_email: str,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.to_email = to_email

    def send(self, message: str, level: str = "info") -> bool:
        """Send an email notification."""
        try:
            subject_map = {
                "trade": "🔔 QuantumTrade — New Trade Alert",
                "warning": "⚠️ QuantumTrade — Warning",
                "error": "🚨 QuantumTrade — Error Alert",
                "info": "ℹ️ QuantumTrade — Info",
            }

            msg = MIMEMultipart("alternative")
            msg["From"] = self.username
            msg["To"] = self.to_email
            msg["Subject"] = subject_map.get(level, "QuantumTrade Alert")

            # Plain text
            msg.attach(MIMEText(message, "plain"))

            # HTML version
            html_body = f"""
            <div style="font-family: 'Segoe UI', sans-serif; padding: 20px;
                        background: #1a1a2e; color: #eee; border-radius: 8px;">
                <h2 style="color: #00d4ff; margin-bottom: 10px;">
                    QuantumTrade Alert
                </h2>
                <p style="font-size: 14px; line-height: 1.6;">
                    {message.replace(chr(10), '<br>')}
                </p>
                <hr style="border-color: #333; margin: 15px 0;">
                <p style="font-size: 11px; color: #888;">
                    {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
                </p>
            </div>
            """
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, self.to_email, msg.as_string())

            logger.debug("Email notification sent")
            return True

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
