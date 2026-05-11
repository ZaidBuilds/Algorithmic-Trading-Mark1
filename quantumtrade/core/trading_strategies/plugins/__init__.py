"""
Strategy plugins package.

Drop custom strategy implementations in this directory.
They will be discovered and loaded by the StrategyPluginLoader.
"""

from quantumtrade.adapters.strategy.plugin_loader import StrategyPluginLoader

__all__ = ["StrategyPluginLoader"]