"""
Logging configuration for the trading system.

This module sets up comprehensive logging for:
- Console output (INFO level and above)
- File logging (DEBUG level and above)
- Trade logs
- Error tracking
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(
    name: str = "TradingBot",
    log_file: Optional[str] = None,
    log_dir: str = "logs",
    level: str = "INFO",
    console_level: str = "INFO"
) -> logging.Logger:
    """
    Set up and configure a logger for the trading system.
    
    Args:
        name: Logger name
        log_file: Optional log file name (defaults to trading_bot_YYYYMMDD.log)
        log_dir: Directory for log files (default: logs/)
        level: File logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_level: Console logging level
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, console_level.upper()))
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_file or log_dir:
        # Create logs directory
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Default log file name with date
        if log_file is None:
            log_file = f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
        
        log_file_path = log_path / log_file
        
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Logging to file: {log_file_path}")
    
    return logger


def get_trade_logger(name: str = "TradeLogger", log_file: str = "trades.log") -> logging.Logger:
    """
    Get a specialized logger for trade logging.
    
    Args:
        name: Logger name
        log_file: Trade log file name
    
    Returns:
        Configured trade logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Trade log formatter (simpler, CSV-friendly format)
    trade_formatter = logging.Formatter(
        '%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler for trades
    log_path = Path("logs")
    log_path.mkdir(parents=True, exist_ok=True)
    
    trade_file = log_path / log_file
    file_handler = logging.FileHandler(trade_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(trade_formatter)
    logger.addHandler(file_handler)
    
    return logger

