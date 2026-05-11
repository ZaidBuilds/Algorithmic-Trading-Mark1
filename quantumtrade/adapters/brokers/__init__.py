"""
Broker integrations for real-money and paper trading.

Supported Brokers:
    - Alpaca   : US stocks & crypto (paper + live)
    - Binance  : Crypto spot trading (testnet + live)
    - Paper    : Local simulated broker (no real money)

Usage:
    from brokers import get_broker
    broker = get_broker("alpaca")  # or "binance", "paper"
"""

from .base import BaseBroker, BrokerOrder, OrderResult
from .alpaca_broker import AlpacaBroker
from .binance_broker import BinanceBroker
from .paper_broker import PaperBroker


def get_broker(name: str, **kwargs) -> BaseBroker:
    """
    Factory function to get the correct broker instance.

    Args:
        name: Broker name — "alpaca", "binance", or "paper"
        **kwargs: Broker-specific config (api_key, api_secret, etc.)

    Returns:
        Configured BaseBroker instance

    Raises:
        ValueError: If broker name is unknown
    """
    brokers = {
        "alpaca": AlpacaBroker,
        "binance": BinanceBroker,
        "paper": PaperBroker,
    }

    name_lower = name.lower().strip()
    if name_lower not in brokers:
        raise ValueError(
            f"Unknown broker: '{name}'. Supported: {list(brokers.keys())}"
        )

    return brokers[name_lower](**kwargs)


__all__ = [
    "BaseBroker",
    "BrokerOrder",
    "OrderResult",
    "AlpacaBroker",
    "BinanceBroker",
    "PaperBroker",
    "get_broker",
]
