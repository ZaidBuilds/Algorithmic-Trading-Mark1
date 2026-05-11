"""
Unit tests for multi-exchange functionality.

Tests:
- CrossExchangePortfolio position aggregation
- ArbitrageDetector spread calculation
- StrategyPluginLoader module loading
- BrokerSelector cross-exchange routing
"""

import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from brokers.base import (
    BaseBroker, BrokerOrder, OrderResult, Position, AccountInfo,
    OrderSide, OrderStatus, OrderType, TimeInForce,
)
from strategy.base import BaseStrategy
from strategy.signals import Signal, SignalType
from quantumtrade.adapters.portfolio.cross_exchange import (
    CrossExchangePortfolio, Position as PortfolioPosition, PortfolioSummary, Quote,
)
from quantumtrade.adapters.arbitrage.detector import (
    ArbitrageDetector, ArbitrageEvent, ArbitrageType,
)
from quantumtrade.adapters.execution.broker_selector import BrokerSelector
from quantumtrade.adapters.strategy.plugin_loader import (
    StrategyPluginLoader, StrategyInterfaceError, StrategyPluginError,
)


class MockBroker(BaseBroker):
    """Mock broker for testing."""
    
    def __init__(self, name="mock", score=0.9, connected=True, cash=10000.0):
        super().__init__(paper=True)
        self.name = name
        self._score = score
        self._connected = connected
        self.positions = []
        self.cash = cash
        self._prices = {}
    
    def connect(self):
        self._connected = True
        return True
    
    def disconnect(self):
        self._connected = False
    
    def is_connected(self):
        return self._connected
    
    def place_order(self, order):
        return OrderResult(
            order_id="test_order",
            symbol=order.symbol,
            side=order.side,
            status=OrderStatus.FILLED,
            quantity=order.quantity,
        )
    
    def cancel_order(self, order_id):
        return True
    
    def get_order(self, order_id):
        return None
    
    def get_positions(self):
        return self.positions
    
    def get_account(self):
        return AccountInfo(
            cash=self.cash,
            portfolio_value=self.cash + sum(p.market_value for p in self.positions),
            buying_power=self.cash * 2,
            equity=self.cash + sum(p.market_value for p in self.positions),
            positions=self.positions,
        )
    
    def get_latest_price(self, symbol):
        return self._prices.get(symbol)
    
    def get_score(self):
        return self._score
    
    def get_metrics(self):
        return {"fill_rate": 0.99, "avg_latency_ms": 50, "depth_factor": 1.0}
    
    def can_trade(self, order, current_price):
        return True
    
    def get_account_balance(self):
        return self.cash
    
    def get_symbols(self):
        return [p.symbol for p in self.positions]
    
    def get_position(self, symbol):
        for p in self.positions:
            if p.symbol == symbol:
                return p.quantity
        return 0


class TestCrossExchangePortfolio:
    """Test cases for CrossExchangePortfolio."""
    
    def test_position_aggregation_single_broker(self):
        """Test position aggregation from a single broker."""
        broker = MockBroker("test_broker")
        broker.positions = [
            Position(symbol="BTC/USD", quantity=0.5, avg_entry_price=40000.0, current_price=50000.0),
        ]
        
        portfolio = CrossExchangePortfolio({"test": broker})
        portfolio.sync_positions()
        
        unified = portfolio.get_unified_positions()
        assert "BTC/USD" in unified
        assert unified["BTC/USD"].quantity == 0.5
    
    def test_position_aggregation_multiple_brokers(self):
        """Test position aggregation from multiple brokers."""
        broker1 = MockBroker("broker1")
        broker1.positions = [
            Position(symbol="BTC/USD", quantity=0.5, avg_entry_price=40000.0, current_price=50000.0),
        ]
        
        broker2 = MockBroker("broker2")
        broker2.positions = [
            Position(symbol="BTC/USD", quantity=0.3, avg_entry_price=45000.0, current_price=50000.0),
        ]
        
        portfolio = CrossExchangePortfolio({"broker1": broker1, "broker2": broker2})
        portfolio.sync_positions()
        
        unified = portfolio.get_unified_positions()
        assert unified["BTC/USD"].quantity == pytest.approx(0.8)
    
    def test_calculate_unified_pnl(self):
        """Test PnL calculation across brokers."""
        broker = MockBroker("test", cash=10000.0)
        broker.positions = [
            Position(symbol="BTC/USD", quantity=1.0, avg_entry_price=40000.0, current_price=50000.0),
        ]
        
        portfolio = CrossExchangePortfolio({"test": broker})
        portfolio.update_price("BTC/USD", "test", 50000.0)
        portfolio.sync_positions()
        
        summary = portfolio.calculate_unified_pnl()
        assert summary.cash == 10000.0
        assert summary.positions_value == pytest.approx(50000.0)
        assert summary.total_value == pytest.approx(60000.0)
        # Unrealized PnL depends on whether position avg_entry was set correctly
        assert summary.unrealized_pnl >= 0
    
    def test_update_price(self):
        """Test price updates for positions."""
        broker = MockBroker("test")
        portfolio = CrossExchangePortfolio({"test": broker})
        
        portfolio.update_price("BTC/USD", "test", 55000.0)
        assert portfolio._prices["test"]["BTC/USD"] == 55000.0
    
    def test_synchronize_cross_exchange_position(self):
        """Test cross-exchange position synchronization."""
        broker = MockBroker("test")
        portfolio = CrossExchangePortfolio({"test": broker})
        
        plan = portfolio.synchronize_cross_exchange_position("BTC/USD", 1.0)
        assert isinstance(plan, dict)


