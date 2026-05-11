"""
Event system — message bus and event types.

This module provides the event-driven architecture for QuantumTrade.
Events flow through Redis Streams to decouple system components.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Standard event type enumeration."""
    MARKET_DATA = "market_data"
    SIGNAL = "signal"
    ORDER = "order"
    TRADE = "trade"
    RISK = "risk"
    SYSTEM = "system"
    ERROR = "error"


@dataclass
class BaseEvent:
    """Base class for all events in the system."""
    event_type: str
    timestamp: datetime
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


@dataclass
class MarketDataEvent(BaseEvent):
    """Market data update event."""
    symbol: str
    price: float
    volume: float

    def __init__(self, symbol: str, price: float, volume: float, timestamp: datetime = None):
        super().__init__(
            event_type=EventType.MARKET_DATA,
            timestamp=timestamp or datetime.now(),
            data={
                "symbol": symbol,
                "price": price,
                "volume": volume,
            },
        )
        self.symbol = symbol
        self.price = price
        self.volume = volume


@dataclass
class SignalEvent(BaseEvent):
    """Trading signal event from strategy."""
    symbol: str
    side: str  # "BUY" or "SELL"
    strength: float
    strategy_name: str

    def __init__(self, symbol: str, side: str, strength: float, strategy_name: str, timestamp: datetime = None):
        super().__init__(
            event_type=EventType.SIGNAL,
            timestamp=timestamp or datetime.now(),
            data={
                "symbol": symbol,
                "side": side,
                "strength": strength,
                "strategy_name": strategy_name,
            },
        )
        self.symbol = symbol
        self.side = side
        self.strength = strength
        self.strategy_name = strategy_name


@dataclass
class OrderEvent(BaseEvent):
    """Order submission event."""
    symbol: str
    side: str
    quantity: float
    order_type: str = "MARKET"

    def __init__(self, symbol: str, side: str, quantity: float, order_type: str = "MARKET", timestamp: datetime = None):
        super().__init__(
            event_type=EventType.ORDER,
            timestamp=timestamp or datetime.now(),
            data={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": order_type,
            },
        )
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.order_type = order_type


@dataclass
class TradeEvent(BaseEvent):
    """Trade execution event."""
    symbol: str
    side: str
    quantity: float
    price: float
    trade_id: str

    def __init__(self, symbol: str, side: str, quantity: float, price: float, trade_id: str, timestamp: datetime = None):
        super().__init__(
            event_type=EventType.TRADE,
            timestamp=timestamp or datetime.now(),
            data={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "trade_id": trade_id,
            },
        )
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.trade_id = trade_id


@dataclass
class RiskEvent(BaseEvent):
    """Risk metrics update event."""
    var_95: float
    var_99: float
    gross_exposure: float
    net_exposure: float

    def __init__(
        self,
        event_type: str = "risk_update",
        timestamp: datetime = None,
        data: Dict[str, Any] = None,
        var_95: float = 0.0,
        var_99: float = 0.0,
        gross_exposure: float = 0.0,
        net_exposure: float = 0.0,
    ):
        if data is None:
            data = {
                "var_95": var_95,
                "var_99": var_99,
                "gross_exposure": gross_exposure,
                "net_exposure": net_exposure,
            }
        super().__init__(event_type=event_type, timestamp=timestamp or datetime.now(), data=data)
        self.var_95 = var_95
        self.var_99 = var_99
        self.gross_exposure = gross_exposure
        self.net_exposure = net_exposure


@dataclass
class SystemEvent(BaseEvent):
    """System-level event (startup, shutdown, error)."""
    level: str  # "INFO", "WARNING", "ERROR", "CRITICAL"
    component: str
    message: str

    def __init__(
        self,
        level: str,
        component: str,
        message: str,
        timestamp: datetime = None,
    ):
        super().__init__(
            event_type=EventType.SYSTEM,
            timestamp=timestamp or datetime.now(),
            data={
                "level": level,
                "component": component,
                "message": message,
            },
        )
        self.level = level
        self.component = component
        self.message = message


