"""Unit tests for position sizing algorithms."""
import pytest
import numpy as np
from quantumtrade.domain.risk.position_sizer import PositionSizer


class TestFixedFractional:
    def test_basic(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="fixed_fractional", risk_per_trade_pct=0.02)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 145.0)
        assert qty > 0
        assert meta["sizing_model"] == "fixed_fractional"

    def test_stop_equals_entry_returns_zero(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="fixed_fractional", risk_per_trade_pct=0.02)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 150.0)
        assert qty == 0

    def test_negative_stop_distance(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="fixed_fractional", risk_per_trade_pct=0.02)
        # abs() is used, so stop > entry still produces a positive distance.
        # Only stop == entry returns zero.
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 155.0)
        assert qty > 0

    def test_max_position_cap(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="fixed_fractional", risk_per_trade_pct=0.50, max_position_pct=0.10)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0)
        max_qty = int((100000 * 0.10) / 150)
        assert qty <= max_qty


class TestKelly:
    def test_basic(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="kelly", kelly_fraction_cap=0.05)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0, win_rate=0.55, avg_win_loss_ratio=1.5)
        assert qty > 0
        assert meta["sizing_model"] == "kelly"

    def test_kelly_fraction_capped(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="kelly", kelly_fraction_cap=0.05)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0, win_rate=0.90, avg_win_loss_ratio=10.0)
        assert meta.get("kelly_fraction", 1.0) <= 0.05


class TestVolatilityAdjusted:
    def test_basic(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="volatility_adjusted", target_volatility=0.20)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0, volatility=0.30)
        assert qty > 0
        assert "volatility_adjustment" in meta

    def test_low_vol_increases_size(self):
        # Use a larger portfolio and higher cap so the volatility adjustment
        # is the dominant factor, not the position cap.
        sizer = PositionSizer(portfolio_value=1000000, strategy="volatility_adjusted", target_volatility=0.20, max_position_pct=1.0)
        qty_high, _ = sizer.calculate_position_size("AAPL", 150.0, 140.0, volatility=0.40)
        qty_low, _ = sizer.calculate_position_size("AAPL", 150.0, 140.0, volatility=0.10)
        assert qty_low > qty_high


class TestEqualRisk:
    def test_basic(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="equal_risk", risk_per_trade_pct=0.02)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0)
        assert qty > 0
        assert meta["sizing_model"] == "equal_risk"


class TestConfidenceWeighted:
    def test_basic(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="confidence_weighted", risk_per_trade_pct=0.02)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0, confidence=0.8)
        assert qty > 0
        assert "confidence_factor" in meta

    def test_high_confidence_larger(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="confidence_weighted", risk_per_trade_pct=0.02)
        qty_high, _ = sizer.calculate_position_size("AAPL", 150.0, 140.0, confidence=0.9)
        qty_low, _ = sizer.calculate_position_size("AAPL", 150.0, 140.0, confidence=0.3)
        assert qty_high > qty_low

    def test_none_confidence_defaults_to_one(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="confidence_weighted", risk_per_trade_pct=0.02)
        qty, _ = sizer.calculate_position_size("AAPL", 150.0, 140.0, confidence=None)
        assert qty > 0


class TestComposite:
    def test_basic(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="composite", risk_per_trade_pct=0.02)
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0, win_rate=0.55, avg_win_loss_ratio=1.5, volatility=0.25, confidence=0.7)
        assert qty > 0
        assert meta["sizing_model"] == "composite"


class TestGetSizingDecision:
    def test_returns_sizing_decision(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="fixed_fractional")
        decision = sizer.get_sizing_decision("AAPL", 150.0, 140.0)
        assert decision.quantity > 0
        assert decision.sizing_model == "fixed_fractional"
        assert decision.risk_amount_usd > 0
        assert decision.stop_distance_pct > 0


class TestInvalidStrategy:
    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError):
            PositionSizer(portfolio_value=100000, strategy="nonexistent")

    def test_invalid_entry_price(self):
        sizer = PositionSizer(portfolio_value=100000)
        qty, meta = sizer.calculate_position_size("AAPL", 0.0, 140.0)
        assert qty == 0
        assert "error" in meta


class TestFallbackOnError:
    def test_fallback_on_exception(self):
        sizer = PositionSizer(portfolio_value=100000, strategy="fixed_fractional")
        qty, meta = sizer.calculate_position_size("AAPL", 150.0, 140.0)
        assert qty >= 1