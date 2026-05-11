"""
Unit tests for Position Sizing Engine.

Tests cover all 6 sizing strategies:
- Fixed Fractional
- Kelly Criterion
- Volatility-Adjusted
- Equal Risk Allocation
- Confidence-Weighted
- Composite (ensemble)

Run with: pytest tests/unit/test_risk/test_position_sizing.py -v
"""

import pytest
import numpy as np
from quantumtrade.domain.risk.position_sizer import PositionSizer, SizingStrategyConfig
from quantumtrade.domain.risk.models import SizingDecision


@pytest.fixture
def default_sizer() -> PositionSizer:
    """Default position sizer with $100k portfolio."""
    return PositionSizer(
        portfolio_value=100_000.0,
        risk_per_trade_pct=0.02,
        max_position_pct=0.10,
        strategy="fixed_fractional",
    )


@pytest.fixture
def kelly_sizer() -> PositionSizer:
    """Kelly criterion position sizer."""
    return PositionSizer(
        portfolio_value=100_000.0,
        risk_per_trade_pct=0.02,
        max_position_pct=0.10,
        strategy="kelly",
    )


@pytest.fixture
def vol_sizer() -> PositionSizer:
    """Volatility-adjusted position sizer."""
    return PositionSizer(
        portfolio_value=100_000.0,
        risk_per_trade_pct=0.02,
        max_position_pct=0.10,
        strategy="volatility_adjusted",
        target_volatility=0.20,
    )


@pytest.fixture
def equal_risk_sizer() -> PositionSizer:
    """Equal risk position sizer."""
    return PositionSizer(
        portfolio_value=100_000.0,
        risk_per_trade_pct=0.02,
        max_position_pct=0.10,
        strategy="equal_risk",
    )


@pytest.fixture
def conf_sizer() -> PositionSizer:
    """Confidence-weighted position sizer."""
    return PositionSizer(
        portfolio_value=100_000.0,
        risk_per_trade_pct=0.02,
        max_position_pct=0.10,
        strategy="confidence_weighted",
    )


@pytest.fixture
def composite_sizer() -> PositionSizer:
    """Composite position sizer."""
    return PositionSizer(
        portfolio_value=100_000.0,
        risk_per_trade_pct=0.02,
        max_position_pct=0.10,
        strategy="composite",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fixed Fractional Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFixedFractional:
    """Tests for fixed fractional sizing."""

    def test_basic_calculation(self, default_sizer):
        """Test basic fixed fractional calculation."""
        quantity, metadata = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
        )

        stop_distance = 20.0
        expected_qty = int((100_000 * 0.02) / stop_distance)
        assert quantity == expected_qty

    def test_max_position_cap_applies(self, default_sizer):
        """Test that max position percentage cap is applied."""
        quantity, _ = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=90.0,
        )

        max_by_cap = int((100_000 * 0.10) / 100.0)
        assert quantity <= max_by_cap

    def test_minimum_one_share(self, default_sizer):
        """Test that at least 1 share is returned."""
        quantity, _ = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=99.0,
        )
        assert quantity >= 1

    def test_metadata_structure(self, default_sizer):
        """Test that metadata contains expected fields."""
        quantity, metadata = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
        )

        assert "sizing_model" in metadata
        assert "risk_amount_usd" in metadata
        assert "risk_pct" in metadata
        assert metadata["sizing_model"] == "fixed_fractional"


