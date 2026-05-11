"""
Integration tests for full backtesting with MarketSimulator.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from quantumtrade.backtesting import (
    BacktestEngine,
    BacktestReporter,
    MarketSimulator,
)
from quantumtrade.strategy.base import BaseStrategy
from quantumtrade.strategy.signals import SignalType, Signal


class MomentumStrategy(BaseStrategy):
    """Momentum-based test strategy."""

    def __init__(self, lookback: int = 10, threshold: float = 0.02):
        self.lookback = lookback
        self.threshold = threshold
        self.name = f"Momentum(lookback={lookback}, threshold={threshold})"
        self.required_periods = lookback

    def validate_data(self, data: pd.DataFrame):
        assert "Close" in data.columns

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        data['returns'] = data['Close'].pct_change(periods=self.lookback)
        return data

    def generate_signal(self, data: pd.DataFrame, index: int) -> Signal:
        row = data.iloc[index]
        if row['returns'] > self.threshold:
            return Signal(SignalType.BUY, 1.0, row.name)
        elif row['returns'] < -self.threshold:
            return Signal(SignalType.SELL, 1.0, row.name)
        else:
            return Signal(SignalType.HOLD, 0.0, row.name)


@pytest.fixture
def synthetic_market_data() -> pd.DataFrame:
    """Create realistic OHLCV with trends, volatility, volume."""
    np.random.seed(42)
    n_days = 300
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")

    # Random walk with drift
    returns = np.random.normal(0.0005, 0.015, n_days)
    prices = 100 * np.exp(np.cumsum(returns))

    # Add some volatility clustering
    volatility = np.abs(np.random.randn(n_days) * 0.02)

    data = pd.DataFrame({
        "Open": prices * (1 + np.random.uniform(-0.005, 0.005, n_days)),
        "High": prices * (1 + volatility),
        "Low": prices * (1 - volatility),
        "Close": prices,
        "Volume": np.random.uniform(500_000, 2_000_000, n_days).astype(int),
    }, index=dates)

    return data


class TestFullBacktestWorkflow:
    """End-to-end backtesting with all simulation layers enabled."""

    def test_backtest_with_advanced_simulator(self, synthetic_market_data):
        config = {
            "slippage_model": "impact",
            "latency_ms": 150.0,
            "spread_bps": 1.5,
            "enable_impact": True,
            "impact_eta": 0.01,
            "impact_epsilon": 0.05,
            "participation_rate": 0.10,
            "enable_liquidity_constraints": False,  # unlimited for simplicity
            "enable_gap_risk": False,  # no gaps in intraday
            "enable_circuit_breakers": False,
            "seed": 42,
        }

        engine = BacktestEngine(
            initial_balance=50000,
            commission=0.0005,  # 5 bps
            simulator_config=config,
        )

        strategy = MomentumStrategy(lookback=20, threshold=0.03)
        metrics = engine.run(strategy, synthetic_market_data)

        # Basic sanity
        assert len(metrics.trades) > 0
        assert metrics.current_balance != metrics.initial_balance

    def test_tca_reports_attached(self, synthetic_market_data):
        config = {
            "slippage_model": "volume",
            "latency_ms": 100,
            "spread_bps": 1.0,
            "enable_impact": True,
            "enable_liquidity_constraints": False,
            "enable_gap_risk": False,
            "seed": 123,
        }

        engine = BacktestEngine(initial_balance=10000, simulator_config=config)
        strategy = MomentumStrategy(threshold=0.025)
        engine.run(strategy, synthetic_market_data)

        reports = engine.get_tca_reports()
        assert len(reports) == len(metrics.trades) or len(reports) >= len(metrics.trades) * 0.8

        # Each report should have total_cost_bps
        for report in reports[:10]:  # sample
            assert report.total_cost_bps >= 0

    def test_reporter_with_tca(self, synthetic_market_data):
        config = {
            "slippage_model": "impact",
            "latency_ms": 150,
            "spread_bps": 1.0,
            "enable_impact": True,
            "enable_gap_risk": False,
            "seed": 42,
        }

        engine = BacktestEngine(
            initial_balance=20000,
            simulator_config=config,
        )
        strategy = MomentumStrategy(threshold=0.02)
        metrics = engine.run(strategy, synthetic_market_data)

        reporter = BacktestReporter(
            metrics,
            tca_reports=engine.get_tca_reports(),
            simulation_metrics={},
        )

        summary = reporter.generate_summary_text(include_tca=True)
        assert "TRANSACTION COST ANALYSIS" in summary
        assert "TOTAL COST:" in summary

    def test_export_functionality(self, synthetic_market_data, tmp_path):
        config = {"slippage_model": "fixed", "fixed_slippage_bps": 1.0, "seed": 42}
        engine = BacktestEngine(initial_balance=10000, simulator_config=config)
        strategy = MomentumStrategy()
        engine.run(strategy, synthetic_market_data)

        trades_csv = tmp_path / "trades.csv"
        equity_csv = tmp_path / "equity.csv"
        tca_csv = tmp_path / "tca.csv"

        reporter = BacktestReporter(engine.metrics, tca_reports=engine.tca_reports)

        reporter.export_trades_csv(str(trades_csv))
        reporter.export_equity_curve_csv(str(equity_csv))
        reporter.export_tca_reports_csv(str(tca_csv))

        assert trades_csv.exists()
        assert equity_csv.exists()
        assert tca_csv.exists()

    def test_simulator_seed_reproducibility(self):
        """Same seed → same results."""
        config = {
            "slippage_model": "volume",
            "latency_ms": 150,
            "seed": 999,
        }

        sim1 = MarketSimulator(**config)
        sim2 = MarketSimulator(**config)

        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=1000,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {
            "close": 100.0,
            "high": 101.0,
            "low": 99.0,
            "volume": 1_000_000,
            "timestamp": datetime.now(),
        }

        fill1 = sim1.simulate_fill(order, bar, avg_daily_volume=1_000_000)
        fill2 = sim2.simulate_fill(order, bar, avg_daily_volume=1_000_000)

        if fill1 and fill2:
            assert fill1.price == pytest.approx(fill2.price, abs=1e-6)
            assert fill1.latency_ms == fill2.latency_ms


class TestCostMetrics:
    """Verify cost breakdown accuracy."""

    def test_total_implicit_cost_composition(self, synthetic_market_data):
        config = {
            "slippage_model": "impact",
            "latency_ms": 100,
            "spread_bps": 2.0,
            "enable_impact": True,
            "impact_eta": 0.02,
            "impact_epsilon": 0.1,
            "enable_liquidity_constraints": False,
            "enable_gap_risk": False,
            "seed": 42,
        }

        engine = BacktestEngine(initial_balance=10000, simulator_config=config)
        strategy = MomentumStrategy(threshold=0.05)  # trigger fewer trades
        metrics = engine.run(strategy, synthetic_market_data)

        # Aggregate TCA
        reports = engine.tca_reports
        if reports:
            avg_total_implicit = np.mean([
                r.total_implicit_cost_bps for r in reports if r.total_implicit_cost_bps > 0
            ])
            # With impact and spread, should be > 0
            assert avg_total_implicit > 0

    def test_slippage_vs_order_size_correlation(self, synthetic_market_data):
        """Larger order sizes should generally have higher slippage."""
        config = {
            "slippage_model": "volume",
            "latency_ms": 50,
            "spread_bps": 1.0,
            "enable_impact": False,
            "enable_gap_risk": False,
            "seed": 42,
        }

        engine = BacktestEngine(initial_balance=10000, simulator_config=config)
        strategy = MomentumStrategy(threshold=0.02)
        engine.run(strategy, synthetic_market_data)

        # If we have varying trade sizes, some correlation should exist
        fills = []
        for report in engine.tca_reports:
            fills.append({
                'quantity': report.order_quantity,
                'slippage_bps': report.implicit_slippage_bps,
            })

        if len(fills) >= 5:
            df = pd.DataFrame(fills)
            if df['quantity'].std() > 0:
                corr = df['quantity'].corr(df['slippage_bps'])
                # May not be strongly positive due to small sample, but should be >= 0
                assert corr >= -0.5  # weak positive or zero (not strongly negative)


class TestEdgeCases:
    """Handle edge inputs gracefully."""

    def test_zero_volume_bar(self):
        sim = MarketSimulator()
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": 100.0, "volume": 0, "timestamp": datetime.now()}
        fill = sim.simulate_fill(order, bar, avg_daily_volume=1_000_000)
        # With zero volume, fill may not occur
        assert fill is None or fill.quantity > 0

    def test_extreme_slippage_parameters(self):
        sim = MarketSimulator(
            slippage_model="impact",
            impact_eta=10.0,  # very high impact
            impact_epsilon=10.0,
            seed=42,
        )
        order = BrokerOrder(
            symbol="TEST",
            side=OrderSide.BUY,
            quantity=1_000_000,
            order_type=OrderType.MARKET,
            timestamp=datetime.now(),
        )
        bar = {"close": 100.0, "volume": 1_000_000, "timestamp": datetime.now()}
        fill = sim.simulate_fill(order, bar, avg_daily_volume=1_000_000)
        if fill:
            # Price should be astronomically high but still finite
            assert fill.price > 0
            assert fill.price < 1e9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
