"""
Execution module for placing orders and managing trades.

This module provides broker clients for different asset classes:
- PaperBroker: Paper trading / simulated execution
- StocksBroker: Real-time stocks execution
- CryptoBroker: Real-time crypto execution
- ForexBroker: Real-time forex execution
"""

from .broker_client import BaseBroker, PaperBroker

__all__ = ['BaseBroker', 'PaperBroker']
