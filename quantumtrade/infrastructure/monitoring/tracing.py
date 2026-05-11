from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
try:
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
except Exception:  # pragma: no cover
    JaegerExporter = None

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
import os
import logging


def setup_tracing(service_name: str = "quantumtrade", 
                  jaeger_endpoint: str = "http://localhost:14268/api/traces",
                  sample_rate: float = 0.1):
    """Initialize OpenTelemetry distributed tracing."""
    # Resource
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "2.0.0",
        "deployment.environment": os.getenv("ENV", "development")
    })
    
    # Tracer provider with sampling
    sampler = ParentBased(root=TraceIdRatioBased(sample_rate))
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)
    
    # Jaeger exporter
    if JaegerExporter is None:
        logger = logging.getLogger(__name__)
        logger.warning(
            "Jaeger exporter package is not installed; tracing is disabled.")
        return

    jaeger_exporter = JaegerExporter(
        collector_endpoint=jaeger_endpoint,
    )

    # Span processor (batch for performance)
    span_processor = BatchSpanProcessor(jaeger_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)
    
    # Auto-instrument libraries
    RedisInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Tracing initialized", extra={
        "service": service_name, 
        "jaeger": jaeger_endpoint,
        "sample_rate": sample_rate
    })


def get_tracer(name: str):
    """Get a tracer for manual spans."""
    return trace.get_tracer(name)