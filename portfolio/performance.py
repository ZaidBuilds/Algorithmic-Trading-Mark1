"""
Performance Analyzer — Deep portfolio analytics.

Calculates:
  - Sharpe Ratio
  - Max Drawdown
  - Win Rate & Profit Factor
  - Best/Worst periods
  - Rolling returns
  - Strategy comparison
"""

import logging
import math
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """
    Calculates advanced portfolio performance metrics
    from trade history and snapshots in the database.
    """

    def __init__(self, db=None, initial_capital: float = 100_000.0):
        self.db = db
        self.initial_capital = initial_capital

    # ── Core Metrics ──────────────────────────────────────────────

    def full_report(self) -> dict:
        """Generate a complete performance report."""
        if not self.db:
            return {"error": "No database connected"}

        stats = self.db.get_stats()
        trades = self.db.get_trades(limit=5000)
        snapshots = self.db.get_snapshots(limit=10000)

        # Build returns list from snapshots
        portfolio_values = [s["portfolio_value"] for s in reversed(snapshots)]
        daily_returns = self._calculate_returns(portfolio_values)

        # P&L per trade
        trade_pnls = [t["pnl"] for t in trades if t["pnl"] != 0]
        winning = [p for p in trade_pnls if p > 0]
        losing = [p for p in trade_pnls if p < 0]

        # Current portfolio value
        current_value = portfolio_values[-1] if portfolio_values else self.initial_capital

        return {
            # Overview
            "initial_capital": self.initial_capital,
            "current_value": current_value,
            "total_return": current_value - self.initial_capital,
            "total_return_pct": ((current_value / self.initial_capital) - 1) * 100,

            # Risk metrics
            "sharpe_ratio": self._sharpe_ratio(daily_returns),
            "max_drawdown_pct": self._max_drawdown(portfolio_values),
            "volatility": self._volatility(daily_returns),
            "calmar_ratio": self._calmar_ratio(daily_returns, portfolio_values),

            # Trade metrics
            "total_trades": stats.get("total_trades", 0),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": len(winning) / len(trade_pnls) * 100 if trade_pnls else 0,
            "profit_factor": self._profit_factor(winning, losing),
            "avg_win": sum(winning) / len(winning) if winning else 0,
            "avg_loss": sum(losing) / len(losing) if losing else 0,
            "largest_win": max(winning) if winning else 0,
            "largest_loss": min(losing) if losing else 0,
            "avg_trade_pnl": sum(trade_pnls) / len(trade_pnls) if trade_pnls else 0,

            # Daily
            "daily_pnl": stats.get("daily_pnl", 0),
            "best_day": max(daily_returns) * 100 if daily_returns else 0,
            "worst_day": min(daily_returns) * 100 if daily_returns else 0,

            # Data points
            "snapshots_count": len(snapshots),
            "data_days": len(daily_returns),
        }

    def formatted_report(self) -> str:
        """Generate a human-readable performance report."""
        r = self.full_report()

        if "error" in r:
            return r["error"]

        return_emoji = "📈" if r["total_return"] >= 0 else "📉"

        lines = [
            "═══════════════════════════════════════════",
            "        📊 PERFORMANCE REPORT",
            "═══════════════════════════════════════════",
            "",
            "  ─── Returns ──────────────────────────",
            f"  {return_emoji} Total Return:    ${r['total_return']:>+12,.2f}",
            f"     Return %:       {r['total_return_pct']:>+11.2f}%",
            f"     Start Capital:  ${r['initial_capital']:>12,.2f}",
            f"     Current Value:  ${r['current_value']:>12,.2f}",
            "",
            "  ─── Risk Metrics ─────────────────────",
            f"     Sharpe Ratio:   {r['sharpe_ratio']:>11.2f}",
            f"     Max Drawdown:   {r['max_drawdown_pct']:>10.2f}%",
            f"     Volatility:     {r['volatility']:>10.2f}%",
            f"     Calmar Ratio:   {r['calmar_ratio']:>11.2f}",
            "",
            "  ─── Trade Stats ──────────────────────",
            f"     Total Trades:   {r['total_trades']:>11}",
            f"     Win Rate:       {r['win_rate']:>10.1f}%",
            f"     Profit Factor:  {r['profit_factor']:>11.2f}",
            f"     Avg Win:        ${r['avg_win']:>+11,.2f}",
            f"     Avg Loss:       ${r['avg_loss']:>+11,.2f}",
            f"     Largest Win:    ${r['largest_win']:>+11,.2f}",
            f"     Largest Loss:   ${r['largest_loss']:>+11,.2f}",
            "",
            "═══════════════════════════════════════════",
        ]
        return "\n".join(lines)

    def telegram_report(self) -> str:
        """Telegram-formatted performance report."""
        r = self.full_report()

        if "error" in r:
            return r["error"]

        return_emoji = "📈" if r["total_return"] >= 0 else "📉"

        return (
            "📊 *Performance Report*\n\n"
            f"{return_emoji} Return: ${r['total_return']:+,.2f} ({r['total_return_pct']:+.2f}%)\n"
            f"💰 Portfolio: ${r['current_value']:,.2f}\n\n"
            f"📏 Sharpe: {r['sharpe_ratio']:.2f}\n"
            f"📉 Max DD: {r['max_drawdown_pct']:.2f}%\n"
            f"🎯 Win Rate: {r['win_rate']:.1f}%\n"
            f"⚡ Profit Factor: {r['profit_factor']:.2f}\n\n"
            f"Total Trades: {r['total_trades']}\n"
            f"Wins: {r['winning_trades']} | Losses: {r['losing_trades']}\n"
            f"Avg Win: ${r['avg_win']:+,.2f}\n"
            f"Avg Loss: ${r['avg_loss']:+,.2f}"
        )

    def strategy_comparison(self) -> str:
        """Compare performance across strategies."""
        if not self.db:
            return "No database connected"

        by_strategy = self.db.get_pnl_by_strategy()

        if not by_strategy:
            return "No strategy data available"

        lines = ["🏆 *Strategy Comparison*\n"]

        for i, s in enumerate(by_strategy, 1):
            emoji = "🟢" if s["total_pnl"] >= 0 else "🔴"
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f" {i}."
            lines.append(
                f"{medal} {emoji} *{s['strategy']}*\n"
                f"   P&L: ${s['total_pnl']:+,.2f} | "
                f"Trades: {s['trade_count']} | "
                f"Avg: ${s['avg_pnl']:+,.2f}"
            )

        return "\n".join(lines)

    # ── Calculation Helpers ───────────────────────────────────────

    @staticmethod
    def _calculate_returns(values: List[float]) -> List[float]:
        """Calculate percentage returns from a list of values."""
        if len(values) < 2:
            return []
        return [
            (values[i] / values[i-1]) - 1
            for i in range(1, len(values))
            if values[i-1] != 0
        ]

    @staticmethod
    def _sharpe_ratio(returns: List[float], risk_free_rate: float = 0.04) -> float:
        """
        Annualized Sharpe Ratio.
        risk_free_rate: Annual risk-free rate (default 4%)
        """
        if len(returns) < 2:
            return 0.0

        mean_return = sum(returns) / len(returns)
        std_return = (
            sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        ) ** 0.5

        if std_return == 0:
            return 0.0

        daily_rf = risk_free_rate / 252
        excess = mean_return - daily_rf

        return (excess / std_return) * math.sqrt(252)

    @staticmethod
    def _max_drawdown(values: List[float]) -> float:
        """Calculate maximum drawdown as a percentage."""
        if not values:
            return 0.0

        peak = values[0]
        max_dd = 0.0

        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd

    @staticmethod
    def _volatility(returns: List[float]) -> float:
        """Annualized volatility (standard deviation of returns)."""
        if len(returns) < 2:
            return 0.0

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        daily_vol = variance ** 0.5

        return daily_vol * math.sqrt(252) * 100  # Annualized %

    @staticmethod
    def _profit_factor(wins: List[float], losses: List[float]) -> float:
        """Profit factor = gross profit / gross loss."""
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0

        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def _calmar_ratio(self, returns: List[float], values: List[float]) -> float:
        """Calmar Ratio = annualized return / max drawdown."""
        max_dd = self._max_drawdown(values)
        if max_dd == 0 or len(returns) < 2:
            return 0.0

        total_return = (values[-1] / values[0] - 1) * 100 if values else 0
        # Rough annualization
        days = len(returns)
        annual_return = total_return * (252 / days) if days > 0 else 0

        return annual_return / max_dd
