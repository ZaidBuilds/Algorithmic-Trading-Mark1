"""Unit tests for event-driven architecture.

Run: pytest tests/test_events.py -v
"""

import pytest
import json
from datetime import datetime
from uuid import UUID

from quantumtrade.events import (
    BaseEvent,
    MarketDataEvent,
    SignalEvent,
    OrderEvent,
    TradeEvent,
    RiskEvent,
    SystemEvent,
    deserialize_event,
)


# ─────────────────────────────────────────────────────────────────────────────
# BaseEvent
# ─────────────────────────────────────────────────────────────────────────────

def test_base_event_has_required_fields():
    event = BaseEvent(source="test")
    assert event.event_id is not None
    assert UUID(event.event_id)  # valid UUID
    assert event.timestamp is not None
    assert event.source == "test"
    assert event.version == "1.0"


def test_base_event_serialization():
    event = BaseEvent(source="test_source")
    json_str = event.to_json()
    parsed = json.loads(json_str)

    assert parsed["event_id"] == event.event_id
    assert parsed["source"] == "test_source"
    assert "timestamp" in parsed
    assert parsed["version"] == "1.0"


def test_base_event_deserialization():
    json_str = '{"event_id": "123", "timestamp": "2024-01-01T00:00:00", "source": "test", "version": "1.0"}'
    event = BaseEvent.from_json(json_str)
    assert event.event_id == "123"
    assert event.source == "test"


# ─────────────────────────────────────────────────────────────────────────────
# MarketDataEvent
# ─────────────────────────────────────────────────────────────────────────────

