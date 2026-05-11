"""
Multi-Exchange Trading Demo

Demonstrates:
- Initializing multiple brokers (Alpaca, Binance)
- Creating a CrossExchangePortfolio
- Detecting arbitrage opportunities
- Routing orders across exchanges
- Using the plugin loader for custom strategies
"""

import os
import logging
from datetime import datetime

from brokers.base import OrderSide, OrderType, OrderStatus
from brokers.alpaca_broker import AlpacaBroker
from brokers.binance_broker import BinanceBroker
from quantumtrade.adapters.portfolio.cross_exchange import CrossExchangePortfolio
from quantumtrade.adapters.arbitrage.detector import ArbitrageDetector
from quantumtrade.adapters.execution.broker_selector import BrokerSelector
from quantumtrade.adapters.strategy.plugin_loader import StrategyPluginLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_alpaca_broker():
    broker = AlpacaBroker(
        api_key=os.getenv("ALPACA_API_KEY", "demo_key"),
        api_secret=os.getenv("ALPACA_API_SECRET", "demo_secret"),
        paper=True,
    )
    broker.connect()
    return broker


def create_binance_broker():
    broker = BinanceBroker(
        api_key=os.getenv("BINANCE_API_KEY", "demo_key"),
        api_secret=os.getenv("BINANCE_API_SECRET", "demo_secret"),
        paper=True,
    )
    broker.connect()
    return broker


def demo_cross_exchange_portfolio(brokers):
    logger.info("=== Cross-Exchange Portfolio Demo ===")
    
    portfolio = CrossExchangePortfolio(brokers)
    
    for name, broker in brokers.items():
        if broker.is_connected():
            try:
                account = broker.get_account()
                logger.info(f"{name} account - Cash: ${account.cash:,.2f}, Portfolio: ${account.portfolio_value:,.2f}")
                
                for pos in account.positions:
                    portfolio.update_price(pos.symbol, name, pos.current_price)
                    logger.info(f"  {pos.symbol}: {pos.quantity} @ ${pos.current_price:,.2f}")
            except Exception as e:
                logger.error(f"Error syncing {name}: {e}")
    
    unified = portfolio.get_unified_positions()
    logger.info(f"Unified positions: {len(unified)} symbols")
    
    summary = portfolio.calculate_unified_pnl()
    logger.info(f"Total portfolio value: ${summary.total_value:,.2f}")
    logger.info(f"Unrealized PnL: ${summary.unrealized_pnl:,.2f}")
    
    return portfolio


def demo_arbitrage_detector(brokers):
    logger.info("=== Arbitrage Detector Demo ===")
    
    detector = ArbitrageDetector(min_spread_bps=5.0, min_profit_bps=2.0)
    
    symbols = ["BTCUSDT", "ETHUSDT"]
    prices = {}
    
    for symbol in symbols:
        prices[symbol] = {}
        for name, broker in brokers.items():
            if broker.is_connected():
                try:
                    price = broker.get_latest_price(symbol)
                    if price:
                        prices[symbol][name] = price
                        detector.update_price(symbol, name, price)
                        logger.info(f"{symbol} on {name}: ${price:,.2f}")
                except Exception as e:
                    logger.warning(f"Could not get price for {symbol} on {name}: {e}")
    
    opportunities = []
    for symbol in symbols:
        if len(detector._prices) >= 2:
            events = detector.detect_cross_exchange_arbitrage(symbol)
            opportunities.extend(events)
    
    if opportunities:
        logger.info(f"Found {len(opportunities)} arbitrage opportunities:")
        for event in opportunities:
            logger.info(
                f"  {event.symbol}: Buy {event.buy_exchange} @ ${event.buy_price:,.2f}, "
                f"Sell {event.sell_exchange} @ ${event.sell_price:,.2f}, "
                f"Profit: {event.estimated_profit_bps:.1f} bps"
            )
    else:
        logger.info("No arbitrage opportunities found (need price discrepancies)")
    
    return opportunities


def demo_broker_routing(brokers):
    logger.info("=== Broker Selector Demo ===")
    
    selector = BrokerSelector(
        brokers=brokers,
        default_broker="alpaca",
        enable_fallback=True,
    )
    
    allocations = selector.select_broker_cross_exchange(
        symbol="BTC/USDT",
        order_type="MARKET",
        quantity=0.1,
        side=OrderSide.BUY,
        current_price=50000.0,
        max_exchanges=2,
    )
    
    logger.info("Order routing plan:")
    for broker_name, quantity in allocations:
        logger.info(f"  {broker_name}: {quantity} units")
    
    return allocations


def demo_plugin_loader():
    logger.info("=== Strategy Plugin Loader Demo ===")
    
    loader = StrategyPluginLoader(strategies_dir="strategy/plugins")
    
    try:
        plugins = loader.load_plugins_from_directory()
        logger.info(f"Loaded {len(plugins)} strategy plugins:")
        for name, cls in plugins.items():
            logger.info(f"  {name}: {cls.__module__}")
    except Exception as e:
        logger.warning(f"Could not load plugins: {e}")
    
    symbol_map = loader.get_cross_exchange_symbol_map("binance", "coinbase")
    logger.info("Sample cross-exchange symbol mapping:")
    for k, v in list(symbol_map.items())[:3]:
        logger.info(f"  {k} -> {v}")
    
    return loader


def main():
    logger.info("Starting Multi-Exchange Trading Demo")
    logger.info("=" * 50)
    
    brokers = {}
    
    alpaca = create_alpaca_broker()
    if alpaca.is_connected():
        brokers["alpaca"] = alpaca
    
    binance = create_binance_broker()
    if binance.is_connected():
        brokers["binance"] = binance
    
    if not brokers:
        logger.warning("No brokers connected. Using mock data for demo.")
        brokers = _create_mock_brokers()
    
    portfolio = demo_cross_exchange_portfolio(brokers)
    opportunities = demo_arbitrage_detector(brokers)
    routing = demo_broker_routing(brokers)
    loader = demo_plugin_loader()
    
    logger.info("=" * 50)
    logger.info("Demo complete!")
    
    return {
        "portfolio": portfolio,
        "opportunities": opportunities,
        "routing": routing,
        "loader": loader,
    }


def _create_mock_brokers():
    class MockBroker:
        def __init__(self, name):
            self.name = name
            self._connected = True
        
        def is_connected(self):
            return self._connected
        
        def connect(self):
            self._connected = True
            return True
        
        def disconnect(self):
            self._connected = False
        
        def get_account(self):
            from brokers.base import AccountInfo, Position
            return AccountInfo(
                cash=10000.0,
                portfolio_value=15000.0,
                buying_power=20000.0,
                equity=25000.0,
                positions=[
                    Position(symbol="BTC/USDT", quantity=0.5, avg_entry_price=40000.0, current_price=50000.0),
                ],
            )
        
        def get_latest_price(self, symbol):
            prices = {"BTCUSDT": 50000.0, "ETHUSDT": 3000.0}
            return prices.get(symbol, 100.0)
    
    return {"alpaca": MockBroker("alpaca"), "binance": MockBroker("binance")}


if __name__ == "__main__":
    main()
