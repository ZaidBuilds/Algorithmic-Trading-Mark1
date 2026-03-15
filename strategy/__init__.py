"""
Strategy module — 10 trading strategies for all market conditions.

Strategies:
  Trend-Following:    EMA Crossover · SMA · MACD · Momentum
  Mean-Reversion:     RSI · Bollinger Bands · Mean Reversion (Z-Score)
  Price-Action:       Breakout · VWAP
  High-Frequency:     Scalping
"""

from .base import BaseStrategy
from .ema_crossover import EMACrossoverStrategy
from .sma_strategy import SMAStrategy
from .rsi_strategy import RSIStrategy
from .macd_strategy import MACDStrategy
from .bollinger_strategy import BollingerBandsStrategy
from .vwap_strategy import VWAPStrategy
from .breakout_strategy import BreakoutStrategy
from .mean_reversion import MeanReversionStrategy
from .momentum_strategy import MomentumStrategy
from .scalping_strategy import ScalpingStrategy
from .signals import Signal, SignalType


# Registry of all available strategies
STRATEGY_REGISTRY = {
    "EMA Crossover": EMACrossoverStrategy,
    "SMA": SMAStrategy,
    "RSI": RSIStrategy,
    "MACD": MACDStrategy,
    "Bollinger Bands": BollingerBandsStrategy,
    "VWAP": VWAPStrategy,
    "Breakout": BreakoutStrategy,
    "Mean Reversion": MeanReversionStrategy,
    "Momentum": MomentumStrategy,
    "Scalping": ScalpingStrategy,
}


def get_strategy(name: str, **kwargs) -> BaseStrategy:
    """
    Factory function to instantiate a strategy by name.

    Args:
        name: Strategy name (see STRATEGY_REGISTRY)
        **kwargs: Strategy-specific parameters

    Returns:
        Configured BaseStrategy instance

    Raises:
        ValueError: If strategy name is unknown
    """
    if name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown strategy: '{name}'. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}"
        )
    return STRATEGY_REGISTRY[name](**kwargs)


def list_strategies() -> list:
    """Return a list of all available strategy names."""
    return list(STRATEGY_REGISTRY.keys())


__all__ = [
    "BaseStrategy",
    "EMACrossoverStrategy",
    "SMAStrategy",
    "RSIStrategy",
    "MACDStrategy",
    "BollingerBandsStrategy",
    "VWAPStrategy",
    "BreakoutStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "ScalpingStrategy",
    "Signal",
    "SignalType",
    "STRATEGY_REGISTRY",
    "get_strategy",
    "list_strategies",
]