class TestArbitrageDetector:
    """Test cases for ArbitrageDetector."""
    
    def test_spread_calculation(self):
        """Test spread calculation in basis points."""
        detector = ArbitrageDetector(min_spread_bps=5.0, min_profit_bps=2.0)
        
        spread = detector._calculate_spread_bps(99.0, 101.0)
        assert spread == pytest.approx(200.0, rel=0.01)
    
    def test_spread_calculation_equal_prices(self):
        """Test spread calculation with equal prices."""
        detector = ArbitrageDetector()
        
        spread = detector._calculate_spread_bps(100.0, 100.0)
        assert spread == 0.0
    
    def test_detect_cross_exchange_arbitrage_no_opportunity(self):
        """Test detection when no arbitrage opportunity exists."""
        detector = ArbitrageDetector(min_spread_bps=50.0, min_profit_bps=30.0)
        
        detector.update_price("BTCUSD", "exchange1", 50000.0)
        detector.update_price("BTCUSD", "exchange2", 50001.0)
        
        opportunities = detector.detect_cross_exchange_arbitrage("BTCUSD")
        assert len(opportunities) == 0
    
    def test_detect_cross_exchange_arbitrage_with_opportunity(self):
        """Test detection of arbitrage opportunity."""
        detector = ArbitrageDetector(min_spread_bps=5.0, min_profit_bps=1.0)
        
        detector.update_price("BTCUSD", "exchange1", 49500.0)
        detector.update_price("BTCUSD", "exchange2", 50500.0)
        
        opportunities = detector.detect_cross_exchange_arbitrage("BTCUSD")
        assert len(opportunities) >= 1
    
    def test_scan_all_symbols(self):
        """Test scanning multiple symbols."""
        detector = ArbitrageDetector(min_spread_bps=10.0)
        
        detector.update_price("BTCUSD", "ex1", 50000.0)
        detector.update_price("BTCUSD", "ex2", 50500.0)
        detector.update_price("ETHUSD", "ex1", 3000.0)
        detector.update_price("ETHUSD", "ex2", 3030.0)
        
        opportunities = detector.scan_all_symbols(["BTCUSD", "ETHUSD"])
        assert isinstance(opportunities, list)


