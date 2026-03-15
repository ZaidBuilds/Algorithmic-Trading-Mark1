"""
Live trading module for running strategies in real-time.

This module provides:
- TradingRunner: Main runner for live trading
- Schedule-based execution
- Real-time market data integration
"""

try:
    from .runner import TradingRunner
    __all__ = ['TradingRunner']
except ImportError:
    __all__ = []
