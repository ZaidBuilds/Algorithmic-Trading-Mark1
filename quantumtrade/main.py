"""
QuantumTrade Main Entry Point

Starts health/metrics server on port 8080, FastAPI server on port 8000,
and initializes OpenTelemetry tracing with graceful signal handling.
"""

import asyncio
import logging
import os
import signal
from typing import Optional

from monitoring.health_endpoint import HealthServer, run_health_server
from monitoring.metrics_endpoint import start_metrics_endpoint
from monitoring.tracing import setup_tracing
from quantumtrade.interfaces.http.api_server import app

logger = logging.getLogger(__name__)


class QuantumTradeApplication:
    def __init__(self):
        self.health_thread: Optional[object] = None
        self.metrics_thread: Optional[object] = None
        self.uvicorn_server: Optional[object] = None
        self._shutdown_event = asyncio.Event()

    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers."""
        loop = asyncio.get_event_loop()

        def handle_signal(sig):
            logger.info(f"Received signal {sig}, initiating graceful shutdown...")
            self._shutdown_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    def _start_health_metrics_server(self):
        """Start health server on port 8080 and metrics on port 9090."""
        logger.info("Starting health server on port 8080...")
        self.health_thread = run_health_server(port=8080)
        logger.info("Health server started with /health/live and /health/ready endpoints")

        logger.info("Starting metrics endpoint on port 9090...")
        self.metrics_thread = start_metrics_endpoint(port=9090)
        logger.info("Metrics endpoint started")

    async def _start_api_server(self):
        """Start the FastAPI/Uvicorn server on port 8000."""
        import uvicorn

        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
        )
        self.uvicorn_server = uvicorn.Server(config)

        logger.info("Starting FastAPI server on port 8000...")
        server_task = asyncio.create_task(self.uvicorn_server.serve())
        return server_task

    async def run(self):
        """Run the application with both servers."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        jaeger_endpoint = os.getenv(
            "JAEGER_ENDPOINT", "http://localhost:14268/api/traces"
        )
        sample_rate = float(os.getenv("TRACING_SAMPLE_RATE", "0.1"))

        try:
            setup_tracing(
                service_name="quantumtrade",
                jaeger_endpoint=jaeger_endpoint,
                sample_rate=sample_rate,
            )
            logger.info("OpenTelemetry tracing initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize tracing: {e}")

        self._start_health_metrics_server()
        self._setup_signal_handlers()

        server_task = await self._start_api_server()

        await self._shutdown_event.wait()

        logger.info("Shutting down servers...")

        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
            await server_task
            logger.info("FastAPI server stopped")

        logger.info("Shutdown complete")


def main():
    asyncio.run(QuantumTradeApplication().run())


if __name__ == "__main__":
    main()