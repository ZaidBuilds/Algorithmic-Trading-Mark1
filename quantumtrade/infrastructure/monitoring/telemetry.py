"""
Convenience module to initialize all telemetry: logging, metrics, and tracing.
Call once at startup: telemetry.initialize_all()
"""

import os
import logging
from typing import Optional

# Import the individual setup functions
from monitoring.logger import setup_logger
from monitoring.metrics import setup_metrics_endpoint as setup_metrics
from monitoring.tracing import setup_tracing


def initialize_all(
    service_name: str = "quantumtrade",
    service_version: str = "2.0.0",
    jaeger_endpoint: Optional[str] = None,
    prometheus_port: int = 8000,
    log_level: str = "INFO",
    sample_rate: float = 0.1,
) -> None:
    """
    Initialize all telemetry components (logging, metrics, tracing).
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        jaeger_endpoint: Jaeger collector endpoint (if None, uses env var or default)
        prometheus_port: Port for Prometheus metrics endpoint
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        sample_rate: Sampling rate for tracing (0.0 to 1.0)
    """
    # Setup logging first so we can log the initialization
    setup_logger(
        name=service_name,
        log_file=f"{service_name}.log",
        log_dir="logs",
        level=log_level,
        console_level=log_level,
    )
    
    # Setup metrics endpoint
    setup_metrics(prometheus_port)
    
    # Setup tracing
    if jaeger_endpoint is None:
        jaeger_endpoint = os.getenv(
            "OTEL_EXPORTER_JAEGER_ENDPOINT", 
            "http://localhost:14268/api/traces"
        )
    
    setup_tracing(
        service_name=service_name,
        jaeger_endpoint=jaeger_endpoint,
        sample_rate=sample_rate,
    )
    
    logger = logging.getLogger(__name__)
    logger.info(
        "All telemetry initialized",
        extra={
            "service": service_name,
            "version": service_version,
            "jaeger_endpoint": jaeger_endpoint,
            "prometheus_port": prometheus_port,
            "log_level": log_level,
            "sample_rate": sample_rate,
        }
    )


def initialize_logging_only(
    service_name: str = "quantumtrade",
    service_version: str = "2.0.0",
    log_level: str = "INFO",
) -> None:
    """Initialize only logging (for testing or when metrics/tracing not needed)."""
    setup_logger(
        name=service_name,
        log_file=f"{service_name}.log",
        log_dir="logs",
        level=log_level,
        console_level=log_level,
    )


def initialize_metrics_only(
    service_name: str = "quantumtrade",
    service_version: str = "2.0.0",
    prometheus_port: int = 8000,
) -> None:
    """Initialize only metrics (for testing or when logging/tracing not needed)."""
    setup_metrics(prometheus_port)


def initialize_tracing_only(
    service_name: str = "quantumtrade",
    jaeger_endpoint: Optional[str] = None,
    sample_rate: float = 0.1,
) -> None:
    """Initialize only tracing (for testing or when logging/metrics not needed)."""
    if jaeger_endpoint is None:
        jaeger_endpoint = os.getenv(
            "OTEL_EXPORTER_JAEGER_ENDPOINT", 
            "http://localhost:14268/api/traces"
        )
    
    setup_tracing(
        service_name=service_name,
        jaeger_endpoint=jaeger_endpoint,
        sample_rate=sample_rate,
    )