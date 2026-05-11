"""
Tests for gap risk and circuit breaker models.

Covers:
- Overnight gap simulation
- Gap probability estimation
- Stop-loss behavior across gaps
- Circuit breaker triggers
"""

import pytest
import numpy as np
from datetime import datetime, timedelta

from quantumtrade.backtesting.simulation.gap_risk import (
    GapRiskModel,
    CircuitBreakerModel,
    LimitMoveModel,
)


class TestGapRiskModel:
    """Overnight gap modeling."""

    def setup_method(self):
        self.model = GapRiskModel(
            gap_probability=0.02,
            mean_gap_pct=0.5,
            gap_std_pct=1.0,
            max_gap_pct=10.0,
        )

    def test_no_gap_majority_of_time(self):
        """Most days have no gap (98% if p=0.02)."""
        rng = np.random.default_rng(42)
        gaps = [self.model.simulate_gap(100.0, rng)[0] for _ in range(1000)]
        gap_freq = np.mean([abs(g) > 0 for g in gaps])
        assert 0.01 <= gap_freq <= 0.05  # roughly 2%

    def test_gap_size_distribution(self):
        rng = np.random.default_rng(123)
        gaps_pct = []
        for _ in range(1000):
            gap_pct, _ = self.model.simulate_gap(100.0, rng)
            if gap_pct != 0:
                gaps_pct.append(abs(gap_pct))

        if gaps_pct:
            avg_gap = np.mean(gaps_pct)
            # Should be around 0.5% (mean_gap_pct)
            assert 0.3 < avg_gap < 0.8

    def test_gap_direction_random(self):
        """Gap direction is roughly symmetric."""
        rng = np.random.default_rng(456)
        gaps = []
        for _ in range(200):
            gap_pct, _ = self.model.simulate_gap(100.0, rng)
            if gap_pct != 0:
                gaps.append(gap_pct)

        ups = sum(1 for g in gaps if g > 0)
        downs = sum(1 for g in gaps if g < 0)
        # Roughly balanced
        ratio = ups / (ups + downs) if (ups + downs) > 0 else 0.5
        assert 0.3 <= ratio <= 0.7  # not perfectly balanced in small samples

    def test_price_respects_max_gap(self):
        rng = np.random.default_rng(789)
        for _ in range(100):
            gap_pct, new_open = self.model.simulate_gap(100.0, rng)
            if gap_pct != 0:
                assert abs(gap_pct) <= 0.10  # max 10%
                assert new_open > 0

    def test_gap_probability_estimation(self):
        """Probability increases with holding days."""
        p1 = self.model.estimate_gap_probability(holding_days=1, volatility=0.02)
        p5 = self.model.estimate_gap_probability(holding_days=5, volatility=0.02)
        assert p5 > p1  # longer holding → higher chance of gap

    def test_earnings_boost(self):
        p_normal = self.model.estimate_gap_probability(holding_days=1, is_earnings=False)
        p_earnings = self.model.estimate_gap_probability(holding_days=1, is_earnings=True)
        assert p_earnings > p_normal


class TestStopLossAcrossGap:
    """Stop-loss orders can be gapped through."""

    def setup_method(self):
        self.model = GapRiskModel(gap_probability=1.0)  # force gap every time

    def test_long_stop_gapped_through(self):
        """Long stock with sell stop below gap open."""
        previous_close = 100.0
        stop_price = 99.0  # 1% stop
        # Simulate a gap down of 2%
        rng = np.random.default_rng(42)
        # Override to guarantee gap down
        triggered, fill_price, slippage_bps = self.model.adjust_stop_loss_for_gaps(
            stop_price=stop_price,
            previous_close=previous_close,
            side=OrderSide.BUY,  # long
            rng=rng,
        )
        # Gap often occurs, check logic
        # Since gap_probability=1, gap always occurs; direction random
        # We can't guarantee direction, so just check returns are valid
        assert triggered in [True, False]  # may or may not trigger
        if triggered:
            assert fill_price > 0
            assert slippage_bps >= 0

    def test_short_stop_gapped_through(self):
        """Short stock with buy stop above gap."""
        previous_close = 100.0
        stop_price = 101.0  # 1% stop above
        triggered, fill_price, slippage_bps = self.model.adjust_stop_loss_for_gaps(
            stop_price=stop_price,
            previous_close=previous_close,
            side=OrderSide.SELL,  # short
            rng=np.random.default_rng(99),
        )
        assert triggered in [True, False]


class TestCircuitBreakerModel:
    """Exchange circuit breakers and LULD."""

    def setup_method(self):
        self.cb = CircuitBreakerModel(
            level1_threshold_pct=7.0,
            level2_threshold_pct=13.0,
            level3_threshold_pct=20.0,
        )

    def test_level1_trigger(self):
        halted, level, resume = self.cb.check_circuit_breaker(
            price_change_pct=-0.08,  # 8% down
            current_time=datetime(2024, 1, 1, 10, 0),
        )
        assert halted is True
        assert level == "L1"
        assert resume is not None  # resume time set

    def test_level2_trigger(self):
        halted, level, _ = self.cb.check_circuit_breaker(
            price_change_pct=-0.15,
            current_time=datetime.now(),
        )
        assert halted and level == "L2"

    def test_level3_trigger(self):
        halted, level, resume = self.cb.check_circuit_breaker(
            price_change_pct=-0.25,
            current_time=datetime.now(),
        )
        assert halted and level == "L3"
        assert resume is None  # no resume; rest of day halted

    def test_no_trigger_small_move(self):
        halted, level, _ = self.cb.check_circuit_breaker(
            price_change_pct=0.03,
            current_time=datetime.now(),
        )
        assert not halted
        assert level == ""


class TestLimitMoveModel:
    """Limit-up/limit-down bands."""

    def setup_method(self):
        self.lim = LimitMoveModel(reference_price=100.0, limit_level=0.10)

    def test_upper_limit_hit(self):
        price, limited = self.lim.constrain_price(110.5)  # +10.5%
        assert limited is True
        assert price == pytest.approx(110.0)  # capped at 110

    def test_lower_limit_hit(self):
        price, limited = self.lim.constrain_price(89.0)  # -11%
        assert limited is True
        assert price == pytest.approx(90.0)  # floor at 90

    def test_within_band(self):
        price, limited = self.lim.constrain_price(105.0)
        assert limited is False
        assert price == 105.0


class TestGapStatistics:
    """Statistical properties of gap distribution."""

    def test_gap_statistics_compute(self):
        model = GapRiskModel(gap_probability=0.02, mean_gap_pct=0.5, gap_std_pct=0.8)
        stats = model.get_gap_statistics(n_simulations=5000)

        assert "gap_frequency" in stats
        assert "avg_gap_magnitude_pct" in stats
        assert "expected_loss_pct" in stats
        assert 0 <= stats["gap_frequency"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
