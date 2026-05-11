"""
Tests for market impact model (Almgren-Chriss).

Covers:
- Permanent and temporary impact calculation
- Impact scaling with participation rate
- Optimal execution trajectory generation
- Horizon estimation
- Parameter stability
"""

import pytest
import numpy as np
from quantumtrade.backtesting.simulation.market_impact import (
    AlmgrenChrissImpact,
    ImpactCalibrator,
)


class TestAlmgrenChrissImpact:
    """Full market impact model tests."""

    def setup_method(self):
        self.impact = AlmgrenChrissImpact(eta=0.01, epsilon=0.05)

    def test_zero_adv_returns_zeros(self):
        result = self.impact.calculate_impact(1000, 0, 50.0, "BUY")
        assert all(v == 0.0 for v in result.values())

    def test_zero_quantity_returns_zeros(self):
        result = self.impact.calculate_impact(0, 10000, 50.0, "BUY")
        assert all(v == 0.0 for v in result.values())

    def test_permanent_linear_scaling(self):
        # Permanent impact ∝ participation rate
        adv = 10000.0
        q1, q2 = 1000, 2000
        r1 = self.impact.calculate_impact_components(q1, adv)
        r2 = self.impact.calculate_impact_components(q2, adv)
        assert r2["permanent_bps"] == pytest.approx(2 * r1["permanent_bps"], rel=1e-3)

    def test_temporary_sqrt_scaling(self):
        # Temporary impact ∝ sqrt(participation)
        adv = 10000.0
        q1, q2 = 1000, 4000
        r1 = self.impact.calculate_impact_components(q1, adv)
        r2 = self.impact.calculate_impact_components(q2, adv)
        # 4x size → 2x sqrt
        assert r2["temporary_bps"] == pytest.approx(2 * r1["temporary_bps"], rel=0.1)

    def test_total_impact_components(self):
        result = self.impact.calculate_impact(5000, 10000, 100.0, "BUY")
        assert result["total_bps"] == pytest.approx(
            result["permanent_bps"] + result["temporary_bps"], rel=1e-6
        )

    def test_dollar_cost_at_10000_notional(self):
        # 10000 notional ≈ 100 shares @ $100
        result = self.impact.calculate_impact(100, 10000, 100.0, "BUY")
        # Total impact in dollars should be positive
        assert result["total_dollars"] > 0
        # For typical parameters: ~0.5–2 bps total → $5–$20 on $10k
        assert 0 < result["total_dollars"] < 100

    def test_buy_sell_symmetry(self):
        # Impact magnitude should be same for BUY and SELL (dollar cost)
        buy = self.impact.calculate_impact(1000, 10000, 100.0, "BUY")
        sell = self.impact.calculate_impact(1000, 10000, 100.0, "SELL")
        assert buy["total_dollars"] == pytest.approx(sell["total_dollars"])


class TestOptimalExecutionTrajectory:
    """Almgren-Chriss optimal liquidation schedule."""

    def setup_method(self):
        self.impact = AlmgrenChrissImpact(
            eta=0.01,
            epsilon=0.05,
            lambda_risk=0.001,
            daily_volatility=0.02,
        )

    def test_trajectory_front_loaded(self):
        """Optimal schedule is front-loaded for risk-averse."""
        times, quantities = self.impact.calculate_optimal_execution_trajectory(
            total_quantity=10000,
            time_horizon_days=10,
            num_periods=100,
        )
        # First few periods should have higher execution rate
        first_qty = np.sum(quantities[:10])
        last_qty = np.sum(quantities[-10:])
        assert first_qty > last_qty  # front-loaded

    def test_total_quantity_conserved(self):
        times, quantities = self.impact.calculate_optimal_execution_trajectory(
            total_quantity=5000,
            time_horizon_days=5,
            num_periods=50,
        )
        assert np.sum(quantities) == pytest.approx(5000, rel=1e-3)

    def test_horizon_zero_when_lambda_zero(self):
        # If no risk aversion, immediate execution is optimal
        impact = AlmgrenChrissImpact(lambda_risk=0.0)
        horizon = impact.calculate_optimal_horizon(1000, 10000)
        # With λ=0, horizon should be 0 (immediate)
        assert horizon == pytest.approx(0.0, abs=1e-6)

    def test_horizon_increases_with_quantity(self):
        # Larger orders need more time
        impact = AlmgrenChrissImpact(lambda_risk=0.001)
        adv = 10000.0
        h1 = impact.calculate_optimal_horizon(1000, adv)
        h2 = impact.calculate_optimal_horizon(4000, adv)
        # 4x size → 2x horizon (since H ∝ sqrt(Q))
        assert h2 / h1 == pytest.approx(2.0, rel=0.5)

    def test_horizon_bounded(self):
        impact = AlmgrenChrissImpact()
        horizon = impact.calculate_optimal_horizon(1e9, 1e6)  # extreme case
        assert 0.1 <= horizon <= 30.0  # bounded between 0.1 and 30 days


class TestParticipationRateToImpact:
    """Quick lookup by participation rate."""

    def test_participation_rate_conversion(self):
        model = AlmgrenChrissImpact(eta=0.01, epsilon=0.05)
        result = model.participation_rate_to_impact(0.10)  # 10% of ADV

        assert result["permanent_bps"] == pytest.approx(0.01 * 0.1 * 10000, rel=1e-5)  # 10 bps
        assert result["temporary_bps"] > 0
        assert result["total_bps"] > result["permanent_bps"]


class TestImpactCalibrator:
    """Calibrate impact parameters from historical data."""

    def test_calibrate_synthetic_data(self):
        # Generate synthetic data with known eta/epsilon
        true_eta = 0.008
        true_epsilon = 0.04
        adv = np.full(100, 10000.0)
        qty = np.linspace(100, 2000, 100)
        part = qty / adv

        # impact = eta * part + epsilon * sqrt(part) + noise
        impacts = true_eta * part * 10000 + true_epsilon * np.sqrt(part) * 10000
        impacts += np.random.normal(0, 0.5, size=len(impacts))  # small noise

        cal = ImpactCalibrator()
        result = cal.calibrate_from_executions(qty, adv, impacts)

        assert result["eta"] == pytest.approx(true_eta, rel=0.2)
        assert result["epsilon"] == pytest.approx(true_epsilon, rel=0.2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
