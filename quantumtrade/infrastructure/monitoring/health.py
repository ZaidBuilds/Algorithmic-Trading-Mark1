"""
Health checking system for QuantumTrade.

Provides liveness, readiness, and health endpoints for monitoring.
"""

import time
import os
try:
    import psutil
except ImportError:
    psutil = None
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

import logging

logger = logging.getLogger(__name__)

# Thresholds
DISK_MIN_GB = 10
MEMORY_MAX_PCT = 90
CPU_MAX_PCT = 80
REDIS_MEMORY_MAX_PCT = 80


@dataclass
class HealthCheckResult:
    name: str
    status: str
    duration_ms: float
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthChecker:
    def __init__(
        self,
        db=None,
        redis_client=None,
        broker=None,
        message_bus=None,
        data_dir: str = "data",
    ):
        self.db = db
        self.redis = redis_client
        self.broker = broker
        self.bus = message_bus
        self.data_dir = data_dir

    def check_all(self) -> Dict[str, Any]:
        start_time = time.time()
        checks = {
            "database": self._check_database,
            "redis": self._check_redis,
            "broker": self._check_broker,
            "message_bus": self._check_message_bus,
            "disk": self._check_disk,
            "memory": self._check_memory,
            "cpu": self._check_cpu,
        }

        results = {}
        overall = "healthy"

        for name, check_fn in checks.items():
            start = time.time()
            try:
                result = check_fn()
                results[name] = asdict(result)
                if result.status == "unhealthy":
                    overall = "unhealthy"
                elif result.status == "degraded" and overall == "healthy":
                    overall = "degraded"
            except Exception as e:
                results[name] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "duration_ms": (time.time() - start) * 1000,
                }
                overall = "unhealthy"

        total_duration = (time.time() - start_time) * 1000
        return {
            "status": overall,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": total_duration,
            "checks": results,
        }

    def check_readiness(self) -> Dict[str, Any]:
        start_time = time.time()
        checks = ["database", "redis", "broker"]
        results = {}
        overall = "healthy"

        for name in checks:
            check_fn = getattr(self, f"_check_{name}")
            start = time.time()
            try:
                result = check_fn()
                results[name] = asdict(result)
                if result.status == "unhealthy":
                    overall = "unhealthy"
            except Exception as e:
                results[name] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "duration_ms": (time.time() - start) * 1000,
                }
                overall = "unhealthy"

        return {
            "status": overall,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "checks": results,
        }

    def check_liveness(self) -> Dict[str, Any]:
        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def _check_database(self) -> HealthCheckResult:
        start = time.time()
        try:
            if self.db is None:
                return HealthCheckResult("database", "unhealthy", 0, "Database not configured")
            self.db.conn.execute("SELECT 1").fetchone()
            return HealthCheckResult("database", "healthy", (time.time() - start) * 1000)
        except Exception as e:
            return HealthCheckResult("database", "unhealthy", (time.time() - start) * 1000, str(e))

    def _check_redis(self) -> HealthCheckResult:
        start = time.time()
        try:
            if self.redis is None:
                return HealthCheckResult("redis", "unhealthy", 0, "Redis not configured")
            ping_result = self.redis.ping()
            if not ping_result:
                return HealthCheckResult("redis", "unhealthy", (time.time() - start) * 1000, "PING failed")
            info = self.redis.info()
            used_memory = info.get("used_memory", 0)
            max_memory = info.get("maxmemory", 1)
            if max_memory > 0:
                memory_pct = (used_memory / max_memory) * 100
                if memory_pct > REDIS_MEMORY_MAX_PCT:
                    return HealthCheckResult(
                        "redis", "degraded", (time.time() - start) * 1000,
                        details={"memory_pct": memory_pct}
                    )
            return HealthCheckResult("redis", "healthy", (time.time() - start) * 1000)
        except Exception as e:
            return HealthCheckResult("redis", "unhealthy", (time.time() - start) * 1000, str(e))

    def _check_broker(self) -> HealthCheckResult:
        start = time.time()
        try:
            if self.broker is None:
                return HealthCheckResult("broker", "unhealthy", 0, "Broker not configured")
            if getattr(self.broker, "paper", True):
                return HealthCheckResult("broker", "healthy", (time.time() - start) * 1000, details={"mode": "paper"})
            if not self.broker.is_connected:
                return HealthCheckResult("broker", "unhealthy", (time.time() - start) * 1000, "Not connected")
            account = self.broker.get_account()
            return HealthCheckResult("broker", "healthy", (time.time() - start) * 1000)
        except Exception as e:
            return HealthCheckResult("broker", "unhealthy", (time.time() - start) * 1000, str(e))

    def _check_message_bus(self) -> HealthCheckResult:
        start = time.time()
        try:
            if self.bus is None:
                return HealthCheckResult("message_bus", "unhealthy", 0, "Message bus not configured")
            if not self.bus.health_check():
                return HealthCheckResult("message_bus", "unhealthy", (time.time() - start) * 1000, "Health check failed")
            test_channel = f"health_check:{int(time.time())}"
            test_msg = {"test": True, "timestamp": datetime.utcnow().isoformat()}
            msg_id = self.bus.publish(test_msg, test_channel)
            if not msg_id:
                return HealthCheckResult("message_bus", "degraded", (time.time() - start) * 1000, "Publish test failed")
            return HealthCheckResult("message_bus", "healthy", (time.time() - start) * 1000)
        except Exception as e:
            return HealthCheckResult("message_bus", "unhealthy", (time.time() - start) * 1000, str(e))

    def _check_disk(self) -> HealthCheckResult:
        start = time.time()
        try:
            if not os.path.exists(self.data_dir):
                return HealthCheckResult("disk", "unhealthy", (time.time() - start) * 1000, f"Directory {self.data_dir} not found")
            if psutil is None:
                return HealthCheckResult(
                    "disk",
                    "degraded",
                    (time.time() - start) * 1000,
                    "psutil not installed",
                )
            usage = psutil.disk_usage(self.data_dir)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < DISK_MIN_GB:
                return HealthCheckResult(
                    "disk", "unhealthy", (time.time() - start) * 1000,
                    f"Free space {free_gb:.1f}GB < {DISK_MIN_GB}GB",
                    {"free_gb": free_gb}
                )
            return HealthCheckResult("disk", "healthy", (time.time() - start) * 1000, details={"free_gb": free_gb})
        except Exception as e:
            return HealthCheckResult("disk", "unhealthy", (time.time() - start) * 1000, str(e))

    def _check_memory(self) -> HealthCheckResult:
        start = time.time()
        try:
            if psutil is None:
                return HealthCheckResult(
                    "memory",
                    "degraded",
                    (time.time() - start) * 1000,
                    "psutil not installed",
                )
            usage = psutil.virtual_memory()
            used_pct = usage.percent
            if used_pct > MEMORY_MAX_PCT:
                return HealthCheckResult(
                    "memory", "unhealthy", (time.time() - start) * 1000,
                    f"Memory usage {used_pct}% > {MEMORY_MAX_PCT}%",
                    {"percent": used_pct}
                )
            return HealthCheckResult("memory", "healthy", (time.time() - start) * 1000, details={"percent": used_pct})
        except Exception as e:
            return HealthCheckResult("memory", "unhealthy", (time.time() - start) * 1000, str(e))

    def _check_cpu(self) -> HealthCheckResult:
        start = time.time()
        try:
            if psutil is None or not hasattr(os, "getloadavg"):
                return HealthCheckResult(
                    "cpu",
                    "degraded",
                    (time.time() - start) * 1000,
                    "psutil or loadavg unavailable",
                )
            load_avg = os.getloadavg()[0]
            cpu_count = psutil.cpu_count()
            load_pct = (load_avg / cpu_count) * 100
            if load_pct > CPU_MAX_PCT:
                return HealthCheckResult(
                    "cpu", "degraded", (time.time() - start) * 1000,
                    f"CPU load {load_pct:.1f}% > {CPU_MAX_PCT}%",
                    {"load_pct": load_pct, "load_avg": load_avg}
                )
            return HealthCheckResult("cpu", "healthy", (time.time() - start) * 1000, details={"load_pct": load_pct})
        except Exception as e:
            return HealthCheckResult("cpu", "unhealthy", (time.time() - start) * 1000, str(e))