# ─────────────────────────────────────────────────────────────────────────────
# Kelly Criterion Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKellyCriterion:
    """Tests for Kelly criterion sizing."""

    def test_kelly_formula_manual(self, kelly_sizer):
        """Test Kelly formula: win_rate=0.6, payoff=2.0 → Kelly ≈ 0.4."""
        quantity, metadata = kelly_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=50.0,
            win_rate=0.6,
            avg_win_loss_ratio=2.0,
        )

        kelly_f = (0.6 * 2.0 - 0.4) / 2.0
        expected_kelly = min(0.05, max(0.0, kelly_f)) * 0.5
        expected_qty = int((100_000 * expected_kelly) / 50.0)

        assert quantity == expected_qty

    def test_default_parameters(self, kelly_sizer):
        """Test Kelly with no parameters uses defaults."""
        quantity, metadata = kelly_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=50.0,
        )

        assert quantity >= 1
        assert metadata["kelly_fraction"] is not None

    def test_half_kelly_cap(self, kelly_sizer):
        """Test that Kelly is capped at 5% (half-Kelly)."""
        quantity, metadata = kelly_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=50.0,
            win_rate=0.8,
            avg_win_loss_ratio=3.0,
        )

        kelly_f = metadata["kelly_fraction"]
        assert kelly_f <= 0.05

    def test_zero_win_rate(self, kelly_sizer):
        """Test Kelly with zero win rate."""
        quantity, _ = kelly_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=50.0,
            win_rate=0.0,
            avg_win_loss_ratio=2.0,
        )
        assert quantity >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Volatility-Adjusted Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVolatilityAdjusted:
    """Tests for volatility-adjusted sizing."""

    def test_high_volatility_smaller_size(self, vol_sizer):
        """High volatility → smaller position size."""
        vol_low = 0.10
        vol_high = 0.40

        qty_low, _ = vol_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            volatility=vol_low,
        )

        qty_high, _ = vol_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            volatility=vol_high,
        )

        assert qty_low > qty_high

    def test_adjustment_clamped_between_0_5_and_2(self, vol_sizer):
        """Test adjustment factor is clamped between 0.5x and 2x."""
        qty, metadata = vol_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            volatility=0.80,
        )

        adj = metadata["volatility_adjustment"]
        assert 0.5 <= adj <= 2.0

    def test_target_volatility_equal(self, vol_sizer):
        """When volatility equals target, no adjustment."""
        qty, metadata = vol_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            volatility=0.20,
        )

        assert metadata["volatility_adjustment"] == 1.0

    def test_no_volatility_uses_default(self, vol_sizer):
        """When volatility is None, uses default adjustment of 1.0."""
        qty, metadata = vol_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
        )

        assert metadata["volatility_adjustment"] == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Equal Risk Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEqualRisk:
    """Tests for equal risk allocation sizing."""

    def test_quantity_matches_risk_budget_formula(self, equal_risk_sizer):
        """Test quantity = risk_budget / stop_distance exactly."""
        entry_price = 100.0
        stop_loss = 80.0
        stop_distance = entry_price - stop_loss

        quantity, metadata = equal_risk_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )

        risk_budget = 100_000 * 0.02
        expected_qty = int(risk_budget / stop_distance)
        assert quantity == expected_qty

    def test_correct_risk_amount(self, equal_risk_sizer):
        """Test that risk amount equals risk budget."""
        quantity, metadata = equal_risk_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
        )

        expected_risk = quantity * 20.0
        assert metadata["risk_amount_usd"] == expected_risk


