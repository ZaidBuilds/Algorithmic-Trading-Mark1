"""
Database module — persistent storage for QuantumTrade.

Uses SQLite (zero-config, no server needed, free).

Tables:
  - trades       : Every trade executed
  - signals      : Signal audit log
  - snapshots    : Portfolio value over time
  - settings_kv  : Key-value settings store

Usage:
    from database import get_db
    db = get_db()
    db.log_trade(...)
    trades = db.get_trades(symbol="AAPL")
"""

from .db import Database, get_db
from .trade_repository import TradeRepository

__all__ = ["Database", "get_db", "TradeRepository"]