class MessageBus:
    """
    Simple Redis-based message bus for event pub/sub.

    Uses Redis Streams for reliable message delivery with consumer groups.
    """

    def __init__(self, redis_client=None, stream_prefix: str = "qt"):
        self.redis = redis_client
        self.stream_prefix = stream_prefix
        self._consumer_id = f"consumer-{datetime.now().timestamp()}"

    def publish(self, event: BaseEvent) -> bool:
        """Publish event to appropriate stream."""
        if not self.redis:
            logger = logging.getLogger(__name__)
            logger.warning("No Redis client — MessageBus publish skipped")
            return False

        try:
            stream_name = f"{self.stream_prefix}:{event.event_type}"
            payload = event.to_dict()
            payload["_id"] = f"{self._consumer_id}:{datetime.now().timestamp()}"

            self.redis.xadd(stream_name, payload, maxlen=10000)
            return True
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"MessageBus publish failed: {e}")
            return False

    async def publish_async(self, event: BaseEvent) -> bool:
        """Async version of publish."""
        return self.publish(event)

    def subscribe(self, event_type: str, callback):
        """Subscribe to events of a given type."""
        pass  # To be implemented

    def create_consumer_group(self, stream_name: str, group_name: str):
        """Create a Redis consumer group."""
        if not self.redis:
            return
        try:
            self.redis.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except Exception:
            pass  # Group may already exist

def deserialize_event(json_str: str, event_type: Optional[str] = None) -> Any:
    """Deserialize an event payload used by legacy unit tests.

    The current `quantumtrade/events.py` defines a simplified event model.
    Tests expect a helper that can infer event type from payload keys.
    """
    import json as _json

    payload = _json.loads(json_str)

    # Infer event type if not explicitly provided
    inferred_type = event_type
    if inferred_type is None:
        # Prefer explicit `event_type` / `source` fields
        inferred_type = payload.get("event_type") or payload.get("type")
        if inferred_type is None:
            # Infer based on presence of known payload fields
            if "ohlcv" in payload:
                inferred_type = "market_data"
            elif "signal_type" in payload or "confidence" in payload:
                inferred_type = "signal"
            elif "order_type" in payload or "quantity" in payload and "status" in payload:
                inferred_type = "order"
            else:
                inferred_type = "market_data"

    inferred_type = str(inferred_type).lower()

    if inferred_type == "market_data":
        return MarketDataEvent(
            symbol=payload["symbol"],
            timeframe=payload.get("timeframe", ""),
            ohlcv=payload.get("ohlcv", {}),
            source=payload.get("source", ""),
            event_id=payload.get("event_id"),
            version=payload.get("version", "1.0"),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
        )
    if inferred_type == "signal":
        return SignalEvent(
            symbol=payload["symbol"],
            strategy=payload.get("strategy", payload.get("strategy_name", "")),
            signal_type=payload["signal_type"],
            confidence=payload.get("confidence", 0.0),
            price=payload.get("price", 0.0),
            source=payload.get("source", ""),
            event_id=payload.get("event_id"),
            version=payload.get("version", "1.0"),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            metadata=payload.get("metadata", {}),
        )

    if inferred_type == "order":
        return OrderEvent(
            order_id=payload.get("order_id"),
            symbol=payload.get("symbol", ""),
            side=payload.get("side", payload.get("signal_type", "")),
            quantity=payload.get("quantity", 0),
            order_type=payload.get("order_type", "MARKET"),
            broker=payload.get("broker", ""),
            source=payload.get("source", ""),
            status=payload.get("status", "PENDING"),
            event_id=payload.get("event_id"),
            version=payload.get("version", "1.0"),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
        )

    # Fallback: if we can't match, return BaseEvent with raw data
    return BaseEvent(
        event_id=payload.get("event_id"),
        timestamp=datetime.fromisoformat(payload["timestamp"]),
        source=payload.get("source", ""),
        version=payload.get("version", "1.0"),
        data=payload,
    )


def get_message_bus(redis_url: str = "redis://localhost:6379/0") -> "MessageBus":
    """Get singleton message bus instance."""

    if not hasattr(get_message_bus, "_instance"):
        try:
            import redis
            try:
                client = redis.from_url(redis_url)
                get_message_bus._instance = MessageBus(client)
            except Exception:
                get_message_bus._instance = MessageBus(None)
        except ImportError:
            get_message_bus._instance = MessageBus(None)
    return get_message_bus._instance
