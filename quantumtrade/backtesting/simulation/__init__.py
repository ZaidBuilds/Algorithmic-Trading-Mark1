"""
Backtesting simulation package — realistic market microstructure modeling.

Provides:
- Slippage models (fixed, volume-based, square-root, Almgren-Chriss)
- Latency simulation (network, broker, exchange delays)
- Spread cost modeling (bid-ask)
- Market impact (permanent + temporary)
- Liquidity constraints (partial fills, order book depth)
- Gap risk (overnight moves, limit moves)
- Circuit breakers (trading halts)

Main entry point: MarketSimulator
"""

from .slippage import (
    SlippageModelType,
    BaseSlippageModel,
    FixedSlippageModel,
    VolumeBasedSlippageModel,
    SquareRootSlippageModel,
    AlmgrenChrissSlippageModel,
    create_slippage_model,
)
from .latency import LatencyModel, FixedLatencyModel, LatencyDistribution
from .spread import SpreadCostModel, OrderBookSpreadModel
from .market_impact import AlmgrenChrissImpact, ImpactCalibrator
from .liquidity import (
    LiquidityModel,
    LimitOrderFillModel,
    GapRiskModel,
    CircuitBreakerModel,
)
from .simulator import MarketSimulator, MarketFill

__all__ = [
    # Slippage models
    "SlippageModelType",
    "BaseSlippageModel",
    "FixedSlippageModel",
    "VolumeBasedSlippageModel",
    "SquareRootSlippageModel",
    "AlmgrenChrissSlippageModel",
    "create_slippage_model",
    # Latency
    "LatencyModel",
    "FixedLatencyModel",
    "LatencyDistribution",
    # Spread
    "SpreadCostModel",
    "OrderBookSpreadModel",
    # Impact
    "AlmgrenChrissImpact",
    "ImpactCalibrator",
    # Liquidity
    "LiquidityModel",
    "LimitOrderFillModel",
    "GapRiskModel",
    "CircuitBreakerModel",
    # Main simulator
    "MarketSimulator",
    "MarketFill",
]
