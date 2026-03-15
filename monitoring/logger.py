"""
Monitoring logger module - re-exports from utils.logger for consistency.

This module provides a central import point for logging functionality used
throughout the trading system.
"""

from utils.logger import setup_logger, get_trade_logger

# Default logger for trading system
logger = setup_logger(
    name="TradingBot",
    log_file="trading_bot.log",
    log_dir="logs",
    level="INFO",
    console_level="INFO"
)

__all__ = ['setup_logger', 'get_trade_logger', 'logger']
