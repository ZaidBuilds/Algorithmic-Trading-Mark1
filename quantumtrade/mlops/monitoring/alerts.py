"""Alert manager for drift and degradation notifications."""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelDriftAlert:
    """Alert for model drift detection."""
    model_name: str
    alert_type: str  # "data_drift", "concept_drift", "performance_degradation"
    severity: str   # "low", "medium", "high", "critical"
    message: str
    metrics: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    suggested_action: Optional[str] = None


@dataclass
class AlertConfig:
    """Alert configuration."""
    enabled: bool = True
    min_severity: str = "medium"  # Minimum severity to send
    throttle_period_minutes: int = 15  # Minimum time between duplicate alerts
    webhook_url: Optional[str] = None
    telegram_config: Optional[Dict[str, str]] = None
    discord_config: Optional[Dict[str, str]] = None


class AlertManager:
    """
    Manages alerts for drift, degradation, and system events.
    
    Supports multiple notification channels:
    - Webhook (generic)
    - Telegram
    - Discord
    - Email (future)
    """
    
    SEVERITY_LEVELS = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }
    
    def __init__(self, config: AlertConfig):
        """
        Initialize alert manager.
        
        Args:
            config: Alert configuration
        """
        self.config = config
        self._alert_history: List[ModelDriftAlert] = []
        self._last_alert_times: Dict[str, datetime] = {}
        
        logger.info("AlertManager initialized")
    
    async def send_alert(self, alert: ModelDriftAlert):
        """
        Send alert via configured channels.
        
        Args:
            alert: Alert object
        """
        if not self.config.enabled:
            return
        
        # Check severity threshold
        if self.SEVERITY_LEVELS[alert.severity] < self.SEVERITY_LEVELS[self.config.min_severity]:
            logger.debug(f"Alert suppressed (severity {alert.severity} below threshold)")
            return
        
        # Check throttling
        alert_key = f"{alert.model_name}:{alert.alert_type}"
        now = datetime.utcnow()
        last_time = self._last_alert_times.get(alert_key)
        
        if last_time and (now - last_time).total_seconds() < self.config.throttle_period_minutes * 60:
            logger.debug(f"Alert throttled: {alert_key}")
            return
        
        self._last_alert_times[alert_key] = now
        self._alert_history.append(alert)
        
        # Send via configured channels
        tasks = []
        
        if self.config.webhook_url:
            tasks.append(self._send_webhook(alert))
        
        if self.config.telegram_config:
            tasks.append(self._send_telegram(alert))
        
        if self.config.discord_config:
            tasks.append(self._send_discord(alert))
        
        # Execute all
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Alert send failed: {r}")
        
        logger.info(f"Alert sent: [{alert.severity.upper()}] {alert.message}")
    
    async def _send_webhook(self, alert: ModelDriftAlert):
        """Send alert via generic webhook."""
        if not self.config.webhook_url:
            return
        
        payload = {
            "model_name": alert.model_name,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "metrics": alert.metrics,
            "timestamp": alert.timestamp.isoformat(),
            "suggested_action": alert.suggested_action,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
    
    async def _send_telegram(self, alert: ModelDriftAlert):
        """Send alert via Telegram bot."""
        config = self.config.telegram_config
        if not config:
            return
        
        token = config.get("bot_token")
        chat_id = config.get("chat_id")
        if not token or not chat_id:
            return
        
        emoji = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔥",
        }.get(alert.severity, "📊")
        
        text = (
            f"{emoji} *{alert.model_name}*\n\n"
            f"*{alert.alert_type.replace('_', ' ').title()}*\n"
            f"{alert.message}\n\n"
            f"*Metrics:*\n"
        )
        
        for key, value in alert.metrics.items():
            if isinstance(value, float):
                text += f"  • {key}: {value:.4f}\n"
            else:
                text += f"  • {key}: {value}\n"
        
        if alert.suggested_action:
            text += f"\n💡 *Action:* {alert.suggested_action}"
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as resp:
                resp.raise_for_status()
    
    async def _send_discord(self, alert: ModelDriftAlert):
        """Send alert via Discord webhook."""
        config = self.config.discord_config
        if not config or not config.get("webhook_url"):
            return
        
        color = {
            "low": 0x808080,      # Gray
            "medium": 0xFFA500,   # Orange
            "high": 0xFF0000,     # Red
            "critical": 0x8B0000, # Dark Red
        }.get(alert.severity, 0x0000FF)
        
        embed = {
            "title": f"🚨 {alert.model_name} - {alert.alert_type.replace('_', ' ').title()}",
            "description": alert.message,
            "color": color,
            "timestamp": alert.timestamp.isoformat(),
            "fields": [
                {
                    "name": key,
                    "value": f"{value:.4f}" if isinstance(value, float) else str(value),
                    "inline": True,
                }
                for key, value in list(alert.metrics.items())[:5]
            ],
        }
        
        if alert.suggested_action:
            embed["footer"] = {"text": f"Action: {alert.suggested_action}"}
        
        payload = {"embeds": [embed]}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(config["webhook_url"], json=payload) as resp:
                resp.raise_for_status()
    
    def send_custom_alert(
        self,
        model_name: str,
        alert_type: str,
        severity: str,
        message: str,
        metrics: Optional[Dict[str, Any]] = None,
        suggested_action: Optional[str] = None,
    ):
        """
        Send custom alert (sync wrapper).
        
        Args:
            model_name: Model identifier
            alert_type: Type of alert
            severity: Severity level
            message: Alert message
            metrics: Additional metrics
            suggested_action: Recommended action
        """
        alert = ModelDriftAlert(
            model_name=model_name,
            alert_type=alert_type,
            severity=severity,
            message=message,
            metrics=metrics or {},
            timestamp=datetime.utcnow(),
            suggested_action=suggested_action,
        )
        
        # Run async in background
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self.send_alert(alert))
        except RuntimeError:
            # No event loop, run synchronously
            asyncio.run(self.send_alert(alert))
    
    def get_alert_history(
        self,
        model_name: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[ModelDriftAlert]:
        """Get filtered alert history."""
        alerts = self._alert_history
        
        if model_name:
            alerts = [a for a in alerts if a.model_name == model_name]
        
        if since:
            alerts = [a for a in alerts if a.timestamp >= since]
        
        return alerts
