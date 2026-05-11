"""
Slippage models for realistic order execution simulation.

Multiple slippage models:
- Fixed: constant bps
- Volume-based: linear with order size / ADV
- Square-root: sqrt(quantity / ADV) — Almgren-Chriss temporary impact
- Impact-based: full Almgren-Chriss permanent + temporary
"""

from typing import Optional
import numpy as np
from enum import Enum

from quantumtrade.adapters.execution.models import OrderSide


class SlippageModelType(str, Enum):
    """Supported slippage model types."""
    FIXED = "fixed"
    VOLUME = "volume"
    SQUARE_ROOT = "sqrt"
    IMPACT = "impact"


class BaseSlippageModel:
    """Base class for slippage models."""

    def calculate_slippage_bps(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        avg_daily_volume: Optional[float] = None,
        volatility: Optional[float] = None,
        **kwargs
    ) -> float:
        """
        Calculate slippage in basis points.

        Args:
            side: Order side (BUY/SELL)
            quantity: Order size in shares/units
            price: Current price (mid or best)
            avg_daily_volume: ADV for volume-based models
            volatility: Annualized volatility (optional)

        Returns:
            Slippage in basis points (positive = adverse movement)
        """
        raise NotImplementedError


class FixedSlippageModel(BaseSlippageModel):
    """Fixed slippage — constant bps regardless of order size."""

    def __init__(self, bps: float = 1.0):
        """
        Args:
            bps: Fixed slippage in basis points
        """
        self.bps = max(0.0, bps)

    def calculate_slippage_bps(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        **kwargs
    ) -> float:
        return self.bps


class VolumeBasedSlippageModel(BaseSlippageModel):
    """
    Linear volume-based slippage.

    Formula: slippage_bps = k * (quantity / ADV)
    Typical: k = 100-500 bps per unit participation
    """

    def __init__(self, k: float = 100.0):
        """
        Args:
            k: Slippage coefficient (bps per unit participation rate)
                100 bps means 1% of ADV → 1 bps slippage
        """
        self.k = k

    def calculate_slippage_bps(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        avg_daily_volume: Optional[float] = None,
        **kwargs
    ) -> float:
        if avg_daily_volume is None or avg_daily_volume <= 0 or quantity <= 0:
            return 0.0

        participation = quantity / avg_daily_volume
        slippage_bps = self.k * participation

        return max(0.0, slippage_bps)


class SquareRootSlippageModel(BaseSlippageModel):
    """
    Square-root slippage model — widely used in algo trading.

    Slippage ~ sqrt(participation_rate)
    Captures diminishing returns: doubling order size gives <2x slippage

    Formula: slippage_bps = sigma * sqrt(quantity / ADV)
    where sigma is a volatility-adjusted coefficient.
    """

    def __init__(self, sigma: float = 0.01):
        """
        Args:
            sigma: Volatility coefficient (typical: 0.01–0.05)
                   Higher for less liquid instruments
        """
        self.sigma = sigma

    def calculate_slippage_bps(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        avg_daily_volume: Optional[float] = None,
        volatility: Optional[float] = None,
        **kwargs
    ) -> float:
        if avg_daily_volume is None or avg_daily_volume <= 0 or quantity <= 0:
            return 0.0

        participation = quantity / avg_daily_volume

        # Adjust sigma by volatility if provided (volatility ~ 0.01–0.05 daily)
        effective_sigma = self.sigma
        if volatility is not None:
            effective_sigma = self.sigma * (volatility / 0.02)  # normalized to 2% daily

        slippage_bps = effective_sigma * np.sqrt(participation) * 10000

        return max(0.0, slippage_bps)


class AlmgrenChrissSlippageModel(BaseSlippageModel):
    """
    Full Almgren-Chriss market impact model.

    Separates permanent and temporary impact:
    - Permanent impact: eta * (Q / ADV)  [linear]
    - Temporary impact: epsilon * sqrt(Q / ADV)  [square-root]

    Parameters:
      eta (η): permanent impact coefficient
      epsilon (ε): temporary impact coefficient

    Total slippage = permanent + temporary (expressed in bps)

    Reference: Almgren & Chriss (2000), "Optimal Execution of Portfolio Transactions"
    """

    def __init__(
        self,
        eta: float = 0.01,
        epsilon: float = 0.05,
    ):
        """
        Args:
            eta: Permanent impact coefficient (linear)
            epsilon: Temporary impact coefficient (square-root)
        """
        self.eta = eta
        self.epsilon = epsilon

    def calculate_slippage_bps(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        avg_daily_volume: Optional[float] = None,
        **kwargs
    ) -> float:
        if avg_daily_volume is None or avg_daily_volume <= 0 or quantity <= 0:
            return 0.0

        participation = quantity / avg_daily_volume

        # Permanent impact (linear in participation)
        permanent_bps = self.eta * participation * 10000

        # Temporary impact (sqrt of participation)
        temporary_bps = self.epsilon * np.sqrt(participation) * 10000

        total_bps = permanent_bps + temporary_bps

        return max(0.0, total_bps)

    def calculate_impact_components(
        self,
        quantity: float,
        avg_daily_volume: float,
    ) -> dict:
        """
        Return breakdown of permanent and temporary impact.

        Returns:
            dict with 'permanent_bps', 'temporary_bps', 'total_bps'
        """
        participation = quantity / avg_daily_volume

        permanent_bps = self.eta * participation * 10000
        temporary_bps = self.epsilon * np.sqrt(participation) * 10000

        return {
            "permanent_bps": permanent_bps,
            "temporary_bps": temporary_bps,
            "total_bps": permanent_bps + temporary_bps,
        }


def create_slippage_model(
    model_type: str,
    **params
) -> BaseSlippageModel:
    """
    Factory function to create slippage model from config.

    Args:
        model_type: "fixed", "volume", "sqrt", or "impact"
        **params: Model-specific parameters (bps, k, sigma, eta, epsilon)

    Example:
        model = create_slippage_model("impact", eta=0.01, epsilon=0.05)
    """
    model_type = model_type.lower()

    if model_type == SlippageModelType.FIXED:
        return FixedSlippageModel(bps=params.get("fixed_slippage_bps", 1.0))
    elif model_type == SlippageModelType.VOLUME:
        return VolumeBasedSlippageModel(k=params.get("k", 100.0))
    elif model_type == SlippageModelType.SQUARE_ROOT:
        return SquareRootSlippageModel(sigma=params.get("sigma", 0.01))
    elif model_type == SlippageModelType.IMPACT:
        return AlmgrenChrissSlippageModel(
            eta=params.get("impact_eta", 0.01),
            epsilon=params.get("impact_epsilon", 0.05),
        )
    else:
        raise ValueError(f"Unknown slippage model: {model_type}")
