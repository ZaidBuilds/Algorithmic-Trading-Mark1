"""
SQLite Database Manager.

Zero-config, zero-cost, zero-server database.
The DB file lives at data/quantumtrade.db by default.
All tables are auto-created on first connection.
"""

import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = os.path.join("data", "quantumtrade.db")

# Singleton instance
_db_instance: Optional["Database"] = None


class Database:
    """
    SQLite database manager for QuantumTrade.

    Features:
      - Auto-creates tables on first use
      - Thread-safe (check_same_thread=False)
      - WAL mode for better concurrent read/write
      - Simple API: just call methods, no ORM overhead
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        # Connect
        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False,  # Safe for our use case
        )
        self.conn.row_factory = sqlite3.Row  # Dict-like access
        self.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        self.conn.execute("PRAGMA foreign_keys=ON")

        # Create tables
        self._create_tables()

        logger.info(f"📁 Database connected: {db_path}")

    def _create_tables(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.executescript("""
            -- ═══════════════════════════════════════
            -- Trade History
            -- ═══════════════════════════════════════
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
                symbol          TEXT NOT NULL,
                side            TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                quantity        REAL NOT NULL,
                price           REAL NOT NULL,
                total_value     REAL NOT NULL,
                commission      REAL DEFAULT 0.0,
                pnl             REAL DEFAULT 0.0,
                strategy        TEXT DEFAULT '',
                confidence      REAL DEFAULT 0.0,
                broker          TEXT DEFAULT 'paper',
                order_id        TEXT DEFAULT '',
                status          TEXT DEFAULT 'FILLED',
                notes           TEXT DEFAULT ''
            );

            -- ═══════════════════════════════════════
            -- Signal Audit Log
            -- ═══════════════════════════════════════
            CREATE TABLE IF NOT EXISTS signals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
                symbol          TEXT NOT NULL,
                signal_type     TEXT NOT NULL CHECK(signal_type IN ('BUY', 'SELL', 'HOLD')),
                price           REAL NOT NULL,
                confidence      REAL DEFAULT 0.0,
                strategy        TEXT DEFAULT '',
                reason          TEXT DEFAULT '',
                executed        INTEGER DEFAULT 0
            );

            -- ═══════════════════════════════════════
            -- Portfolio Snapshots (periodic P&L tracking)
            -- ═══════════════════════════════════════
            CREATE TABLE IF NOT EXISTS snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
                cash            REAL NOT NULL,
                equity          REAL NOT NULL,
                portfolio_value REAL NOT NULL,
                positions_count INTEGER DEFAULT 0,
                daily_pnl       REAL DEFAULT 0.0,
                total_pnl       REAL DEFAULT 0.0
            );

            -- ═══════════════════════════════════════
            -- Key-Value Settings Store
            -- ═══════════════════════════════════════
            CREATE TABLE IF NOT EXISTS settings_kv (
                key             TEXT PRIMARY KEY,
                value           TEXT NOT NULL,
                updated_at      TEXT DEFAULT (datetime('now'))
            );

            -- ═══════════════════════════════════════
            -- Indexes for fast queries
            -- ═══════════════════════════════════════
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
            CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
            CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
        """)
        self.conn.commit()

    # ─── Trades ───────────────────────────────────────────────────

    def log_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        pnl: float = 0.0,
        commission: float = 0.0,
        strategy: str = "",
        confidence: float = 0.0,
        broker: str = "paper",
        order_id: str = "",
        notes: str = "",
    ) -> int:
        """Log a trade to the database. Returns the trade ID."""
        cursor = self.conn.execute(
            """INSERT INTO trades
               (symbol, side, quantity, price, total_value, commission,
                pnl, strategy, confidence, broker, order_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol, side.upper(), quantity, price,
                quantity * price, commission, pnl,
                strategy, confidence, broker, order_id, notes,
            ),
        )
        self.conn.commit()
        logger.debug(f"Trade logged: {side} {quantity} {symbol} @ ${price}")
        return cursor.lastrowid

    def get_trades(
        self,
        symbol: str = None,
        side: str = None,
        strategy: str = None,
        limit: int = 50,
        since: str = None,
    ) -> list:
        """Fetch trades with optional filters."""
        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if side:
            query += " AND side = ?"
            params.append(side.upper())
        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        if since:
            query += " AND timestamp >= ?"
            params.append(since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_trade_count(self) -> int:
        """Total number of trades."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM trades").fetchone()
        return row["cnt"]

    def get_total_pnl(self) -> float:
        """Sum of all realized P&L."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(pnl), 0.0) as total FROM trades"
        ).fetchone()
        return row["total"]

    def get_daily_pnl(self, date_str: str = None) -> float:
        """P&L for a specific day (default: today)."""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT COALESCE(SUM(pnl), 0.0) as total FROM trades "
            "WHERE timestamp LIKE ?",
            (f"{date_str}%",),
        ).fetchone()
        return row["total"]

    def get_trades_today(self) -> list:
        """Get all trades from today."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_trades(since=today, limit=100)

    def get_pnl_by_symbol(self) -> list:
        """P&L breakdown by symbol."""
        rows = self.conn.execute(
            """SELECT symbol,
                      COUNT(*) as trade_count,
                      SUM(pnl) as total_pnl,
                      SUM(CASE WHEN side='BUY' THEN total_value ELSE 0 END) as total_bought,
                      SUM(CASE WHEN side='SELL' THEN total_value ELSE 0 END) as total_sold
               FROM trades GROUP BY symbol ORDER BY total_pnl DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pnl_by_strategy(self) -> list:
        """P&L breakdown by strategy."""
        rows = self.conn.execute(
            """SELECT strategy,
                      COUNT(*) as trade_count,
                      SUM(pnl) as total_pnl,
                      AVG(pnl) as avg_pnl
               FROM trades WHERE strategy != ''
               GROUP BY strategy ORDER BY total_pnl DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Signals ──────────────────────────────────────────────────

    def log_signal(
        self,
        symbol: str,
        signal_type: str,
        price: float,
        confidence: float = 0.0,
        strategy: str = "",
        reason: str = "",
        executed: bool = False,
    ) -> int:
        """Log a signal for audit trail."""
        cursor = self.conn.execute(
            """INSERT INTO signals
               (symbol, signal_type, price, confidence, strategy, reason, executed)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (symbol, signal_type.upper(), price, confidence, strategy, reason, int(executed)),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ─── Snapshots ────────────────────────────────────────────────

    def save_snapshot(
        self,
        cash: float,
        equity: float,
        portfolio_value: float,
        positions_count: int = 0,
        daily_pnl: float = 0.0,
        total_pnl: float = 0.0,
    ) -> None:
        """Save a portfolio snapshot."""
        self.conn.execute(
            """INSERT INTO snapshots
               (cash, equity, portfolio_value, positions_count, daily_pnl, total_pnl)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cash, equity, portfolio_value, positions_count, daily_pnl, total_pnl),
        )
        self.conn.commit()

    def get_snapshots(self, limit: int = 100) -> list:
        """Get recent portfolio snapshots."""
        rows = self.conn.execute(
            "SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Settings KV ──────────────────────────────────────────────

    def set_setting(self, key: str, value: str) -> None:
        """Set a key-value setting."""
        self.conn.execute(
            """INSERT OR REPLACE INTO settings_kv (key, value, updated_at)
               VALUES (?, ?, datetime('now'))""",
            (key, value),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        """Get a setting value."""
        row = self.conn.execute(
            "SELECT value FROM settings_kv WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    # ─── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall trading statistics."""
        total_trades = self.get_trade_count()
        total_pnl = self.get_total_pnl()
        daily_pnl = self.get_daily_pnl()

        wins = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM trades WHERE pnl > 0"
        ).fetchone()["cnt"]

        losses = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM trades WHERE pnl < 0"
        ).fetchone()["cnt"]

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        best = self.conn.execute(
            "SELECT COALESCE(MAX(pnl), 0) as best FROM trades"
        ).fetchone()["best"]

        worst = self.conn.execute(
            "SELECT COALESCE(MIN(pnl), 0) as worst FROM trades"
        ).fetchone()["worst"]

        return {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "daily_pnl": daily_pnl,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "best_trade": best,
            "worst_trade": worst,
        }

    # ─── Cleanup ──────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
        logger.info("Database connection closed")


def get_db(db_path: str = DEFAULT_DB_PATH) -> Database:
    """Get or create the singleton Database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