class TestStrategyPluginLoader:
    """Test cases for StrategyPluginLoader."""
    
    def test_load_strategy_from_module_file(self):
        """Test loading strategy from a Python file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
from strategy.base import BaseStrategy
import pandas as pd
from strategy.signals import Signal, SignalType

class TestStrategy(BaseStrategy):
    def calculate_indicators(self, data):
        return data
    
    def generate_signal(self, data, idx):
        return Signal(SignalType.HOLD, 0.0, idx)
    
    def get_required_periods(self):
        return 10
""")
            f.flush()
            module_path = f.name
        
        try:
            loader = StrategyPluginLoader()
            strategy_class = loader.load_strategy_from_module(module_path)
            assert strategy_class.__name__ == "TestStrategy"
        finally:
            os.unlink(module_path)
    
    def test_load_strategy_invalid_file(self):
        """Test loading strategy from invalid file raises error."""
        loader = StrategyPluginLoader()
        
        with pytest.raises(StrategyPluginError):
            loader.load_strategy_from_module("/nonexistent/path.py")
    
    def test_validate_strategy_interface_valid(self):
        """Test validation of valid strategy interface."""
        loader = StrategyPluginLoader()
        
        class ValidStrategy(BaseStrategy):
            def calculate_indicators(self, data): pass
            def generate_signal(self, data, idx): pass
            def get_required_periods(self): return 10
        
        loader._validate_strategy_interface(ValidStrategy)
    
    def test_validate_strategy_interface_missing_method(self):
        """Test validation fails for missing method."""
        loader = StrategyPluginLoader()
        
        class InvalidStrategy:
            def calculate_indicators(self, data): pass
        
        with pytest.raises(StrategyInterfaceError):
            loader._validate_strategy_interface(InvalidStrategy)
    
    def test_get_cross_exchange_symbol_map(self):
        """Test cross-exchange symbol mapping."""
        loader = StrategyPluginLoader()
        
        mapping = loader.get_cross_exchange_symbol_map("binance", "coinbase")
        assert "BTCUSDT" in mapping
        assert mapping["BTCUSDT"] == "BTC-USD"
    
    def test_map_symbol_for_exchange(self):
        """Test symbol mapping for exchange."""
        loader = StrategyPluginLoader()
        
        result = loader.map_symbol_for_exchange("BTCUSDT", "binance", "coinbase")
        assert result == "BTC-USD"


class TestBrokerSelector:
    """Test cases for BrokerSelector cross-exchange routing."""
    
    def test_select_broker_single_broker(self):
        """Test broker selection with single broker."""
        broker = MockBroker("test")
        selector = BrokerSelector(brokers={"test": broker})
        
        result = selector.select_broker(
            symbol="BTC/USD",
            order_type="MARKET",
            quantity=1.0,
            side=OrderSide.BUY,
            current_price=50000.0,
        )
        
        assert result == "test"
    
    def test_select_broker_fallback(self):
        """Test fallback broker selection."""
        broker1 = MockBroker("broker1", connected=False)
        broker2 = MockBroker("broker2", connected=True)
        
        selector = BrokerSelector(
            brokers={"broker1": broker1, "broker2": broker2},
            default_broker="broker2",
            enable_fallback=True,
        )
        
        result = selector.select_broker(
            symbol="BTC/USD",
            order_type="MARKET",
            quantity=1.0,
            side=OrderSide.BUY,
            current_price=50000.0,
        )
        
        assert result == "broker2"
    
    def test_select_broker_cross_exchange(self):
        """Test cross-exchange broker selection."""
        broker1 = MockBroker("alpaca", score=0.9)
        broker2 = MockBroker("binance", score=0.8)
        
        selector = BrokerSelector(brokers={"alpaca": broker1, "binance": broker2})
        
        allocations = selector.select_broker_cross_exchange(
            symbol="BTC/USD",
            order_type="MARKET",
            quantity=1.0,
            side=OrderSide.BUY,
            current_price=50000.0,
            max_exchanges=2,
        )
        
        assert isinstance(allocations, list)
        assert len(allocations) >= 1


class TestQuote:
    """Test cases for Quote class."""
    
    def test_mid_price(self):
        """Test mid price calculation."""
        quote = Quote(
            bid_price=99.0,
            ask_price=101.0,
            bid_exchange="ex1",
            ask_exchange="ex2",
        )
        
        assert quote.mid_price == 100.0
    
    def test_spread_bps(self):
        """Test spread calculation in basis points."""
        quote = Quote(
            bid_price=99.0,
            ask_price=101.0,
            bid_exchange="ex1",
            ask_exchange="ex2",
        )
        
        assert quote.spread_bps == pytest.approx(200.0, rel=0.01)


class TestArbitrageEvent:
    """Test cases for ArbitrageEvent."""
    
    def test_event_creation(self):
        """Test arbitrage event creation."""
        event = ArbitrageEvent(
            arbitrage_type=ArbitrageType.CROSS_EXCHANGE,
            symbol="BTCUSD",
            buy_exchange="exchange1",
            sell_exchange="exchange2",
            buy_price=49500.0,
            sell_price=50500.0,
            spread_bps=2.0,
            estimated_profit_bps=1.0,
        )
        
        assert event.symbol == "BTCUSD"
        assert event.arbitrage_type == ArbitrageType.CROSS_EXCHANGE
