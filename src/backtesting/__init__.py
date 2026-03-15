"""
Backtesting module for testing trading strategies on historical data.

This module provides:
- BacktestEngine: Main backtesting engine that simulates trades
- BacktestMetrics: Performance metrics calculation  
- Trade: Trade record data structure
- BacktestReporter: Results reporting and CSV export
"""

from .engine import BacktestEngine
from .metrics import BacktestMetrics, Trade
from .reporter import BacktestReporter

__all__ = ['BacktestEngine', 'BacktestMetrics', 'Trade', 'BacktestReporter']
