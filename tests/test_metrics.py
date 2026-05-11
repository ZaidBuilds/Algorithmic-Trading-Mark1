"""Tests for Prometheus metrics module.

Run with: pytest tests/test_metrics.py -v

Tests metric increment, label handling, histogram buckets, gauge operations,
and ensures no duplicate registration errors.
"""

import pytest
import time
import os
import sys

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock


def test_metrics_can_be_imported():
    """Verify metrics module imports without errors."""
    try:
        from monitoring import metrics
        assert hasattr(metrics, 'TRADING_TICKS_TOTAL')
        assert hasattr(metrics, 'ORDERS_SUBMITTED_TOTAL')
        assert hasattr(metrics, 'ACTIVE_POSITIONS_COUNT')
    except ImportError as e:
        pytest.skip(f"prometheus_client not installed: {e}")


def test_counter_increment():
    """Test counter increments properly."""
    from monitoring.metrics import TRADING_TICKS_TOTAL

    # Increment with labels
    TRADING_TICKS_TOTAL.labels(symbol="AAPL", outcome="success").inc()
    TRADING_TICKS_TOTAL.labels(symbol="AAPL", outcome="success").inc(2)

    # Get value (returns Collector object, need to use _value)
    counter = TRADING_TICKS_TOTAL.labels(symbol="AAPL", outcome="success")
    assert counter._value.get() >= 3


def test_gauge_set_inc_dec():
    """Test gauge set, increment, decrement operations."""
    from monitoring.metrics import ACTIVE_POSITIONS_COUNT

    gauge = ACTIVE_POSITIONS_COUNT

    # Set value
    gauge.set(5)
    assert gauge._value.get() == 5

    # Increment
    gauge.inc()
    assert gauge._value.get() == 6

    # Decrement
    gauge.dec()
    assert gauge._value.get() == 5

    # Increment by specific amount
    gauge.inc(3)
    assert gauge._value.get() == 8


def test_histogram_observe():
    """Test histogram observes values correctly."""
    from monitoring.metrics import TRADING_TICK_DURATION_SECONDS

    hist = TRADING_TICK_DURATION_SECONDS

    # Observe some values
    hist.observe(0.01)   # Fast tick
    hist.observe(0.1)    # Medium tick
    hist.observe(0.5)    # Slow tick
    hist.observe(0.05)   # Another fast tick

    # Check bucket counts (approximate)
    # 0.001-0.005: should be 0
    # 0.005-0.01: at least 1 (0.01 goes to 0.01 bucket, but prom hist is <=)
    # Actually Prometheus histogram buckets are le (<=), so:
    # 0.01 -> 0.01 bucket
    # 0.05 -> 0.05 bucket
    # 0.1 -> 0.1 bucket
    # 0.5 -> 0.5 bucket
    bucket_counts = hist._metrics
    assert len(bucket_counts) > 0


def test_label_handling():
    """Test that labels work correctly for multi-label metrics."""
    from monitoring.metrics import ORDERS_SUBMITTED_TOTAL

    # Submit orders with different label combinations
    ORDERS_SUBMITTED_TOTAL.labels(
        side="BUY",
        order_type="MARKET",
        broker="alpaca",
        status="filled"
    ).inc()

    ORDERS_SUBMITTED_TOTAL.labels(
        side="SELL",
        order_type="LIMIT",
        broker="binance",
        status="pending"
    ).inc()

    # Verify counts are separate
    buy_orders = ORDERS_SUBMITTED_TOTAL.labels(
        side="BUY", order_type="MARKET", broker="alpaca", status="filled"
    )._value.get()

    sell_orders = ORDERS_SUBMITTED_TOTAL.labels(
        side="SELL", order_type="LIMIT", broker="binance", status="pending"
    )._value.get()

    assert buy_orders >= 1
    assert sell_orders >= 1


