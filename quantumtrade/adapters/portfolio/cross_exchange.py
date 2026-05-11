"""
Cross-exchange portfolio aggregation and P&L tracking.

Aggregates positions across multiple brokers/exchanges into a unified view.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Any, Tuple
from enum import Enum

if TYPE_CHECKING:
    from quantumtrade.adapters.brokers.base import BaseBroker


class PositionType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass
class Position:
    symbol: str
    quantity: float
    average_entry_price: float
    current_price: float
    position_type: PositionType = PositionType.FLAT
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        return self.quantity * self.average_entry_price
    
    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis
    
    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / abs(self.cost_basis)) * 100


@dataclass
class PortfolioSummary:
    total_value: float
    cash: float
    positions_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_value": self.total_value,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_pnl": self.total_pnl,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Quote:
    bid_price: float
    ask_price: float
    bid_exchange: str
    ask_exchange: str
    
    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2
    
    @property
    def spread_bps(self) -> float:
        if self.mid_price == 0:
            return 0.0
        return ((self.ask_price - self.bid_price) / self.mid_price) * 10000


class CrossExchangePortfolio:
    def __init__(self, brokers: Dict[str, "BaseBroker"]):
        self.brokers = brokers
        self._positions: Dict[str, Dict[str, Position]] = {}
        self._prices: Dict[str, Dict[str, float]] = {}
        self._cash: float = 0.0
        self._realized_pnl: float = 0.0
        self._last_sync: Optional[datetime] = None
    
    def sync_positions(self) -> None:
        for broker_name, broker in self.brokers.items():
            if not broker.is_connected():
                continue
            
            try:
                account_balance = broker.get_account_balance()
                self._cash += account_balance
                
                symbols = broker.get_symbols() if hasattr(broker, 'get_symbols') else []
                for symbol in symbols:
                    position_qty = broker.get_position(symbol)
                    if position_qty != 0:
                        current_price = self._get_price(symbol, broker_name)
                        avg_entry = self._get_average_entry(symbol, broker_name)
                        
                        position_type = PositionType.LONG if position_qty > 0 else PositionType.SHORT
                        
                        if symbol not in self._positions:
                            self._positions[symbol] = {}
                        
                        self._positions[symbol][broker_name] = Position(
                            symbol=symbol,
                            quantity=position_qty,
                            average_entry_price=avg_entry,
                            current_price=current_price,
                            position_type=position_type,
                        )
            except Exception:
                continue
        
        self._last_sync = datetime.now()
    
    def _get_price(self, symbol: str, broker_name: str) -> float:
        if broker_name in self._prices and symbol in self._prices[broker_name]:
            return self._prices[broker_name][symbol]
        return 0.0
    
    def _get_average_entry(self, symbol: str, broker_name: str) -> float:
        if broker_name in self._positions and symbol in self._positions[broker_name]:
            return self._positions[broker_name][symbol].average_entry_price
        return 0.0
    
    def update_price(self, symbol: str, broker_name: str, price: float) -> None:
        if broker_name not in self._prices:
            self._prices[broker_name] = {}
        self._prices[broker_name][symbol] = price
        
        if symbol in self._positions and broker_name in self._positions[symbol]:
            self._positions[symbol][broker_name].current_price = price
    
    def get_unified_positions(self) -> Dict[str, Position]:
        unified: Dict[str, Position] = {}
        
        for symbol, broker_positions in self._positions.items():
            total_qty = sum(p.quantity for p in broker_positions.values())
            weighted_entry = sum(
                p.quantity * p.average_entry_price for p in broker_positions.values()
            )
            avg_entry = weighted_entry / total_qty if total_qty != 0 else 0.0
            
            latest_price = self._prices.get(list(broker_positions.keys())[0], {}).get(symbol, 0.0)
            for broker_positions_dict in self._prices.values():
                if symbol in broker_positions_dict:
                    latest_price = broker_positions_dict[symbol]
                    break
            
            unified[symbol] = Position(
                symbol=symbol,
                quantity=total_qty,
                average_entry_price=avg_entry,
                current_price=latest_price,
                position_type=PositionType.LONG if total_qty > 0 else PositionType.SHORT,
            )
        
        return unified
    
    def calculate_unified_pnl(self) -> PortfolioSummary:
        positions_value = 0.0
        unrealized_pnl = 0.0
        
        for symbol, position in self.get_unified_positions().items():
            positions_value += position.market_value
            unrealized_pnl += position.unrealized_pnl
        
        total_value = self._cash + positions_value
        
        return PortfolioSummary(
            total_value=total_value,
            cash=self._cash,
            positions_value=positions_value,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=self._realized_pnl + unrealized_pnl,
        )
    
    def get_best_bid_offer(self, symbol: str) -> Optional[Quote]:
        best_bid = (-1, 0.0, "")
        best_ask = (-1, float('inf'), "")
        
        for broker_name, prices in self._prices.items():
            if symbol in prices:
                price = prices[symbol]
                if price > best_bid[1]:
                    best_bid = (price, price, broker_name)
                if price < best_ask[1]:
                    best_ask = (price, price, broker_name)
        
        if best_bid[1] <= 0 or best_ask[1] == float('inf'):
            return None
        
        spread = best_ask[1] - best_bid[1]
        if best_ask[1] > 0:
            spread = (spread / best_ask[1]) * 10000
        
        return Quote(
            bid_price=best_bid[0],
            ask_price=best_ask[0],
            bid_exchange=best_bid[2],
            ask_exchange=best_ask[2],
        )
    
    def synchronize_cross_exchange_position(self, symbol: str, target_quantity: float) -> Dict[str, float]:
        unified = self.get_unified_positions()
        current_qty = unified.get(symbol, Position(symbol=symbol, quantity=0, average_entry_price=0, current_price=0)).quantity
        delta = target_quantity - current_qty
        
        if delta == 0:
            return {}
        
        plan: Dict[str, float] = {}
        side = "SELL" if delta < 0 else "BUY"
        qty_to_trade = abs(delta)
        
        broker_allocations = self._score_brokers_for_execution(symbol)
        
        for broker_name, score in broker_allocations:
            if qty_to_trade <= 0:
                break
            if score < 0.5:
                continue
            
            allocation = min(qty_to_trade, qty_to_trade)
            plan[broker_name] = allocation * (1 if side == "BUY" else -1)
            qty_to_trade -= allocation
        
        return plan
    
    def _score_brokers_for_execution(self, symbol: str) -> List[Tuple[str, float]]:
        scores: List[Tuple[str, float]] = []
        
        for name, broker in self.brokers.items():
            if not broker.is_connected():
                continue
            
            score = 0.0
            metrics = broker.get_metrics()
            
            score += metrics.get("fill_rate", 0.99) * 0.3
            score += (1 - min(metrics.get("avg_latency_ms", 100) / 500, 1)) * 0.3
            score += metrics.get("depth_factor", 1.0) * 0.4
            
            scores.append((name, score))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def record_fill(self, symbol: str, quantity: float, price: float, is_buy: bool) -> None:
        self._realized_pnl += quantity * price * (1 if is_buy else -1)