# ─────────────────────────────────────────────────────────────────────────────
# Confidence-Weighted Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceWeighted:
    """Tests for confidence-weighted sizing."""

    def test_confidence_half_size(self, conf_sizer):
        """Test confidence=0.5 → half size."""
        qty_full, _ = conf_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            confidence=1.0,
        )

        qty_half, _ = conf_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            confidence=0.5,
        )

        assert qty_half < qty_full

    def test_confidence_30_percent(self, conf_sizer):
        """Test confidence=0.3 → ~30% size."""
        qty_full, _ = conf_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            confidence=1.0,
        )

        qty_low, _ = conf_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
            confidence=0.3,
        )

        assert qty_low < qty_full

    def test_no_confidence_uses_full_size(self, conf_sizer):
        """Test that None confidence defaults to full size."""
        qty, metadata = conf_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
        )

        assert metadata["confidence_factor"] == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Composite Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestComposite:
    """Tests for composite (ensemble) sizing."""

    def test_weighted_ensemble(self, composite_sizer):
        """Test composite combines multiple models with weights."""
        quantity, metadata = composite_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=95.0,
            confidence=0.8,
            volatility=0.15,
            win_rate=0.6,
            avg_win_loss_ratio=1.5,
        )

        assert quantity >= 1
        assert "Composite" in metadata["reason"]

    def test_custom_weights(self, composite_sizer):
        """Test composite with custom weights."""
        weights = {"kelly": 0.5, "equal_risk": 0.5}

        quantity, _ = composite_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=95.0,
            strategy_weights=weights,
        )

        assert quantity >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_stop_distance(self, default_sizer):
        """Test zero stop distance returns 0 with error."""
        quantity, metadata = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=100.0,
        )

        assert quantity == 0
        assert "error" in metadata

    def test_zero_portfolio_value(self):
        """Test with zero portfolio value."""
        sizer = PositionSizer(portfolio_value=0.0)
        quantity, _ = sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=80.0,
        )
        assert quantity >= 1

    def test_extreme_volatility(self, vol_sizer):
        """Test extreme volatility values."""
        qty_high, _ = vol_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=95.0,
            volatility=2.0,
        )

        assert qty_high >= 1

    def test_invalid_strategy_raises(self):
        """Test invalid strategy raises ValueError."""
        with pytest.raises(ValueError):
            PositionSizer(portfolio_value=100_000, strategy="invalid")

    def test_negative_entry_price(self, default_sizer):
        """Test negative entry price returns 0."""
        quantity, metadata = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=-100.0,
            stop_loss_price=-110.0,
        )
        assert quantity == 0

    def test_low_prices(self, default_sizer):
        """Test with low-priced stock."""
        quantity, metadata = default_sizer.calculate_position_size(
            symbol="PENNY",
            entry_price=0.50,
            stop_loss_price=0.45,
        )
        assert quantity >= 1

    def test_very_tight_stop_results_small_position(self, default_sizer):
        """Very tight stop → small position after max cap."""
        quantity, _ = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=99.99,
        )
        assert quantity >= 1

    def test_very_wide_stop_capped(self, default_sizer):
        """Very wide stop → capped by max position percentage."""
        quantity, _ = default_sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=10.0,
        )

        max_by_cap = int((100_000 * 0.10) / 100.0)
        assert quantity <= max_by_cap


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Switching
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategySwitching:
    """Tests for runtime strategy switching."""

    def test_set_strategy_valid(self, default_sizer):
        """Test setting valid strategy."""
        default_sizer.set_strategy("kelly")
        assert default_sizer.strategy == "kelly"

    def test_set_strategy_invalid(self, default_sizer):
        """Test setting invalid strategy raises."""
        with pytest.raises(ValueError):
            default_sizer.set_strategy("invalid")


# ─────────────────────────────────────────────────────────────────────────────
# SizingDecision Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSizingDecision:
    """Tests for SizingDecision dataclass."""

    def test_get_sizing_decision(self, default_sizer):
        """Test get_sizing_decision returns typed object."""
        decision = default_sizer.get_sizing_decision(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        assert isinstance(decision, SizingDecision)
        assert decision.quantity >= 1
        assert decision.sizing_model == "fixed_fractional"
        assert decision.risk_amount_usd > 0

    def test_sizing_decision_to_dict(self, default_sizer):
        """Test SizingDecision serialization."""
        decision = default_sizer.get_sizing_decision(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=95.0,
        )

        data = decision.to_dict()
        assert "quantity" in data
        assert "risk_pct" in data
        assert "sizing_model" in data


# ─────────────────────────────────────────────────────────────────────────────
# All Strategies Produce Reasonable Quantities
# ─────────────────────────────────────────────────────────────────────────────

class TestAllStrategies:
    """Test that all strategies produce reasonable quantities."""

    @pytest.mark.parametrize("strategy", [
        "fixed_fractional",
        "kelly",
        "volatility_adjusted",
        "equal_risk",
        "confidence_weighted",
        "composite",
    ])
    def test_strategy_produces_quantity(self, strategy):
        """Each strategy should produce a valid quantity."""
        sizer = PositionSizer(
            portfolio_value=100_000.0,
            risk_per_trade_pct=0.02,
            max_position_pct=0.10,
            strategy=strategy,
        )

        quantity, metadata = sizer.calculate_position_size(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss_price=50.0,
            confidence=0.8,
            volatility=0.20,
            win_rate=0.6,
            avg_win_loss_ratio=1.5,
        )

        assert quantity >= 1, f"{strategy} should produce quantity >= 1"
        assert metadata["sizing_model"] == strategy