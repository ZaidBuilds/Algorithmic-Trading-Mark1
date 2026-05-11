"""
Strategy module — 10 trading strategies for all market conditions.

Strategies:
  Trend-Following:    EMA Crossover · SMA · MACD · Momentum
  Mean-Reversion:     RSI · Bollinger Bands · Mean Reversion (Z-Score)
  Price-Action:       Breakout · VWAP
  High-Frequency:     Scalping

Plugin Support:
  - Load custom strategies from strategy/plugins/ directory
  - Cross-exchange symbol mapping for unified portfolio management
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

# Global plugin loader instance for cross-exchange mapping
_plugin_loader_instance = None


def get_plugin_loader():
    """Get or create the global plugin loader instance."""
    global _plugin_loader_instance
    if _plugin_loader_instance is None:
        from quantumtrade.adapters.strategy.plugin_loader import StrategyPluginLoader
        _plugin_loader_instance = StrategyPluginLoader()
    return _plugin_loader_instance


def load_strategy_plugins() -> dict:
    """
    Load all strategy plugins from the plugins directory.
    
    Returns:
        Dictionary of loaded strategy classes
    """
    loader = get_plugin_loader()
    return loader.load_plugins_from_directory()


def register_plugin_strategy(
    name: str,
    strategy_class,
    registry: dict = None,
) -> None:
    """
    Register a custom strategy from a plugin.
    
    Args:
        name: Name for the strategy
        strategy_class: Strategy class to register
        registry: Optional registry dict (defaults to STRATEGY_REGISTRY)
    """
    loader = get_plugin_loader()
    loader.register_strategy(name, strategy_class, registry or STRATEGY_REGISTRY)


def map_symbol_cross_exchange(
    symbol: str,
    from_exchange: str,
    to_exchange: str,
):
    """
    Map a symbol from one exchange format to another.
    
    Args:
        symbol: Symbol in source exchange format
        from_exchange: Source exchange name
        to_exchange: Target exchange name
        
    Returns:
        Mapped symbol in target exchange format, or None
    """
    loader = get_plugin_loader()
    return loader.map_symbol_for_exchange(symbol, from_exchange, to_exchange)


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
    "get_plugin_loader",
    "load_strategy_plugins",
    "register_plugin_strategy",
    "map_symbol_cross_exchange",
]