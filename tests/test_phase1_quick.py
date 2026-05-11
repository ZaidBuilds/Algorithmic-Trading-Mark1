"""
Quick verification script for Phase 1 event-driven architecture.

Tests:
1. All modules import without errors
2. Event creation & serialization
3. Settings with YAML loading
4. MessageBus instantiation (without Redis)

Usage: python tests/test_phase1_quick.py
"""

import sys
import os
import traceback

# Add project root to sys.path so quantumtrade and config can be imported
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_imports():
    print("Testing imports...")
    try:
        from quantumtrade.events import (
            MarketDataEvent, SignalEvent, OrderEvent,
            TradeEvent, RiskEvent, SystemEvent, MessageBus
        )
        print("  [OK] Events module")
    except Exception as e:
        print(f"  [FAIL] Events: {e}")
        return False

    try:
        from quantumtrade.events.handlers import MarketDataHandler, SignalHandler, OrderHandler
        print("  [OK] Handlers module")
    except Exception as e:
        print(f"  [FAIL] Handlers: {e}")
        return False

    try:
        from quantumtrade.config.config_schema import QuantumTradeSettings
        print("  [OK] Config schema")
    except Exception as e:
        print(f"  [FAIL] Config: {e}")
        return False

    try:
        from live.trading_engine import LiveTradingEngine
        print("  [OK] TradingEngine (backward compatible)")
    except Exception as e:
        print(f"  [FAIL] TradingEngine: {e}")
        return False

    return True


def test_events():
    print("\nTesting event creation...")
    try:
        from quantumtrade.events import MarketDataEvent, SignalEvent, OrderEvent, deserialize_event
        import json

        # Create market data
        md = MarketDataEvent(
            symbol="AAPL",
            timeframe="1m",
            ohlcv={"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000000}
        )
        assert md.validate(), "MarketDataEvent validation failed"
        print(f"  [OK] MarketDataEvent created: {md.event_id[:8]}...")

        # Serialize & deserialize
        json_str = md.to_json()
        recovered = deserialize_event(json_str, "market_data")
        assert recovered.symbol == "AAPL"
        print(f"  [OK] Serialization/deserialization works")

        # Signal
        sig = SignalEvent(
            symbol="AAPL",
            strategy="Test",
            signal_type="BUY",
            confidence=0.85,
            price=100.5
        )
        assert sig.validate()
        print(f"  [OK] SignalEvent created: confidence={sig.confidence}")

        # Order
        order = OrderEvent(
            symbol="AAPL",
            side="BUY",
            quantity=10,
            order_type="MARKET",
            broker="paper"
        )
        assert order.validate()
        print(f"  [OK] OrderEvent created: qty={order.quantity}")

        return True
    except Exception as e:
        print(f"  [FAIL] Event test failed: {e}")
        traceback.print_exc()
        return False


def test_settings():
    print("\nTesting settings...")
    try:
        from config.settings import settings
        print(f"  [OK] Settings loaded")
        print(f"    Broker: {settings.BROKER_NAME}")
        print(f"    Symbols: {settings.SYMBOLS}")
        print(f"    Message bus URL: {settings.MESSAGE_BUS_URL}")
        print(f"    Consumer group: {settings.CONSUMER_GROUP}")

        # Test YAML loading (if file exists)
        from pathlib import Path
        yaml_path = Path(settings.CONFIG_YAML_PATH)
        if yaml_path.exists():
            print(f"  [OK] YAML config found at {yaml_path}")
        else:
            print(f"    [INFO] YAML config not found (optional)")

        return True
    except Exception as e:
        print(f"  [FAIL] Settings test failed: {e}")
        traceback.print_exc()
        return False


def test_message_bus_instantiation():
    print("\nTesting MessageBus instantiation...")
    try:
        from quantumtrade.events.bus import MessageBus
        bus = MessageBus(redis_url="redis://localhost:6379/0")
        print(f"  [OK] MessageBus created")

        # Health check (Redis may not be running)
        try:
            healthy = bus.health_check()
            print(f"  {'[OK]' if healthy else '[WARN]'} Redis health: {'OK' if healthy else 'Not running'}")
        except Exception as e:
            print(f"  [WARN] Redis not reachable: {e} (OK for offline test)")

        bus.close()
        return True
    except Exception as e:
        print(f"  [FAIL] MessageBus test failed: {e}")
        traceback.print_exc()
        return False


def test_handler_initialization():
    print("\nTesting handler initialization...")
    try:
        from quantumtrade.events.handlers import MarketDataHandler, SignalHandler, OrderHandler
        from quantumtrade.events import MarketDataEvent, SignalEvent, OrderEvent

        # MarketDataHandler
        md_handler = MarketDataHandler(calculate_indicators=True)
        print(f"  [OK] MarketDataHandler initialized")

        # SignalHandler
        sig_handler = SignalHandler()
        print(f"  [OK] SignalHandler initialized")

        # OrderHandler
        order_handler = OrderHandler()
        print(f"  [OK] OrderHandler initialized")

        return True
    except Exception as e:
        print(f"  [FAIL] Handler initialization failed: {e}")
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("PHASE 1 EVENT-DRIVEN ARCHITECTURE — VERIFICATION")
    print("=" * 60)

    results = [
        test_imports(),
        test_events(),
        test_settings(),
        test_message_bus_instantiation(),
        test_handler_initialization(),
    ]

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} test groups passed")

    if all(results):
        print("[OK] Phase 1 implementation verified successfully!")
        return 0
    else:
        print("[FAIL] Some tests failed — review output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
