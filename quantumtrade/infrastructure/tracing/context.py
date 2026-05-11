from opentelemetry import trace
from contextlib import contextmanager
import logging
from typing import Generator, Any, Dict, Optional


def get_tracer(name: str):
    """Get a tracer for manual spans."""
    return trace.get_tracer(name)


@contextmanager
def span(name: str, tracer_name: str = __name__, **attributes) -> Generator[trace.Span, None, None]:
    """Context manager for creating a span with attributes."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span


def get_trace_id() -> Optional[str]:
    """Get the current trace ID for logging injection."""
    current_span = trace.get_current_span()
    if current_span:
        trace_id = trace.format_trace_id(current_span.get_span_context().trace_id)
        return trace_id
    return None


def get_span_id() -> Optional[str]:
    """Get the current span ID for logging injection."""
    current_span = trace.get_current_span()
    if current_span:
        span_id = trace.format_span_id(current_span.get_span_context().span_id)
        return span_id
    return None


def traced(operation: str):
    """Decorator to automatically create a span for a function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with span(operation, args=str(args), kwargs=str(kwargs)):
                return func(*args, **kwargs)
        return wrapper
    return decorator