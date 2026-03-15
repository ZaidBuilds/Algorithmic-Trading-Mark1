"""
Portfolio Tracker — Real-time position and P&L tracking.

Tracks:
  - Every open position with live P&L
  - Portfolio value over time (equity curve)
  - Allocation percentages
  - Best/worst performers
  - Auto-snapshots to database
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TrackedPosition:
    """A tracked position with full P&L details."""
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    cost_basis: float = 0.0
    unrealised_pnl: float = 0.0
    unrealised_pnl_pct: float = 0.0
    weight_pct: float = 0.0  # Portfolio allocation %
    strategy: str = ""
    opened_at: str = ""


@dataclass
class PortfolioSnapshot:
    """Point-in-time snapshot of the portfolio."""
    timestamp: str
    cash: float
    equity: float
    portfolio_value: float
    positions_count: int
    unrealised_pnl: float
    realised_pnl: float
    total_return_pct: float
    positions: List[TrackedPosition] = field(default_factory=list)


class PortfolioTracker:
    """
    Tracks portfolio positions and performance in real-time.

    Pulls data from broker + database to give a complete picture.
    """

    def __init__(self, broker=None, db=None, initial_capital: float = 100_000.0):
        """
        Args:
            broker: BaseBroker instance for live position data
            db: Database instance for historical data
            initial_capital: Starting capital for return calculations
        """
        self.broker = broker
        self.db = db
        self.initial_capital = initial_capital
        self._last_snapshot: Optional[PortfolioSnapshot] = None
        self._snapshots: List[PortfolioSnapshot] = []

    # ── Core Tracking ─────────────────────────────────────────────

    def update(self) -> PortfolioSnapshot:
        """
        Refresh portfolio data and create a new snapshot.

        Returns:
            Current PortfolioSnapshot
        """
        if not self.broker or not self.broker.is_connected:
            logger.warning("Broker not connected, using last known state")
            return self._last_snapshot or PortfolioSnapshot(
                timestamp=datetime.now().isoformat(),
                cash=self.initial_capital,
                equity=self.initial_capital,
                portfolio_value=self.initial_capital,
                positions_count=0,
                unrealised_pnl=0,
                realised_pnl=0,
                total_return_pct=0,
            )

        # Get account & positions from broker
        account = self.broker.get_account()
        broker_positions = self.broker.get_positions()
        realised_pnl = self.db.get_total_pnl() if self.db else 0.0

        # Build tracked positions
        tracked = []
        total_market_value = sum(
            p.quantity * p.current_price for p in broker_positions
        )
        total_unrealised = 0.0

        for p in broker_positions:
            market_val = p.quantity * p.current_price
            cost = p.quantity * p.avg_entry_price
            u_pnl = market_val - cost
            u_pnl_pct = ((p.current_price / p.avg_entry_price) - 1) * 100 if p.avg_entry_price else 0
            weight = (market_val / account.portfolio_value * 100) if account.portfolio_value else 0

            total_unrealised += u_pnl

            tracked.append(TrackedPosition(
                symbol=p.symbol,
                quantity=p.quantity,
                avg_entry_price=p.avg_entry_price,
                current_price=p.current_price,
                market_value=market_val,
                cost_basis=cost,
                unrealised_pnl=u_pnl,
                unrealised_pnl_pct=u_pnl_pct,
                weight_pct=weight,
            ))

        # Sort by market value (biggest positions first)
        tracked.sort(key=lambda x: x.market_value, reverse=True)

        total_return_pct = (
            (account.portfolio_value / self.initial_capital - 1) * 100
            if self.initial_capital else 0
        )

        snapshot = PortfolioSnapshot(
            timestamp=datetime.now().isoformat(),
            cash=account.cash,
            equity=account.equity,
            portfolio_value=account.portfolio_value,
            positions_count=len(tracked),
            unrealised_pnl=total_unrealised,
            realised_pnl=realised_pnl,
            total_return_pct=total_return_pct,
            positions=tracked,
        )

        self._last_snapshot = snapshot
        self._snapshots.append(snapshot)

        # Auto-save to DB
        if self.db:
            self.db.save_snapshot(
                cash=account.cash,
                equity=account.equity,
                portfolio_value=account.portfolio_value,
                positions_count=len(tracked),
                daily_pnl=self.db.get_daily_pnl(),
                total_pnl=realised_pnl + total_unrealised,
            )

        return snapshot

    # ── Reports ───────────────────────────────────────────────────

    def report(self) -> str:
        """Generate a formatted portfolio report."""
        snap = self._last_snapshot or self.update()

        lines = [
            "═══════════════════════════════════════",
            "       📊 PORTFOLIO REPORT",
            "═══════════════════════════════════════",
            "",
            f"  💰 Cash:           ${snap.cash:>12,.2f}",
            f"  📊 Equity:         ${snap.equity:>12,.2f}",
            f"  🏦 Portfolio:      ${snap.portfolio_value:>12,.2f}",
            f"  📈 Total Return:   {snap.total_return_pct:>+11.2f}%",
            "",
            f"  📗 Unrealised P&L: ${snap.unrealised_pnl:>+12,.2f}",
            f"  📕 Realised P&L:   ${snap.realised_pnl:>+12,.2f}",
            f"  📊 Positions:      {snap.positions_count:>12}",
            "",
        ]

        if snap.positions:
            lines.append("  ─── Open Positions ────────────────")
            for p in snap.positions:
                emoji = "🟢" if p.unrealised_pnl >= 0 else "🔴"
                lines.append(
                    f"  {emoji} {p.symbol:8s} "
                    f"{p.quantity:>6.1f} @ ${p.avg_entry_price:>8,.2f} "
                    f"→ ${p.current_price:>8,.2f} "
                    f"P&L: ${p.unrealised_pnl:>+8,.2f} ({p.unrealised_pnl_pct:>+.1f}%)"
                )

            # Allocation breakdown
            lines.append("")
            lines.append("  ─── Allocation ───────────────────")
            cash_pct = (snap.cash / snap.portfolio_value * 100) if snap.portfolio_value else 100
            lines.append(f"  💵 Cash:  {cash_pct:.1f}%")
            for p in snap.positions:
                lines.append(f"  📊 {p.symbol:8s} {p.weight_pct:.1f}%")

        lines.append("")
        lines.append("═══════════════════════════════════════")

        return "\n".join(lines)

    def telegram_report(self) -> str:
        """Generate a Telegram-formatted portfolio report (Markdown)."""
        snap = self._last_snapshot or self.update()

        return_emoji = "📈" if snap.total_return_pct >= 0 else "📉"

        lines = [
            "📊 *Portfolio Overview*\n",
            f"💰 Cash: ${snap.cash:,.2f}",
            f"📊 Equity: ${snap.equity:,.2f}",
            f"{return_emoji} Return: {snap.total_return_pct:+.2f}%\n",
            f"📗 Unrealised: ${snap.unrealised_pnl:+,.2f}",
            f"📕 Realised: ${snap.realised_pnl:+,.2f}",
        ]

        if snap.positions:
            lines.append(f"\n📈 *Positions ({snap.positions_count}):*")
            for p in snap.positions:
                emoji = "🟢" if p.unrealised_pnl >= 0 else "🔴"
                lines.append(
                    f"{emoji} *{p.symbol}*: {p.quantity} @ ${p.avg_entry_price:,.2f}"
                    f"\n   Now: ${p.current_price:,.2f} | "
                    f"P&L: ${p.unrealised_pnl:+,.2f} ({p.unrealised_pnl_pct:+.1f}%)"
                )

            # Top performer
            best = max(snap.positions, key=lambda x: x.unrealised_pnl_pct)
            worst = min(snap.positions, key=lambda x: x.unrealised_pnl_pct)
            lines.append(f"\n🏆 Best: {best.symbol} ({best.unrealised_pnl_pct:+.1f}%)")
            lines.append(f"💀 Worst: {worst.symbol} ({worst.unrealised_pnl_pct:+.1f}%)")
        else:
            lines.append("\n📭 No open positions")

        return "\n".join(lines)

    # ── Equity Curve ──────────────────────────────────────────────

    def get_equity_curve(self, days: int = 30) -> List[dict]:
        """
        Get equity curve data from database snapshots.

        Returns list of {timestamp, portfolio_value, daily_pnl}
        """
        if not self.db:
            return []

        snapshots = self.db.get_snapshots(limit=days * 24)  # hourly snapshots

        return [
            {
                "timestamp": s["timestamp"],
                "portfolio_value": s["portfolio_value"],
                "equity": s["equity"],
                "cash": s["cash"],
                "daily_pnl": s["daily_pnl"],
                "total_pnl": s["total_pnl"],
            }
            for s in reversed(snapshots)  # chronological
        ]

    def get_allocation(self) -> Dict[str, float]:
        """
        Get current portfolio allocation as {symbol: percentage}.
        """
        snap = self._last_snapshot or self.update()

        alloc = {}
        if snap.portfolio_value > 0:
            alloc["CASH"] = snap.cash / snap.portfolio_value * 100
            for p in snap.positions:
                alloc[p.symbol] = p.weight_pct

        return alloc

    # ── Performance Metrics ───────────────────────────────────────

    def get_metrics(self) -> dict:
        """
        Calculate portfolio performance metrics.
        """
        snap = self._last_snapshot or self.update()
        stats = self.db.get_stats() if self.db else {}

        return {
            "portfolio_value": snap.portfolio_value,
            "cash": snap.cash,
            "equity": snap.equity,
            "total_return_pct": snap.total_return_pct,
            "unrealised_pnl": snap.unrealised_pnl,
            "realised_pnl": snap.realised_pnl,
            "positions_count": snap.positions_count,
            "total_trades": stats.get("total_trades", 0),
            "win_rate": stats.get("win_rate", 0),
            "best_trade": stats.get("best_trade", 0),
            "worst_trade": stats.get("worst_trade", 0),
        }
