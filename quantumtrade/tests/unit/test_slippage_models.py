"""
Tests for slippage models.

Covers:
- FixedSlippageModel
- VolumeBasedSlippageModel
- SquareRootSlippageModel
- AlmgrenChrissSlippageModel
- Factory function
"""

import pytest
import numpy as np
from quantumtrade.backtesting.simulation.slippage import (
    FixedSlippageModel,
    VolumeBasedSlippageModel,
    SquareRootSlippageModel,
    AlmgrenChrissSlippageModel,
    create_slippage_model,
)


class TestFixedSlippageModel:
    """Fixed slippage returns constant bps."""

    def test_fixed_slippage(self):
        model = FixedSlippageModel(bps=2.5)
        assert model.calculate_slippage_bps(side="BUY", quantity=100, price=100.0) == 2.5
        assert model.calculate_slippage_bps(side="SELL", quantity=100, price=100.0) == 2.5

    def test_zero_slippage(self):
        model = FixedSlippageModel(bps=0.0)
        assert model.calculate_slippage_bps(side="BUY", quantity=100, price=100.0) == 0.0

    def test_negative_slippage_clamped(self):
        # Negative bps clamped to 0
        model = FixedSlippageModel(bps=-5.0)
        assert model.calculate_slippage_bps(side="BUY", quantity=100, price=100.0) == 0.0


class TestVolumeBasedSlippageModel:
    """Volume-based slippage scales with order size/ADV."""

    def test_zero_when_no_adv(self):
        model = VolumeBasedSlippageModel(k=100.0)
        assert model.calculate_slippage_bps(side="BUY", quantity=100, price=100.0, avg_daily_volume=0) == 0.0
        assert model.calculate_slippage_bps(side="SELL", quantity=100, price=100.0, avg_daily_volume=None) == 0.0

    def test_linear_scaling(self):
        model = VolumeBasedSlippageModel(k=100.0)
        # 1% of ADV → 1 bps
        slippage = model.calculate_slippage_bps(
            side="BUY", quantity=100, price=100.0, avg_daily_volume=10000
        )
        assert slippage == pytest.approx(1.0, rel=1e-3)

        # 10% of ADV → 10 bps
        slippage = model.calculate_slippage_bps(
            side="BUY", quantity=1000, price=100.0, avg_daily_volume=10000
        )
        assert slippage == pytest.approx(10.0, rel=1e-3)

    def test_k_parameter(self):
        # k=200 → double slippage
        model1 = VolumeBasedSlippageModel(k=100.0)
        model2 = VolumeBasedSlippageModel(k=200.0)
        qty = 500
        adv = 10000
        s1 = model1.calculate_slippage_bps(side="BUY", quantity=qty, price=100.0, avg_daily_volume=adv)
        s2 = model2.calculate_slippage_bps(side="BUY", quantity=qty, price=100.0, avg_daily_volume=adv)
        assert s2 == pytest.approx(2 * s1)


class TestSquareRootSlippageModel:
    """Square-root model produces diminishing returns."""

    def test_zero_when_no_adv(self):
        model = SquareRootSlippageModel(sigma=0.01)
        assert model.calculate_slippage_bps(side="BUY", quantity=100, price=100.0, avg_daily_volume=0) == 0.0

    def test_sqrt_scaling(self):
        model = SquareRootSlippageModel(sigma=0.02)
        adv = 10000.0

        # 1% participation
        s1 = model.calculate_slippage_bps(side="BUY", quantity=100, price=100.0, avg_daily_volume=adv)
        # 4% participation (4x larger, sqrt(4)=2, so 2x slippage)
        s2 = model.calculate_slippage_bps(side="BUY", quantity=400, price=100.0, avg_daily_volume=adv)

        assert s2 == pytest.approx(2 * s1, rel=0.1)

    def test_volatility_scaling(self):
        # Higher volatility → higher impact
        model = SquareRootSlippageModel(sigma=0.01)
        adv = 10000.0
        qty = 100

        s_low = model.calculate_slippage_bps(
            side="BUY", quantity=qty, price=100.0, avg_daily_volume=adv, volatility=0.02
        )
        s_high = model.calculate_slippage_bps(
            side="BUY", quantity=qty, price=100.0, avg_daily_volume=adv, volatility=0.04
        )

        assert s_high > s_low


class TestAlmgrenChrissSlippageModel:
    """Full impact model with permanent + temporary components."""

    def test_zero_adv_returns_zero(self):
        model = AlmgrenChrissSlippageModel()
        result = model.calculate_slippage_bps(side="BUY", quantity=1000, price=100.0, avg_daily_volume=0)
        assert result == 0.0

    def test_positive_slippage(self):
        model = AlmgrenChrissSlippageModel(eta=0.01, epsilon=0.05)
        result = model.calculate_slippage_bps(side="BUY", quantity=10000, price=100.0, avg_daily_volume=1_000_000)
        assert result > 0

    def test_slippage_increases_with_quantity(self):
        model = AlmgrenChrissSlippageModel(eta=0.01, epsilon=0.05)
        adv = 1_000_000.0
        q1 = 100_000
        q2 = 400_000
        s1 = model.calculate_slippage_bps(side="BUY", quantity=q1, price=100.0, avg_daily_volume=adv)
        s2 = model.calculate_slippage_bps(side="BUY", quantity=q2, price=100.0, avg_daily_volume=adv)
        assert s2 > s1

    def test_slippage_matches_components(self):
        model = AlmgrenChrissSlippageModel(eta=0.01, epsilon=0.05)
        qty = 10000
        adv = 1_000_000
        participation = qty / adv
        expected_bps = model.eta * participation * 10000 + model.epsilon * np.sqrt(participation) * 10000
        actual = model.calculate_slippage_bps(side="BUY", quantity=qty, price=100.0, avg_daily_volume=adv)
        assert actual == pytest.approx(expected_bps)

    def test_parameters_stored_correctly(self):
        model = AlmgrenChrissSlippageModel(eta=0.02, epsilon=0.1)
        assert model.eta == 0.02
        assert model.epsilon == 0.1


class TestSlippageFactory:
    """Factory creates correct model types."""

    def test_create_fixed(self):
        model = create_slippage_model("fixed", fixed_slippage_bps=5.0)
        assert isinstance(model, FixedSlippageModel)
        assert model.bps == 5.0

    def test_create_volume(self):
        model = create_slippage_model("volume", k=200.0)
        assert isinstance(model, VolumeBasedSlippageModel)
        assert model.k == 200.0

    def test_create_sqrt(self):
        model = create_slippage_model("sqrt", sigma=0.03)
        assert isinstance(model, SquareRootSlippageModel)
        assert model.sigma == 0.03

    def test_create_impact(self):
        model = create_slippage_model("impact", impact_eta=0.02, impact_epsilon=0.1)
        assert isinstance(model, AlmgrenChrissSlippageModel)
        assert model.eta == 0.02
        assert model.epsilon == 0.1

    def test_invalid_model_type(self):
        with pytest.raises(ValueError):
            create_slippage_model("unknown")