def test_market_data_event_validates_ohlcv():
    # Valid
    event = MarketDataEvent(
        symbol="AAPL",
        timeframe="1m",
        ohlcv={"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000000}
    )
    assert event.validate() is True

    # Missing required field
    event_invalid = MarketDataEvent(symbol="AAPL", timeframe="1m", ohlcv={"open": 100})
    assert event_invalid.validate() is False


def test_market_data_event_serialization():
    event = MarketDataEvent(
        symbol="AAPL",
        timeframe="5m",
        ohlcv={"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000000}
    )
    json_str = event.to_json()
    parsed = json.loads(json_str)

    assert parsed["symbol"] == "AAPL"
    assert parsed["timeframe"] == "5m"
    assert parsed["ohlcv"]["close"] == 100.5


# ─────────────────────────────────────────────────────────────────────────────
# SignalEvent
# ─────────────────────────────────────────────────────────────────────────────

def test_signal_event_clamps_confidence():
    event = SignalEvent(
        symbol="AAPL",
        strategy="TestStrategy",
        signal_type="BUY",
        confidence=1.5,  # Out of range
        price=100.0
    )
    # __post_init__ clamps to [0, 1]
    assert event.confidence == 1.0

    event2 = SignalEvent(
        symbol="AAPL",
        strategy="TestStrategy",
        signal_type="SELL",
        confidence=-0.5,
        price=100.0
    )
    assert event2.confidence == 0.0


def test_signal_event_validation():
    valid_event = SignalEvent(
        symbol="GOOGL",
        strategy="EMA",
        signal_type="BUY",
        confidence=0.85,
        price=1500.0
    )
    assert valid_event.validate() is True

    invalid_event = SignalEvent(
        symbol="GOOGL",
        strategy="EMA",
        signal_type="BUY",
        confidence=0.85,
        price=0.0  # Invalid price
    )
    assert invalid_event.validate() is False


# ─────────────────────────────────────────────────────────────────────────────
# OrderEvent
# ─────────────────────────────────────────────────────────────────────────────

def test_order_event_defaults():
    event = OrderEvent(symbol="AAPL", side="BUY", quantity=10)
    assert event.order_type == "MARKET"
    assert event.status == "PENDING"
    assert event.broker == ""


def test_order_event_validation():
    valid = OrderEvent(
        order_id="order-123",
        symbol="AAPL",
        side="BUY",
        quantity=100,
        order_type="MARKET",
        broker="alpaca"
    )
    assert valid.validate() is True

    invalid = OrderEvent(symbol="", quantity=10)
    assert invalid.validate() is False


# ─────────────────────────────────────────────────────────────────────────────
# TradeEvent
# ─────────────────────────────────────────────────────────────────────────────

def test_trade_event():
    event = TradeEvent(
        trade_id="trade-456",
        symbol="AAPL",
        side="BUY",
        quantity=50,
        price=150.0,
        pnl=100.0,
        strategy="EMA",
        broker="alpaca"
    )
    assert event.validate() is True
    assert event.price == 150.0


# ─────────────────────────────────────────────────────────────────────────────
# SystemEvent
# ─────────────────────────────────────────────────────────────────────────────

def test_system_event():
    event = SystemEvent(
        component="risk_engine",
        level="WARNING",
        message="Position limit reached"
    )
    assert event.validate() is True
    assert event.source == "system"

    event_invalid = SystemEvent(component="", message="test")
    assert event_invalid.validate() is False


# ─────────────────────────────────────────────────────────────────────────────
# Deserialization
# ─────────────────────────────────────────────────────────────────────────────

def test_deserialize_market_data():
    data = json.dumps({
        "event_id": "uuid-123",
        "timestamp": "2024-01-01T12:00:00",
        "source": "data_feed",
        "version": "1.0",
        "symbol": "AAPL",
        "timeframe": "1m",
        "ohlcv": {"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000}
    })
    event = deserialize_event(data, "market_data")
    assert isinstance(event, MarketDataEvent)
    assert event.symbol == "AAPL"


def test_deserialize_signal():
    data = json.dumps({
        "event_id": "uuid-456",
        "timestamp": "2024-01-01T12:00:01",
        "source": "strategy",
        "symbol": "GOOGL",
        "strategy": "RSI",
        "signal_type": "BUY",
        "confidence": 0.75,
        "price": 1500.0
    })
    event = deserialize_event(data, "signal")
    assert isinstance(event, SignalEvent)
    assert event.signal_type == "BUY"
    assert event.confidence == 0.75


def test_deserialize_infers_type():
    """If event_type not specified, infer from payload."""
    data = json.dumps({
        "event_id": "uuid-789",
        "timestamp": "2024-01-01T12:00:02",
        "symbol": "AAPL",
        "timeframe": "5m",
        "ohlcv": {"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000}
    })
    event = deserialize_event(data)
    assert isinstance(event, MarketDataEvent)


# ─────────────────────────────────────────────────────────────────────────────
# Integration Simulation
# ─────────────────────────────────────────────────────────────────────────────

def test_event_flow():
    """Simulate: MarketData → Signal → Order → Trade."""
    # 1. Market data event
    md = MarketDataEvent(
        symbol="AAPL",
        timeframe="1m",
        ohlcv={"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000000},
        source="data_feed"
    )
    assert md.validate()

    # 2. Signal generated (in real system, by MarketDataHandler)
    sig = SignalEvent(
        symbol=md.symbol,
        strategy="Momentum",
        signal_type="BUY",
        confidence=0.72,
        price=md.ohlcv["close"],
        metadata={"indicator": "rsi_oversold"},
        source="strategy_engine"
    )
    assert sig.validate()

    # 3. Order placed (by SignalHandler)
    order = OrderEvent(
        symbol=sig.symbol,
        side=sig.signal_type,
        quantity=10,
        order_type="MARKET",
        broker="paper",
        source="signal_handler"
    )
    assert order.validate()

    # 4. Trade filled (by OrderHandler)
    trade = TradeEvent(
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        price=sig.price,
        pnl=0.0,
        strategy=sig.strategy,
        broker=order.broker,
        source="order_handler"
    )
    assert trade.validate()

    print("✓ Event flow test passed")
