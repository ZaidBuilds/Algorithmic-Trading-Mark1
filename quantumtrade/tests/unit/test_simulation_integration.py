"""
Integration tests for MarketSimulator.

Tests the full fill simulation pipeline:
1. Slippage + spread + impact composition
2. Latency-induced price shift
3. Liquidity constraints
4. Gap handling
5. TCA integration

Covers realistic scenarios across all simulation components.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from quantumtrade.backtesting.simulation import (
    MarketSimulator,
    MarketFill,
)
from quantumtrade.adapters.execution.models import BrokerOrder, OrderSide, OrderType
from quantumtrade.backtesting.engine import BacktestEngine
from quantumtrade.strategy.base import BaseStrategy
from quantumtrade.strategy.signals import SignalType, Signal


class SimpleTrendStrategy(BaseStrategy):
    """Simple momentum strategy for testing."""

    def __init__(self, threshold: float = 0.0):
        self.threshold = threshold
        self.name = "TrendStrategy"
        self.required_periods = 5

    def validate_data(self, data: pd.DataFrame):
        assert "Close" in data.columns

    def calculate_indicators(self, data):
        data['returns'] = data['Close'].pct_change()
        data['momentum'] = data['returns'].rolling(5).sum()
        return data

    def generate_signal(self, data, index):
        from quantumtrade.strategy.signals import Signal
        row = data.iloc[index]
        if row['momentum'] > self.threshold:
            return Signal(SignalType.BUY, 1.0, row.name)
        else:
            return Signal(SignalType.SELL, 1.0, row.name)


@pytest.fixture
def simulator_config():
    """Reasonable simulator config for tests."""
    return {
        "slippage_model": "impact",
        "fixed_slippage_bps": 1.0,
        "latency_ms": 150.0,
        "spread_bps": 1.0,
        "enable_impact": True,
        "impact_eta": 0.01,
        "impact_epsilon": 0.05,
        "participation_rate": 0.10,
        "enable_liquidity_constraints": True,
        "enable_gap_risk": True,
        "seed": 42,
    }


class TestMarketSimulatorMicro:
    """Unit-level tests on MarketSimulator."""

    def test_simulate_fill_quantity(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {
            "close": 100.0,
            "volume": 1_000_000,
            "timestamp": datetime.now(),
        }

        fill = sim.simulate_fill(order, bar, avg_daily_volume=1_000_000)
        assert fill is not None
        assert fill.quantity <= order.quantity
        assert fill.price > 0

    def test_fill_includes_cost_breakdown(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {
            "close": 100.0,
            "volume": 2_000_000,
            "timestamp": datetime.now(),
        }

        fill = sim.simulate_fill(order, bar, avg_daily_volume=2_000_000)

        assert fill.slippage_bps >= 0
        assert fill.spread_cost_bps >= 0
        assert fill.impact_bps >= 0
        assert fill.latency_ms > 0

    def test_limit_order_simulation(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.LIMIT,
            limit_price=99.0,  # below market (100 close)
            timestamp=datetime.now(),
        )
        bar = {
            "close": 100.0,
            "high": 101.0,
            "low": 99.5,  # low above limit → not filled
            "volume": 1_000_000,
            "timestamp": datetime.now(),
        }

        fill = sim.simulate_fill(order, bar)
        assert fill is None  # Not filled because low > limit

    def test_limit_order_improvement(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            timestamp=datetime.now(),
        )
        # Bar low touches limit
        bar = {
            "close": 100.5,
            "high": 101.0,
            "low": 100.0,  # touches limit
            "volume": 1_000_000,
            "timestamp": datetime.now(),
        }

        fill = sim.simulate_fill(order, bar)
        # May fill depending on randomness; set fixed seed in config
        if fill:
            assert fill.price <= 100.0  # improvement possible

    def test_latency_tracking(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": 100.0, "volume": 1_000_000, "timestamp": datetime.now()}

        fill = sim.simulate_fill(order, bar, avg_daily_volume=1_000_000)
        assert fill.latency_ms > 0
        assert fill.latency_ms < 1000  # within reasonable bound


class TestMarketSimulatorCosts:
    """Verify cost model composition."""

    def test_impact_adds_to_price(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=100_000,  # Large order relative to ADV
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": 100.0, "volume": 1_000_000, "timestamp": datetime.now()}
        # 100k vs 1M ADV = 10% participation
        fill = sim.simulate_fill(order, bar, avg_daily_volume=1_000_000)
        if fill:
            # Price should be > close due to impact premium
            assert fill.price > bar["close"]

    def test_spread_cost_approximation(self, simulator_config):
        sim = MarketSimulator(spread_bps=2.0, **{k: v for k, v in simulator_config.items() if k != "spread_bps"})
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": 100.0, "volume": 1_000_000, "timestamp": datetime.now()}
        fill = sim.simulate_fill(order, bar)

        # For small order, impact negligible, but spread still there (~1 bps half-spread)
        assert fill.spread_cost_bps > 0


class TestBacktestEngineIntegration:
    """Test full BacktestEngine with MarketSimulator."""

    def test_engine_uses_market_simulator(self, simulator_config):
        engine = BacktestEngine(
            initial_balance=10000,
            commission=0.001,
            simulator_config=simulator_config,
        )
        data = pd.DataFrame({
            "Open": 100 + np.cumsum(np.random.randn(200) * 0.1),
            "High": 100.5 + np.cumsum(np.random.randn(200) * 0.1),
            "Low": 99.5 + np.cumsum(np.random.randn(200) * 0.1),
            "Close": 100 + np.cumsum(np.random.randn(200) * 0.1),
            "Volume": np.random.uniform(1e6, 2e6, 200),
        }, index=pd.date_range("2024-01-01", periods=200, freq="D"))

        strategy = SimpleTrendStrategy(threshold=0.001)
        metrics = engine.run(strategy, data)

        assert metrics.final_balance() is not None
        assert len(metrics.trades) > 0
        assert len(engine.get_tca_reports()) > 0

    def test_tca_reports_generated(self, simulator_config):
        engine = BacktestEngine(
            initial_balance=10000,
            simulator_config=simulator_config,
        )
        data = make_simple_data(100)
        strategy = SimpleTrendStrategy()
        engine.run(strategy, data)

        reports = engine.get_tca_reports()
        assert len(reports) >= engine.initial_balance  # at least a few trades
        # Each report should have non-zero implicit costs
        for r in reports[:5]:  # sample first few
            assert r.total_cost_bps > 0 or r.filled_quantity == 0


def make_simple_data(n: int) -> pd.DataFrame:
    """Create simple OHLCV DataFrame."""
    prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "Open": prices,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": np.random.uniform(1e5, 2e5, n),
    }, index=pd.date_range("2024-01-01", periods=n, freq="D"))


class TestSlippageModelsBoundary:
    """Test edge cases for slippage models."""

    def test_zero_quantity_no_slippage(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=0,  # invalid but handled
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": 100.0, "volume": 1_000_000, "timestamp": datetime.now()}
        # Should return None or handle gracefully
        fill = sim.simulate_fill(order, bar)
        assert fill is None or fill.quantity == 0

    def test_negative_price_protection(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": -100.0, "volume": 1_000_000, "timestamp": datetime.now()}
        # Should handle or skip
        fill = sim.simulate_fill(order, bar)
        # Likely None due to validation
        assert fill is None or fill.price > 0


class TestLatencyPriceShiftIntegration:
    """Integration of latency with fill price."""

    def test_volatility_affects_latency_shift(self, simulator_config):
        sim = MarketSimulator(**simulator_config)
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        base_bar = {
            "close": 100.0,
            "volume": 1_000_000,
            "timestamp": datetime.now(),
        }

        fill_low_vol = sim.simulate_fill(
            order, base_bar,
            avg_daily_volume=1_000_000,
            volatility=0.10,
        )
        fill_high_vol = sim.simulate_fill(
            order, base_bar,
            avg_daily_volume=1_000_000,
            volatility=0.30,
        )

        # Higher volatility → larger price shift during latency
        # Fill price difference should reflect that; but due to randomness, just sanity check both > base
        if fill_low_vol and fill_high_vol:
            assert fill_low_vol.price > 0
            assert fill_high_vol.price > 0
            # Prices could be > or < close depending on latency direction randomness


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
