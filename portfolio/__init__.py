"""
Portfolio Tracker — Track positions, P&L, equity curve, and performance.

Features:
  - Real-time position tracking with unrealized P&L
  - Equity curve generation for charts
  - Portfolio-level metrics (total return, drawdown, Sharpe)
  - Auto-snapshots for historical tracking
  - Telegram integration via /portfolio command

Usage:
    from portfolio import PortfolioTracker
    tracker = PortfolioTracker(broker, db)
    tracker.update()
    print(tracker.report())
"""

from .tracker import PortfolioTracker
from .performance import PerformanceAnalyzer

__all__ = ["PortfolioTracker", "PerformanceAnalyzer"]
