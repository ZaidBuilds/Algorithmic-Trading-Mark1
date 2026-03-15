"""
Trade Repository — High-level trade operations built on the Database.

Provides convenient methods for logging, querying, and analyzing trades
without dealing with raw SQL.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from .db import Database, get_db

logger = logging.getLogger(__name__)


class TradeRepository:
    """
    High-level trade management on top of SQLite.

    Usage:
        repo = TradeRepository()
        repo.record_buy("AAPL", 10, 175.50, strategy="EMA Crossover")
        repo.record_sell("AAPL", 10, 180.00, pnl=45.00)
        print(repo.summary())
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    # ─── Record Trades ────────────────────────────────────────────

    def record_buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        strategy: str = "",
        confidence: float = 0.0,
        broker: str = "paper",
        order_id: str = "",
    ) -> int:
        """Record a BUY trade."""
        trade_id = self.db.log_trade(
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            price=price,
            strategy=strategy,
            confidence=confidence,
            broker=broker,
            order_id=order_id,
        )
        logger.info(
            f"📗 BUY recorded: {quantity} {symbol} @ ${price:,.2f} "
            f"[{strategy}] → ID #{trade_id}"
        )
        return trade_id

    def record_sell(
        self,
        symbol: str,
        quantity: float,
        price: float,
        pnl: float = 0.0,
        strategy: str = "",
        confidence: float = 0.0,
        broker: str = "paper",
        order_id: str = "",
    ) -> int:
        """Record a SELL trade with P&L."""
        trade_id = self.db.log_trade(
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            price=price,
            pnl=pnl,
            strategy=strategy,
            confidence=confidence,
            broker=broker,
            order_id=order_id,
        )
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        logger.info(
            f"📕 SELL recorded: {quantity} {symbol} @ ${price:,.2f} "
            f"{pnl_emoji} P&L: ${pnl:+,.2f} → ID #{trade_id}"
        )
        return trade_id

    # ─── Queries ──────────────────────────────────────────────────

    def recent_trades(self, limit: int = 10) -> List[dict]:
        """Get the N most recent trades."""
        return self.db.get_trades(limit=limit)

    def trades_for_symbol(self, symbol: str, limit: int = 50) -> List[dict]:
        """Get trades for a specific symbol."""
        return self.db.get_trades(symbol=symbol, limit=limit)

    def trades_today(self) -> List[dict]:
        """Get all trades from today."""
        return self.db.get_trades_today()

    def trades_this_week(self) -> List[dict]:
        """Get trades from the past 7 days."""
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        return self.db.get_trades(since=week_ago, limit=500)

    # ─── Analytics ────────────────────────────────────────────────

    def summary(self) -> str:
        """Generate a formatted trading summary."""
        stats = self.db.get_stats()

        lines = [
            "═══════════════════════════════════",
            "     📊 TRADING SUMMARY",
            "═══════════════════════════════════",
            f"  Total Trades:  {stats['total_trades']}",
            f"  Total P&L:     ${stats['total_pnl']:+,.2f}",
            f"  Today's P&L:   ${stats['daily_pnl']:+,.2f}",
            f"  Win Rate:      {stats['win_rate']:.1f}%",
            f"  Wins / Losses: {stats['wins']} / {stats['losses']}",
            f"  Best Trade:    ${stats['best_trade']:+,.2f}",
            f"  Worst Trade:   ${stats['worst_trade']:+,.2f}",
            "═══════════════════════════════════",
        ]
        return "\n".join(lines)

    def pnl_report(self) -> str:
        """Generate P&L breakdown by symbol."""
        by_symbol = self.db.get_pnl_by_symbol()

        if not by_symbol:
            return "No trades recorded yet."

        lines = ["📊 P&L by Symbol:", "─────────────────────────"]
        for s in by_symbol:
            emoji = "🟢" if s["total_pnl"] >= 0 else "🔴"
            lines.append(
                f"  {emoji} {s['symbol']:8s}  "
                f"${s['total_pnl']:+10,.2f}  "
                f"({s['trade_count']} trades)"
            )

        by_strategy = self.db.get_pnl_by_strategy()
        if by_strategy:
            lines.append("")
            lines.append("📊 P&L by Strategy:")
            lines.append("─────────────────────────")
            for s in by_strategy:
                emoji = "🟢" if s["total_pnl"] >= 0 else "🔴"
                lines.append(
                    f"  {emoji} {s['strategy']:20s}  "
                    f"${s['total_pnl']:+10,.2f}  "
                    f"(avg: ${s['avg_pnl']:+,.2f})"
                )

        return "\n".join(lines)

    # ─── Snapshot ─────────────────────────────────────────────────

    def take_snapshot(
        self,
        cash: float,
        equity: float,
        portfolio_value: float,
        positions_count: int = 0,
    ) -> None:
        """Take and store a portfolio snapshot."""
        total_pnl = self.db.get_total_pnl()
        daily_pnl = self.db.get_daily_pnl()

        self.db.save_snapshot(
            cash=cash,
            equity=equity,
            portfolio_value=portfolio_value,
            positions_count=positions_count,
            daily_pnl=daily_pnl,
            total_pnl=total_pnl,
        )
