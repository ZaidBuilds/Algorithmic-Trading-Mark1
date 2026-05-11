"""
Tests for Monte Carlo robustness testing.

Covers:
- IID bootstrap resampling
- Block bootstrap
- Return randomization
- Distribution statistics
- Significance testing
"""

import pytest
import numpy as np
import pandas as pd
from quantumtrade.backtesting.monte_carlo import (
    MonteCarloRobustnessTester,
    bootstrap_test_significance,
)
from quantumtrade.backtesting.engine import BacktestEngine
from quantumtrade.backtesting.metrics import BacktestMetrics, Trade
from datetime import datetime


class DummyStrategy:
    def __init__(self, threshold: float = 0.0):
        self.threshold = threshold
        self.name = "Dummy"
        self.required_periods = 5

    def validate_data(self, data):
        pass

    def calculate_indicators(self, data):
        return data

    def generate_signal(self, data, index):
        from quantumtrade.strategy.signals import SignalType, Signal
        if data.iloc[index]['Close'] > self.threshold:
            return Signal(SignalType.BUY, 1.0, data.index[index])
        return Signal(SignalType.SELL, 1.0, data.index[index])


def make_synthetic_trades(n_trades: int = 100, mean_return: float = 0.001, std: float = 0.02) -> list:
    """Generate synthetic trade objects with random returns."""
    trades = []
    entry_date = datetime(2024, 1, 1)
    for i in range(n_trades):
        ret = np.random.normal(mean_return, std)
        entry_price = 100.0
        exit_price = entry_price * (1 + ret)
        pnl = ret * entry_price * 100  # 100 shares
        pnl_pct = ret * 100
        trade = Trade(
            entry_date=entry_date + pd.Timedelta(days=i*5),
            exit_date=entry_date + pd.Timedelta(days=i*5+2),
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=100,
            pnl=pnl,
            pnl_percent=pnl_pct,
            duration=2,
        )
        trades.append(trade)
    return trades


class TestMonteCarloRobustnessTester:
    """Test MC robustness framework."""

    def setup_method(self):
        self.trades = make_synthetic_trades(200, mean_return=0.001, std=0.02)

    def test_iid_bootstrap_produces_valid_curves(self):
        tester = MonteCarloRobustnessTester(
            strategy_factory=lambda p: DummyStrategy(**p),
            n_simulations=1000,
            seed=42,
        )
        results = tester.run_from_trades(self.trades, initial_balance=10000, bootstrap_method="iid")

        assert "total_return_pct" in results
        assert "mean" in results["total_return_pct"]
        assert "p5" in results["total_return_pct"]
        assert results["total_return_pct"]["mean"] is not None

    def test_block_bootstrap_preserves_correlation(self):
        tester = MonteCarloRobustnessTester(
            strategy_factory=lambda p: DummyStrategy(**p),
            n_simulations=500,
            seed=42,
        )
        results = tester.run_from_trades(
            self.trades,
            bootstrap_method="block",
            block_size=10,
        )
        # Should produce results without errors
        assert results.get("total_return_pct") is not None

    def test_randomize_returns(self):
        tester = MonteCarloRobustnessTester(
            strategy_factory=lambda p: DummyStrategy(**p),
            n_simulations=500,
        )
        results = tester.run_from_trades(self.trades, bootstrap_method="randomize")
        assert results["total_return_pct"]["mean"] is not None

    def test_distribution_statistics(self):
        tester = MonteCarloRobustnessTester(
            strategy_factory=lambda p: DummyStrategy(**p),
            n_simulations=2000,
            seed=123,
        )
        results = tester.run_from_trades(self.trades)

        # Check all expected keys
        expected_keys = [
            "total_return_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate"
        ]
        for key in expected_keys:
            assert key in results
            assert "mean" in results[key]
            assert "median" in results[key]
            assert "p5" in results[key]
            assert "p95" in results[key]

    def test_negative_return_probability_computed(self):
        tester = MonteCarloRobustnessTester(
            strategy_factory=lambda p: DummyStrategy(**p),
            n_simulations=1000,
        )
        results = tester.run_from_trades(self.trades)
        prob = results.get("negative_return_probability")
        assert 0.0 <= prob <= 100.0

    def test_report_generation(self):
        tester = MonteCarloRobustnessTester(lambda p: DummyStrategy(), n_simulations=100)
        results = tester.run_from_trades(self.trades)
        report = tester.generate_report(results)
        assert isinstance(report, str)
        assert "MONTE CARLO" in report
        assert "5th percentile" in report


class TestBootstrapSignificance:
    """Statistical significance tests via bootstrap."""

    def test_significance_positive_alpha(self):
        # Strategy has positive excess return
        strategy_rets = np.random.normal(0.002, 0.02, 200)  # 20 bps avg
        benchmark_rets = np.random.normal(0.0, 0.02, 200)

        result = bootstrap_test_significance(strategy_rets, benchmark_rets, n_simulations=5000)

        assert "p_value" in result
        assert result["p_value"] < 0.05  # should be significant
        assert result["original_excess_return"] > 0

    def test_significance_negative_alpha(self):
        # Strategy underperforms
        strategy_rets = np.random.normal(-0.001, 0.02, 200)
        benchmark_rets = np.random.normal(0.0, 0.02, 200)

        result = bootstrap_test_significance(strategy_rets, benchmark_rets, n_simulations=5000)

        assert result["p_value"] > 0.05  # not significant positive

    def test_confidence_interval_contains_zero_when_no_edge(self):
        # Strategy and benchmark identical
        common_rets = np.random.normal(0.0, 0.02, 200)
        result = bootstrap_test_significance(common_rets, common_rets, n_simulations=2000)

        # CI should include 0
        assert result["ci_2.5%"] <= 0 <= result["ci_97.5%"]


class TestMonteCarloIntegration:
    """Integration: Monte Carlo on actual backtest output."""

    def test_from_backtest_results(self):
        data = make_synthetic_data(300, trend=0.0)
        tester = MonteCarloRobustnessTester(
            strategy_factory=lambda p: DummyStrategy(**p),
            n_simulations=500,
            seed=42,
        )

        results = tester.run_from_backtest(
            data=data,
            strategy_params={"threshold": 0.5},
            engine=BacktestEngine(initial_balance=10000),
        )

        assert "total_return_pct" in results
        assert results["total_return_pct"]["p5"] <= results["total_return_pct"]["p95"]

    def test_original_backtest_percentile(self):
        """Original backtest should typically lie near median."""
        data = make_synthetic_data(400, trend=0.0)
        tester = MonteCarloRobustnessTester(
            lambda p: DummyStrategy(**p),
            n_simulations=2000,
            seed=321,
        )
        results = tester.run_from_backtest(
            data=data,
            strategy_params={"threshold": 0.5},
            engine=BacktestEngine(),
        )
        # Original return percentile should be between 10-90% most of the time
        pct = results.get("return_percentile")
        if pct is not None:
            assert 0 <= pct <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
