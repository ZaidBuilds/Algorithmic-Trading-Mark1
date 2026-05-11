"""
HTTP health endpoint server for QuantumTrade.

Exposes /health/live, /health/ready, and /health endpoints.
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from .health import HealthChecker

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    checker: Optional[HealthChecker] = None

    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if self.path == "/health/live":
            self._handle_liveness()
        elif self.path == "/health/ready":
            self._handle_readiness()
        elif self.path == "/health":
            self._handle_health()
        else:
            self._send_json(404, {"error": "Not found"})

    def _handle_liveness(self):
        if self.checker is None:
            self._send_json(200, {"status": "alive", "timestamp": self._timestamp()})
            return
        result = self.checker.check_liveness()
        self._send_json(200, result)

    def _handle_readiness(self):
        if self.checker is None:
            self._send_json(503, {"status": "unhealthy", "error": "No health checker configured"})
            return
        result = self.checker.check_readiness()
        status_code = 200 if result["status"] == "healthy" else 503
        self._send_json(status_code, result)

    def _handle_health(self):
        if self.checker is None:
            self._send_json(503, {"status": "unhealthy", "error": "No health checker configured"})
            return
        result = self.checker.check_all()
        if result["status"] == "healthy":
            status_code = 200
        elif result["status"] == "degraded":
            status_code = 207
        else:
            status_code = 503
        self._send_json(status_code, result)

    def _timestamp(self):
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


class HealthServer:
    def __init__(self, port: int = 8080, checker: Optional[HealthChecker] = None):
        self.port = port
        self.checker = checker
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, daemon: bool = True):
        HealthHandler.checker = self.checker
        self._server = HTTPServer(("0.0.0.0", self.port), HealthHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=daemon)
        self._thread.start()
        logger.info(f"Health server started on port {self.port}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            logger.info("Health server stopped")

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()


def run_health_server(port: int = 8080, checker: Optional[HealthChecker] = None, daemon: bool = True):
    server = HealthServer(port=port, checker=checker)
    server.start(daemon=daemon)
    return server