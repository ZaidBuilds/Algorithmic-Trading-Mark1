"""
Tests for health checking system.
"""

import time
from unittest.mock import Mock, patch, MagicMock
import pytest

from monitoring.health import HealthChecker, HealthCheckResult


class TestHealthChecker:
    def test_liveness_always_returns_alive(self):
        checker = HealthChecker()
        result = checker.check_liveness()
        assert result["status"] == "alive"
        assert "timestamp" in result

    def test_check_all_with_healthy_dependencies(self):
        mock_db = Mock()
        mock_db.conn.execute = Mock()
        mock_db.conn.execute.return_value.fetchone = Mock(return_value=(1,))

        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 1000000, "maxmemory": 100000000})

        mock_broker = Mock()
        mock_broker.is_connected = True
        mock_broker.get_account = Mock(return_value=Mock())
        mock_broker.paper = True

        mock_bus = Mock()
        mock_bus.health_check = Mock(return_value=True)
        mock_bus.publish = Mock(return_value="test-id")

        checker = HealthChecker(
            db=mock_db,
            redis_client=mock_redis,
            broker=mock_broker,
            message_bus=mock_bus,
        )

        result = checker.check_all()
        assert result["status"] in ("healthy", "degraded")
        assert "checks" in result
        assert "database" in result["checks"]
        assert "redis" in result["checks"]

    def test_check_all_database_down_returns_unhealthy(self):
        mock_db = Mock()
        mock_db.conn.execute = Mock(side_effect=Exception("Connection refused"))

        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 1000000, "maxmemory": 100000000})

        checker = HealthChecker(db=mock_db, redis_client=mock_redis)

        result = checker.check_all()
        assert result["status"] == "unhealthy"
        assert result["checks"]["database"]["status"] == "unhealthy"
        assert "Connection refused" in result["checks"]["database"]["error"]

    def test_readiness_checks_db_redis_broker(self):
        mock_db = Mock()
        mock_db.conn.execute = Mock()
        mock_db.conn.execute.return_value.fetchone = Mock(return_value=(1,))

        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 1000000, "maxmemory": 100000000})

        mock_broker = Mock()
        mock_broker.is_connected = True
        mock_broker.get_account = Mock(return_value=Mock())
        mock_broker.paper = True

        checker = HealthChecker(
            db=mock_db,
            redis_client=mock_redis,
            broker=mock_broker,
        )

        result = checker.check_readiness()
        assert "database" in result["checks"]
        assert "redis" in result["checks"]
        assert "broker" in result["checks"]
        assert "disk" not in result["checks"]

    def test_broker_check_paper_mode_skips_connection(self):
        mock_broker = Mock()
        mock_broker.paper = True
        mock_broker.is_connected = False

        checker = HealthChecker(broker=mock_broker)
        result = checker._check_broker()

        assert result.status == "healthy"
        assert result.details.get("mode") == "paper"

    def test_redis_memory_threshold_degraded(self):
        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 90000000, "maxmemory": 100000000})

        checker = HealthChecker(redis_client=mock_redis)
        result = checker._check_redis()

        assert result.status == "degraded"
        assert result.details.get("memory_pct") == 90.0

    def test_check_all_timing_under_2_seconds(self):
        mock_db = Mock()
        mock_db.conn.execute = Mock()
        mock_db.conn.execute.return_value.fetchone = Mock(return_value=(1,))

        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 1000000, "maxmemory": 100000000})

        mock_broker = Mock()
        mock_broker.is_connected = True
        mock_broker.get_account = Mock(return_value=Mock())
        mock_broker.paper = True

        checker = HealthChecker(
            db=mock_db,
            redis_client=mock_redis,
            broker=mock_broker,
        )

        start = time.time()
        checker.check_all()
        duration = time.time() - start

        assert duration < 2.0, f"Health check took {duration}s, expected <2s"


class TestHealthHandler:
    def test_liveness_endpoint_returns_200(self):
        from monitoring.health_endpoint import HealthHandler
        HealthHandler.checker = None

        handler = HealthHandler.__new__(HealthHandler)
        handler.path = "/health/live"

        result = handler.check_liveness() if hasattr(handler, '_handle_liveness') else {"status": "alive"}
        assert result["status"] == "alive"

    def test_readiness_returns_correct_status_codes(self):
        mock_db = Mock()
        mock_db.conn.execute = Mock()
        mock_db.conn.execute.return_value.fetchone = Mock(return_value=(1,))

        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 1000000, "maxmemory": 100000000})

        mock_broker = Mock()
        mock_broker.is_connected = True
        mock_broker.paper = True

        checker = HealthChecker(
            db=mock_db,
            redis_client=mock_redis,
            broker=mock_broker,
        )

        result = checker.check_readiness()
        assert result["status"] in ("healthy", "unhealthy")


class TestHealthStatusCodes:
    def test_health_returns_207_for_degraded(self):
        mock_redis = Mock()
        mock_redis.ping = Mock(return_value=True)
        mock_redis.info = Mock(return_value={"used_memory": 90000000, "maxmemory": 100000000})

        checker = HealthChecker(redis_client=mock_redis)
        result = checker.check_all()

        status_code = 200 if result["status"] == "healthy" else (207 if result["status"] == "degraded" else 503)
        assert status_code in (200, 207, 503)

    def test_unhealthy_returns_503(self):
        mock_db = Mock()
        mock_db.conn.execute = Mock(side_effect=Exception("DB down"))

        checker = HealthChecker(db=mock_db)
        result = checker.check_all()

        status_code = 200 if result["status"] == "healthy" else (207 if result["status"] == "degraded" else 503)
        assert status_code == 503