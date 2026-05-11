"""
Tests for latency simulation models.

Covers:
- LatencyModel random sampling
- Price shift calculation based on volatility
- FixedLatencyModel
- LatencyDistribution multi-component
"""

import pytest
import numpy as np
from quantumtrade.backtesting.simulation.latency import (
    LatencyModel,
    FixedLatencyModel,
    LatencyDistribution,
)


class TestLatencyModel:
    """Basic latency model with normal distribution."""

    def test_mean_latency(self):
        model = LatencyModel(mean_latency_ms=200, std_latency_ms=0)
        latency = model.sample_latency()
        assert latency == pytest.approx(200.0, abs=1e-6)

    def test_latency_clipping(self):
        # Values should be clipped to min/max
        model = LatencyModel(mean_latency_ms=100, std_latency_ms=10, min_latency_ms=50, max_latency_ms=150)
        rng = np.random.default_rng(42)
        for _ in range(100):
            latency = model.sample_latency(rng)
            assert 50 <= latency <= 150

    def test_price_shift_direction(self):
        model = LatencyModel()
        price = 100.0
        volatility = 0.20  # 20% annual

        shift_buy = model.calculate_price_shift(150, volatility, price, "BUY")
        shift_sell = model.calculate_price_shift(150, volatility, price, "SELL")

        # Buy shifts up, sell shifts down
        assert shift_buy > price
        assert shift_sell < price

        # Magnitudes equal (same volatility, same latency)
        assert abs(shift_buy - price) == pytest.approx(abs(shift_sell - price))

    def test_estimate_slippage_bps(self):
        model = LatencyModel(mean_latency_ms=200)
        volatility = 0.25
        price = 50.0
        bps = model.estimate_slippage_bps(200, volatility, price)
        # Should be positive but small (typically < 1 bps for 200ms)
        assert bps >= 0.0
        assert bps < 10.0  # Sanity check: 200ms shouldn't move more than 10 bps for 25% vol

    def test_zero_latency_no_shift(self):
        model = LatencyModel()
        price = model.calculate_price_shift(0, 0.20, 100.0, "BUY")
        assert price == pytest.approx(100.0)

    def test_zero_volatility_no_shift(self):
        model = LatencyModel()
        price = model.calculate_price_shift(150, 0.0, 100.0, "BUY")
        assert price == pytest.approx(100.0)


class TestFixedLatencyModel:
    """Deterministic latency."""

    def test_fixed_value(self):
        model = FixedLatencyModel(fixed_latency_ms=250.0)
        assert model.sample_latency() == pytest.approx(250.0)


class TestLatencyDistribution:
    """Multi-component latency model."""

    def test_total_latency_positive(self):
        dist = LatencyDistribution()
        total = dist.sample_total_latency()
        assert total > 0

    def test_components_add(self):
        dist = LatencyDistribution(
            network_mean_ms=100,
            broker_mean_ms=200,
            exchange_mean_ms=50,
        )
        rng = np.random.default_rng(123)
        # Average total over many samples ≈ sum of means
        samples = [dist.sample_total_latency(rng) for _ in range(1000)]
        avg_total = np.mean(samples)
        # Should be roughly 350ms plus some variance
        assert avg_total == pytest.approx(350.0, rel=0.3)

    def test_reproducibility_with_seed(self):
        dist = LatencyDistribution()
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        s1 = dist.sample_total_latency(rng1)
        s2 = dist.sample_total_latency(rng2)
        assert s1 == pytest.approx(s2)


class TestLatencyPriceShiftCalculations:
    """More detailed tests of the price shift formula."""

    def test_shift_scales_with_sqrt_time(self):
        """Longer latency → larger price movement."""
        model = LatencyModel()
        price = 100.0
        vol = 0.20
        shift_short = model.calculate_price_shift(50, vol, price, "BUY")
        shift_long = model.calculate_price_shift(200, vol, price, "BUY")
        assert shift_long - price > shift_short - price

    def test_shift_scales_with_volatility(self):
        """Higher volatility → larger shift."""
        model = LatencyModel()
        price = 100.0
        latency = 100
        shift_low = model.calculate_price_shift(latency, 0.10, price, "BUY")
        shift_high = model.calculate_price_shift(latency, 0.30, price, "BUY")
        assert shift_high > shift_low

    def test_bps_estimate_small(self):
        """Latency slippage should be sub-bps for typical values."""
        model = LatencyModel(mean_latency_ms=150)
        bps = model.estimate_slippage_bps(150, 0.20, 100.0)
        # 150ms at 20% annual vol → tiny price movement
        assert bps < 1.0  # less than 1 basis point
