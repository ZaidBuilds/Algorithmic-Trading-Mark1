"""QuantumTrade — Event-Driven Trading System.

Main package entry point. Provides access to core components.
"""

from quantumtrade.events import (
    BaseEvent,
    MarketDataEvent,
    SignalEvent,
    OrderEvent,
    TradeEvent,
    RiskEvent,
    SystemEvent,
    MessageBus,
    get_message_bus,
)
from quantumtrade.config.config_schema import (
    QuantumTradeSettings,
    DatabaseConfig,
    RedisConfig,
    BrokerConfig,
    StrategyConfig,
    RiskConfig,
    NotificationConfig,
    LoggingConfig,
    APIConfig,
    EventBusConfig,
)

__version__ = "2.0.0-event-driven"
__author__ = "Zaid"

__all__ = [
    # Events
    "BaseEvent",
    "MarketDataEvent",
    "SignalEvent",
    "OrderEvent",
    "TradeEvent",
    "RiskEvent",
    "SystemEvent",
    "MessageBus",
    "get_message_bus",
    # Config
    "QuantumTradeSettings",
    "DatabaseConfig",
    "RedisConfig",
    "BrokerConfig",
    "StrategyConfig",
    "RiskConfig",
    "NotificationConfig",
    "LoggingConfig",
    "APIConfig",
    "EventBusConfig",
]
