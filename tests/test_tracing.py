"""
Tests for distributed tracing functionality.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Set environment variables before importing tracing modules
os.environ["OTEL_EXPORTER_JAEGER_ENDPOINT"] = "http://localhost:14268/api/traces"
os.environ["OTEL_SAMPLING_RATIO"] = "0.1"
os.environ["OTEL_SERVICE_NAME"] = "quantumtrade"

from monitoring.tracing import setup_tracing, get_tracer
from tracing.context import span, get_trace_id, get_span_id, traced
from tracing.instrumentation import (
    trading_tick_span,
    data_fetch_span,
    signal_generation_span,
    risk_check_span,
    order_execution_span,
)


def test_setup_tracing():
    """Test that tracing is set up correctly."""
    with patch('opentelemetry.sdk.trace.export.BatchSpanProcessor') as mock_processor, \
         patch('opentelemetry.exporter.jaeger.thrift.JaegerExporter') as mock_exporter:
        
        # Setup
        setup_tracing(
            service_name="test-service",
            jaeger_endpoint="http://test:14268/api/traces",
            sample_rate=0.5
        )
        
        # Verify exporter was called with correct endpoint
        mock_exporter.assert_called_once_with(
            collector_endpoint="http://test:14268/api/traces"
        )
        
        # Verify span processor was added
        mock_processor.assert_called_once()
        
        # Verify tracer provider was set
        from opentelemetry import trace
        tracer_provider = trace.get_tracer_provider()
        assert tracer_provider is not None


def test_get_tracer():
    """Test getting a tracer."""
    tracer = get_tracer("test.tracer")
    assert tracer is not None
    # Should be able to start a span
    with tracer.start_as_current_span("test_span") as span:
        span.set_attribute("test.key", "test.value")


def test_span_context_manager():
    """Test the span context manager."""
    with span("test_operation", key1="value1", key2="value2") as current_span:
        assert current_span is not None
        # Check that attributes were set (we can't easily get them back, but we can check it didn't fail)
        assert hasattr(current_span, 'set_attribute')


def test_get_trace_id():
    """Test getting trace ID."""
    # Outside a span, should return None
    assert get_trace_id() is None
    
    # Inside a span, should return a trace ID
    with span("test_span"):
        trace_id = get_trace_id()
        assert trace_id is not None
        assert isinstance(trace_id, str)
        assert len(trace_id) == 32  # Trace ID is 32 hex characters


def test_get_span_id():
    """Test getting span ID."""
    # Outside a span, should return None
    assert get_span_id() is None
    
    # Inside a span, should return a span ID
    with span("test_span"):
        span_id = get_span_id()
        assert span_id is not None
        assert isinstance(span_id, str)
        assert len(span_id) == 16  # Span ID is 16 hex characters


def test_traced_decorator():
    """Test the traced decorator."""
    @traced("test_function")
    def test_func(x, y):
        return x + y
    
    # Function should work normally
    result = test_func(2, 3)
    assert result == 5
    
    # And should have created a span (we can't easily test the span was created without mocking)
    # But we can at least verify it doesn't throw an exception


def test_trading_tick_span():
    """Test trading tick span creation."""
    span_ctx = trading_tick_span(symbols_processed=5)
    assert span_ctx is not None
    # The span context manager should work
    with span_ctx as current_span:
        assert current_span is not None


def test_data_fetch_span():
    """Test data fetch span creation."""
    span_ctx = data_fetch_span("AAPL", success=True, duration_ms=15.5)
    assert span_ctx is not None
    with span_ctx as current_span:
        assert current_span is not None


def test_signal_generation_span():
    """Test signal generation span creation."""
    span_ctx = signal_generation_span(
        symbol="AAPL",
        strategy="EMA_Crossover",
        signal_type="BUY",
        confidence=0.85,
        price=150.25
    )
    assert span_ctx is not None
    with span_ctx as current_span:
        assert current_span is not None


def test_risk_check_span():
    """Test risk check span creation."""
    span_ctx = risk_check_span(
        symbol="AAPL",
        quantity=10.0,
        price=150.25,
        portfolio_value=10000.0,
        approved=True
    )
    assert span_ctx is not None
    with span_ctx as current_span:
        assert current_span is not None


def test_order_execution_span():
    """Test order execution span creation."""
    span_ctx = order_execution_span(
        symbol="AAPL",
        side="BUY",
        quantity=10.0,
        order_type="MARKET",
        success=True,
        order_id="12345"
    )
    assert span_ctx is not None
    with span_ctx as current_span:
        assert current_span is not None
    
    # Test without order_id and error
    span_ctx2 = order_execution_span(
        symbol="GOOGL",
        side="SELL",
        quantity=5.0,
        order_type="LIMIT",
        success=False,
        error="Insufficient funds"
    )
    assert span_ctx2 is not None
    with span_ctx2 as current_span:
        assert current_span is not None


def test_tracing_integration_with_logging():
    """Test that trace IDs can be injected into logs."""
    import logging
    from monitoring.structured_logging import QuantumTradeFormatter
    
    # Create a logger with structured formatting
    logger = logging.getLogger("test_integration")
    logger.setLevel(logging.INFO)
    
    # Mock handler to capture log records
    log_records = []
    class MockHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record)
    
    handler = MockHandler()
    formatter = QuantumTradeFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Test outside span
    logger.info("Test message outside span")
    assert len(log_records) == 1
    record = log_records[0]
    # Should not have trace_id field when outside span
    assert not hasattr(record, 'trace_id') or record.trace_id is None
    
    # Clear records
    log_records.clear()
    
    # Test inside span
    with span("test_span"):
        logger.info("Test message inside span")
        assert len(log_records) == 1
        record = log_records[0]
        # Should have trace_id field
        assert hasattr(record, 'trace_id')
        assert record.trace_id is not None
        assert len(record.trace_id) == 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])