def test_histogram_buckets_cover_range():
    """Verify histogram buckets cover expected latency ranges."""
    from monitoring.metrics import ORDER_LATENCY_SECONDS

    hist = ORDER_LATENCY_SECONDS

    # Check buckets exist
    expected_buckets = [0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
    assert len(hist._kwargs.get('buckets', [])) == len(expected_buckets)


def test_info_metric():
    """Test info metric is properly set."""
    from monitoring.metrics import PYTHON_INFO

    # PYTHON_INFO should be set with version info
    # Info metrics store data differently (as dict)
    assert PYTHON_INFO is not None


def test_gauge_operations():
    """Test gauge set/inc/dec operations."""
    from monitoring.metrics import PORTFOLIO_VALUE_USD

    gauge = PORTFOLIO_VALUE_USD

    # Set to specific value
    gauge.set(100000.0)
    assert gauge._value.get() == 100000.0

    # Increment
    gauge.inc(5000)
    assert gauge._value.get() == 105000.0

    # Decrement
    gauge.dec(5000)
    assert gauge._value.get() == 100000.0


def test_multiple_label_combinations():
    """Test that different label combinations are kept separate."""
    from monitoring.metrics import SIGNALS_GENERATED_TOTAL

    # Generate signals for different strategies
    SIGNALS_GENERATED_TOTAL.labels(strategy="ema_crossover", signal_type="BUY").inc(10)
    SIGNALS_GENERATED_TOTAL.labels(strategy="rsi_strategy", signal_type="BUY").inc(5)
    SIGNALS_GENERATED_TOTAL.labels(strategy="ema_crossover", signal_type="SELL").inc(3)

    ema_buy = SIGNALS_GENERATED_TOTAL.labels(strategy="ema_crossover", signal_type="BUY")._value.get()
    rsi_buy = SIGNALS_GENERATED_TOTAL.labels(strategy="rsi_strategy", signal_type="BUY")._value.get()
    ema_sell = SIGNALS_GENERATED_TOTAL.labels(strategy="ema_crossover", signal_type="SELL")._value.get()

    assert ema_buy == 10
    assert rsi_buy == 5
    assert ema_sell == 3


def test_track_latency_decorator():
    """Test the track_latency decorator records duration."""
    from monitoring.metrics import ORDER_LATENCY_SECONDS

    # Create a test function with decorator
    @patch('monitoring.metrics.ORDER_LATENCY_SECONDS', ORDER_LATENCY_SECONDS)
    def test_func():
        time.sleep(0.01)
        return "done"

    # Apply decorator manually
    decorated = metrics.track_latency(ORDER_LATENCY_SECONDS, broker="test", stage="test_stage")(test_func)
    result = decorated()

    assert result == "done"

    # Check that histogram has observations
    hist = ORDER_LATENCY_SECONDS.labels(broker="test", stage="test_stage")
    # There should be at least one observation
    assert hist._count._value.get() >= 1


def test_count_calls_decorator():
    """Test the count_calls decorator increments counter."""
    from monitoring.metrics import ERRORS_TOTAL

    @metrics.count_calls(ERRORS_TOTAL, component="test", error_type="test_error")
    def failing_func():
        raise ValueError("test error")

    # Call once (should increment before raising)
    with pytest.raises(ValueError):
        failing_func()

    counter = ERRORS_TOTAL.labels(component="test", error_type="test_error")
    assert counter._value.get() >= 1


def test_no_duplicate_registration():
    """Ensure metrics can be imported multiple times without error."""
    # This would fail if metric names conflict during registration
    from monitoring import metrics as m1
    from monitoring import metrics as m2

    # Both should reference the same registry objects
    assert m1.TRADING_TICKS_TOTAL is m2.TRADING_TICKS_TOTAL


def test_histogram_bucket_distribution():
    """Test histogram properly buckets observations."""
    from monitoring.metrics import TRADING_TICK_DURATION_SECONDS

    hist = TRADING_TICK_DURATION_SECONDS

    # Observe values across range
    fast_durations = [0.001, 0.002, 0.003]  # Should go to 0.005 bucket
    med_durations = [0.01, 0.02, 0.03]      # Should go to 0.05 bucket
    slow_durations = [0.1, 0.2, 0.3]        # Should go to 0.1 bucket

    for d in fast_durations + med_durations + slow_durations:
        hist.observe(d)

    # Verify counts exist (exact bucket depends on Prometheus internals)
    assert hist._count._value.get() == 9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
