"""
Unit tests for FillSimulator.

Tests cover:
- Fixed slippage model
- Volume-based slippage scaling
- Unlimited liquidity mode
- Spread cost calculation
- Full execution simulation
"""

import pytest
from datetime import datetime
from decimal import Decimal
import random

from quantumtrade.adapters.execution.models import BrokerOrder, OrderSide
from quantumtrade.adapters.execution.fill_simulator import FillSimulator, create_simulator
from quantumtrade.adapters.execution.cost_models import (
    VolumeBasedSlippageModel,
    SpreadCostModel,
    MarketImpactModel,
)


@pytest.fixture
def sample_order():
    """Create a sample market buy order for testing."""
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        order_type="MARKET",
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_bar():
    """Create a sample OHLCV bar."""
    return {
        "close": 150.0,
        "volume": 1_000_000,
        "timestamp": datetime.now(),
        "high": 151.0,
        "low": 149.0,
    }


class TestFillSimulatorBasics:
    """Test basic FillSimulator behavior."""

    def test_simulate_fill_returns_fill(self, sample_order, sample_bar):
        sim = FillSimulator(
            slippage_model="fixed",
            fixed_slippage_bps=1.0,
            fill_probability=1.0,
            unlimited_liquidity=True,
        )
        fill = sim.simulate_fill(sample_order, sample_bar)
        assert fill is not None
        assert fill.quantity > 0
        assert fill.price > 0

    def test_fill_quantity_full_order(self, sample_order, sample_bar):
        sim = FillSimulator(unlimited_liquidity=True, fill_probability=1.0)
        fill = sim.simulate_fill(sample_order, sample_bar)
        assert fill.quantity == sample_order.quantity

    def test_fill_partial_when_limited(self, sample_order, sample_bar):
        # Without unlimited liquidity, may be partial due to bar volume limits
        sim = FillSimulator(unlimited_liquidity=False, fill_probability=1.0)
        fill = sim.simulate_fill(sample_order, sample_bar)
        # bar_volume = 1e6, participation_rate=0.1 => 100k shares max, greater than 1000
        assert fill.quantity >= 1  # At least some fill
        # quantity likely full because bar volume large enough
        assert fill.quantity == sample_order.quantity  # since bar volume high

    def test_fill_probability(self, sample_order, sample_bar, monkeypatch):
        """Test that fill_probability controls whether fill occurs."""
        sim = FillSimulator(fill_probability=0.0)
        # Monkeypatch random to guarantee >0 -> no fill
        monkeypatch.setattr(random, 'random', lambda: 0.5)
        fill = sim.simulate_fill(sample_order, sample_bar)
        assert fill is None

    def test_zero_remaining_quantity(self, sample_order, sample_bar):
        """No fill if order already filled."""
        sample_order.filled_quantity = sample_order.quantity
        sim = FillSimulator(unlimited_liquidity=True)
        fill = sim.simulate_fill(sample_order, sample_bar)
        assert fill is None


class TestSlippageModels:
    """Test slippage calculation accuracy."""

    def test_fixed_slippage_buy_price(self, sample_order, sample_bar):
        sim = FillSimulator(slippage_model="fixed", fixed_slippage_bps=10.0)
        fill = sim.simulate_fill(sample_order, sample_bar)
        # Buy: price should be higher than close by ~10bps
        expected = 150.0 * (1 + 10/10000)
        assert abs(fill.price - expected) < 0.01  # tolerance for rounding

    def test_fixed_slippage_sell_price(self, sample_bar):
        order = BrokerOrder(symbol="AAPL", side=OrderSide.SELL, quantity=500, timestamp=datetime.now())
        sim = FillSimulator(slippage_model="fixed", fixed_slippage_bps=10.0)
        fill = sim.simulate_fill(order, sample_bar)
        # Sell: price lower by 10bps
        expected = 150.0 * (1 - 10/10000)
        assert abs(fill.price - expected) < 0.01

    def test_volume_based_slippage_with_adv(self, sample_order, sample_bar):
        # Use volume model with default impact_factor=1.0
        sim = FillSimulator(slippage_model="volume")
        # Directly calculate expected slippage
        adv = 1_000_000  # avg daily volume
        part = sample_order.quantity / adv  # 0.001 = 0.1%
        expected_bps = part * 1.0 * 10000  # ~10 bps
        fill = sim.simulate_fill(sample_order, sample_bar, avg_daily_volume=adv)
        assert fill is not None
        # The fill price should reflect slippage ~10bps above close for buy
        approx_price = 150.0 * (1 + expected_bps/10000)
        # Not exact because order book influences base_price but within range
        assert fill.price > 150.0  # Should be higher due to slippage


class TestSpreadCost:
    """Test spread cost calculation via SpreadCostModel."""

    def test_spread_cost_buy(self, sample_order):
        model = SpreadCostModel()
        # For buy: ideal mid, actual paid ask
        bid = 149.9
        ask = 150.1
        mid = (bid + ask) / 2
        fill_price = ask  # typical market buy
        cost_bps = model.calculate_spread_cost(
            side=OrderSide.BUY,
            fill_price=fill_price,
            bid_price=bid,
            ask_price=ask,
            quantity=1000,
        )
        expected_spread = (ask - mid) / mid * 10000
        assert abs(cost_bps - expected_spread) < 0.01

    def test_spread_cost_sell(self, sample_order):
        model = SpreadCostModel()
        bid = 149.9
        ask = 150.1
        mid = (bid + ask) / 2
        # Sell receives bid
        cost_bps = model.calculate_spread_cost(
            side=OrderSide.SELL,
            fill_price=bid,
            bid_price=bid,
            ask_price=ask,
            quantity=1000,
        )
        expected_spread = (mid - bid) / mid * 10000
        assert abs(cost_bps - expected_spread) < 0.01


class TestMarketImpact:
    """Test market impact model."""

    def test_impact_scales_with_participation(self):
        model = MarketImpactModel(permanent_coeff=0.1, temporary_coeff=0.05)
        adv = 10_000_000
        impact1 = model.calculate_impact(OrderSide.BUY, 100_000, adv, 100.0)
        impact2 = model.calculate_impact(OrderSide.BUY, 1_000_000, adv, 100.0)
        # Larger order → higher impact
        assert impact1["total_bps"] < impact2["total_bps"]


class TestFullSimulation:
    """End-to-end execution simulation."""

    def test_simulate_order_execution_multiple_bars(self, sample_order):
        sim = FillSimulator(unlimited_liquidity=True)
        bars = [
            {"close": 100, "volume": 500_000, "timestamp": datetime(2024,1,1,9,30)},
            {"close": 101, "volume": 600_000, "timestamp": datetime(2024,1,1,9,31)},
            {"close": 102, "volume": 700_000, "timestamp": datetime(2024,1,1,9,32)},
        ]
        fills = sim.simulate_order_execution(sample_order, bars)
        total_qty = sum(f.quantity for f in fills)
        assert total_qty == sample_order.quantity

    def test_factory_creation(self):
        config = {"slippage_model": "fixed", "fixed_slippage_bps": 2.5, "unlimited_liquidity": True}
        sim = create_simulator(config)
        assert sim.slippage_model_type == "fixed"
        assert sim.fixed_slippage_bps == 2.5
        assert sim.unlimited_liquidity is True
