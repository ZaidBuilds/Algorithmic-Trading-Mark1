"""
Arbitrage detector for cross-exchange and triangular opportunities.

Monitors price discrepancies between exchanges and detects arbitrage opportunities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging

from quantumtrade.events import MessageBus, BaseEvent, EventType


class ArbitrageType(str, Enum):
    CROSS_EXCHANGE = "cross_exchange"
    TRIANGULAR = "triangular"


@dataclass
class ArbitrageEvent(BaseEvent):
    """Event emitted when an arbitrage opportunity is detected."""
    arbitrage_type: ArbitrageType
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_bps: float
    estimated_profit_bps: float
    max_tradeable_size: Optional[float] = None
    
    def __init__(
        self,
        arbitrage_type: ArbitrageType,
        symbol: str,
        buy_exchange: str,
        sell_exchange: str,
        buy_price: float,
        sell_price: float,
        spread_bps: float,
        estimated_profit_bps: float,
        max_tradeable_size: Optional[float] = None,
        timestamp: datetime = None,
    ):
        super().__init__(
            event_type="arbitrage",
            timestamp=timestamp or datetime.now(),
            data={
                "arbitrage_type": arbitrage_type.value,
                "symbol": symbol,
                "buy_exchange": buy_exchange,
                "sell_exchange": sell_exchange,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "spread_bps": spread_bps,
                "estimated_profit_bps": estimated_profit_bps,
                "max_tradeable_size": max_tradeable_size,
            },
        )
        self.arbitrage_type = arbitrage_type
        self.symbol = symbol
        self.buy_exchange = buy_exchange
        self.sell_exchange = sell_exchange
        self.buy_price = buy_price
        self.sell_price = sell_price
        self.spread_bps = spread_bps
        self.estimated_profit_bps = estimated_profit_bps
        self.max_tradeable_size = max_tradeable_size


@dataclass
class TriangularOpportunity:
    base_currency: str
    intermediate_currency: str
    quote_currency: str
    exchange: str
    path: List[str]
    profit_bps: float


class ArbitrageDetector:
    def __init__(
        self,
        min_spread_bps: float = 5.0,
        min_profit_bps: float = 2.0,
        message_bus: Optional[MessageBus] = None,
    ):
        self.min_spread_bps = min_spread_bps
        self.min_profit_bps = min_profit_bps
        self.message_bus = message_bus or MessageBus()
        self._prices: Dict[str, Dict[str, float]] = {}
        self._logger = logging.getLogger(__name__)
    
    def update_price(self, symbol: str, exchange: str, price: float) -> None:
        if exchange not in self._prices:
            self._prices[exchange] = {}
        self._prices[exchange][symbol] = price
    
    def detect_cross_exchange_arbitrage(self, symbol: str) -> List[ArbitrageEvent]:
        if len(self._prices) < 2:
            return []
        
        opportunities: List[ArbitrageEvent] = []
        
        exchange_prices: List[Tuple[str, float]] = []
        for exchange, prices in self._prices.items():
            if symbol in prices:
                exchange_prices.append((exchange, prices[symbol]))
        
        if len(exchange_prices) < 2:
            return []
        
        for i, (buy_ex, buy_price) in enumerate(exchange_prices):
            for sell_ex, sell_price in exchange_prices[i + 1:]:
                if buy_price >= sell_price:
                    continue
                
                spread_bps = self._calculate_spread_bps(buy_price, sell_price)
                if spread_bps < self.min_spread_bps:
                    continue
                
                profit_bps = spread_bps - self._estimate_transaction_costs_bps(symbol, buy_ex, sell_ex)
                
                if profit_bps >= self.min_profit_bps:
                    event = ArbitrageEvent(
                        arbitrage_type=ArbitrageType.CROSS_EXCHANGE,
                        symbol=symbol,
                        buy_exchange=buy_ex,
                        sell_exchange=sell_ex,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        spread_bps=spread_bps,
                        estimated_profit_bps=profit_bps,
                    )
                    opportunities.append(event)
                    self.message_bus.publish(event)
                
                if sell_price > buy_price:
                    spread_bps = self._calculate_spread_bps(sell_price, buy_price)
                    if spread_bps >= self.min_spread_bps:
                        profit_bps = spread_bps - self._estimate_transaction_costs_bps(symbol, sell_ex, buy_ex)
                        if profit_bps >= self.min_profit_bps:
                            event = ArbitrageEvent(
                                arbitrage_type=ArbitrageType.CROSS_EXCHANGE,
                                symbol=symbol,
                                buy_exchange=sell_ex,
                                sell_exchange=buy_ex,
                                buy_price=sell_price,
                                sell_price=buy_price,
                                spread_bps=spread_bps,
                                estimated_profit_bps=profit_bps,
                            )
                            opportunities.append(event)
                            self.message_bus.publish(event)
        
        return opportunities
    
    def _calculate_spread_bps(self, buy_price: float, sell_price: float) -> float:
        if buy_price <= 0 or sell_price <= 0:
            return 0.0
        mid = (buy_price + sell_price) / 2
        return ((sell_price - buy_price) / mid) * 10000
    
    def _estimate_transaction_costs_bps(self, symbol: str, buy_ex: str, sell_ex: str) -> float:
        base_cost = 5.0
        if "binance" in buy_ex.lower() or "binance" in sell_ex.lower():
            base_cost = 2.0
        if "coinbase" in buy_ex.lower() or "coinbase" in sell_ex.lower():
            base_cost = 8.0
        return base_cost
    
    def detect_triangular_arbitrage(
        self,
        base: str,
        intermediate: str,
        quote: str,
        exchange: str,
    ) -> Optional[TriangularOpportunity]:
        if exchange not in self._prices:
            return None
        
        prices = self._prices[exchange]
        pair1 = f"{base}/{intermediate}"
        pair2 = f"{intermediate}/{quote}"
        pair3 = f"{base}/{quote}"
        
        if pair1 not in prices or pair2 not in prices or pair3 not in prices:
            return None
        
        p1 = prices[pair1]
        p2 = prices[pair2]
        p3 = prices[pair3]
        
        direct_rate = p3
        implied_rate = p1 * p2
        
        if direct_rate > 0:
            arbitrage_bps = ((implied_rate - direct_rate) / direct_rate) * 10000
            if arbitrage_bps > self.min_profit_bps:
                return TriangularOpportunity(
                    base_currency=base,
                    intermediate_currency=intermediate,
                    quote_currency=quote,
                    exchange=exchange,
                    path=[pair1, pair2],
                    profit_bps=arbitrage_bps,
                )
        
        return None
    
    def scan_all_symbols(self, symbols: List[str]) -> List[ArbitrageEvent]:
        all_opportunities: List[ArbitrageEvent] = []
        for symbol in symbols:
            opportunities = self.detect_cross_exchange_arbitrage(symbol)
            all_opportunities.extend(opportunities)
        return all_opportunities