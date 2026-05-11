"""
Broker Selector — intelligent broker routing.

Selects the optimal broker for an order based on:
- Trading fees (maker/taker)
- API latency (historical)
- Fill rate (historical)
- Order book depth (liquidity)
- Current connection status

Can split orders across multiple brokers (consensus routing).
"""

from typing import TYPE_CHECKING, Dict, List, Optional, Any, Tuple
from datetime import datetime

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    OrderSide,
)
from quantumtrade.adapters.brokers.base import BaseBroker

if TYPE_CHECKING:
    from quantumtrade.adapters.brokers.base import BaseBroker


class BrokerSelector:
    """
    Selects best broker(s) for an order.
    
    Scoring weights can be tuned based on strategy priorities.
    """
    
    def __init__(
        self,
        brokers: Dict[str, "BaseBroker"],
        default_broker: Optional[str] = None,
        enable_fallback: bool = True,
        enable_consensus: bool = False,
        consensus_threshold: float = 0.8,
    ):
        """
        Initialize broker selector.
        
        Args:
            brokers: Dict mapping broker name to BaseBroker instance
            default_broker: Name of fallback broker
            enable_fallback: Try secondary broker if primary rejects
            enable_consensus: Split order across multiple brokers
            consensus_threshold: Min broker score ratio to participate in consensus
        """
        self.brokers = brokers
        self.default_broker = default_broker or (list(brokers.keys())[0] if brokers else None)
        self.enable_fallback = enable_fallback
        self.enable_consensus = enable_consensus
        self.consensus_threshold = consensus_threshold
    
    def select_broker(
        self,
        symbol: str,
        order_type: str,
        quantity: float,
        side: OrderSide,
        current_price: float,
        strategy: Optional[str] = None,
        algorithm: Optional[str] = None,
    ) -> str:
        """
        Choose best broker.
        
        Returns:
            Broker name (string)
        """
        candidates = self._score_brokers(symbol, order_type, quantity, side, current_price)
        
        if not candidates:
            # No suitable broker, return default
            return self.default_broker or "unknown"
        
        # Select top broker
        best_broker_name, score = candidates[0]
        return best_broker_name
    
    def split_across_brokers(
        self,
        order: BrokerOrder,
        current_price: float,
        min_slice: float = 100,
    ) -> Dict[str, float]:
        """
        Split order across multiple brokers (consensus routing).
        
        Returns:
            Dict mapping broker name -> quantity to route
        """
        total_qty = order.quantity
        candidates = self._score_brokers(
            order.symbol, order.order_type.value, total_qty, order.side, current_price
        )
        
        if not candidates:
            return {self.default_broker: total_qty} if self.default_broker else {}
        
        # Normalize scores
        total_score = sum(score for _, score in candidates)
        allocations: Dict[str, float] = {}
        allocated = 0.0
        
        for broker_name, score in candidates:
            if score / max(total_score, 1e-9) >= self.consensus_threshold:
                share = score / total_score
                qty = total_qty * share
                if qty >= min_slice:
                    allocations[broker_name] = qty
                    allocated += qty
        
        # Adjust rounding errors
        if allocated < total_qty and allocations:
            # Give remainder to highest-score broker
            best = list(allocations.keys())[0]
            allocations[best] += total_qty - allocated
        
        return allocations if allocations else {candidates[0][0]: total_qty}
    
    def _score_brokers(
        self,
        symbol: str,
        order_type: str,
        quantity: float,
        side: OrderSide,
        current_price: float,
    ) -> List[Tuple[str, float]]:
        """Score and rank brokers."""
        scores = []
        
        for name, broker in self.brokers.items():
            if not broker.is_connected():
                continue
            
            order_mock = BrokerOrder(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
            )
            if not broker.can_trade(order_mock, current_price):
                continue
            
            score = broker.get_score()
            scores.append((name, score))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def update_broker_metrics(
        self,
        broker_name: str,
        fill_success: bool,
        latency_ms: Optional[float] = None,
        fees: Optional[float] = None,
    ):
        """
        Update broker historical metrics for future routing decisions.
        
        Args:
            broker_name: Which broker to update
            fill_success: Whether the fill succeeded
            latency_ms: Observed latency
            fees: Actual fees paid
        """
        if broker_name not in self.brokers:
            return
        
        broker = self.brokers[broker_name]
        
        # Update fill rate with exponential moving average
        alpha = 0.1
        if fill_success:
            broker._fill_rate = (1 - alpha) * broker._fill_rate + alpha * 1.0
        else:
            broker._fill_rate = (1 - alpha) * broker._fill_rate + alpha * 0.0
        
        # Update latency if provided
        if latency_ms is not None:
            beta = 0.1
            broker.latency_ms = (1 - beta) * broker.latency_ms + beta * latency_ms
    
    def get_broker(self, name: str) -> Optional["BaseBroker"]:
        """Get broker instance by name."""
        return self.brokers.get(name)
    
    def list_brokers(self) -> List[str]:
        """List available broker names."""
        return list(self.brokers.keys())
    
    def select_broker_cross_exchange(
        self,
        symbol: str,
        order_type: str,
        quantity: float,
        side: OrderSide,
        current_price: float,
        max_exchanges: int = 3,
        max_slice: float = 1000,
    ) -> List[Tuple[str, float]]:
        """
        Select multiple brokers for cross-exchange routing.
        
        Returns:
            List of (broker_name, quantity) tuples sorted by score
        """
        candidates = self._score_brokers(symbol, order_type, quantity, side, current_price)
        
        if not candidates:
            return [(self.default_broker or "unknown", quantity)]
        
        total_score = sum(score for _, score in candidates[:max_exchanges])
        if total_score == 0:
            total_score = 1
        
        allocations: List[Tuple[str, float]] = []
        allocated = 0.0
        
        for broker_name, score in candidates[:max_exchanges]:
            if allocated >= quantity:
                break
            
            remaining = quantity - allocated
            share = score / total_score
            alloc_qty = min(remaining * share, max_slice)
            
            if alloc_qty > 0:
                allocations.append((broker_name, alloc_qty))
                allocated += alloc_qty
        
        if allocated < quantity and allocations:
            allocations[0] = (allocations[0][0], allocations[0][1] + (quantity - allocated))
        
        return allocations


class FallbackBrokerSelector(BrokerSelector):
    """
    Broker selector with explicit fallback chain.
    
    If primary broker fails, tries secondary, etc.
    """
    
    def __init__(
        self,
        brokers: Dict[str, "BaseBroker"],
        fallback_chain: List[str],
        **kwargs,
    ):
        super().__init__(brokers, **kwargs)
        self.fallback_chain = fallback_chain
    
    def select_broker_with_fallback(
        self,
        symbol: str,
        order_type: str,
        quantity: float,
        side: OrderSide,
        current_price: float,
    ) -> str:
        """Select broker, trying fallbacks if top choice unavailable."""
        candidates = self._score_brokers(symbol, order_type, quantity, side, current_price)
        
        for broker_name, _ in candidates:
            broker = self.brokers.get(broker_name)
            if broker and broker.is_connected():
                return broker_name
        
        # All unavailable, try fallback chain
        for fallback in self.fallback_chain:
            if fallback in self.brokers and self.brokers[fallback].is_connected():
                return fallback
        
        return self.default_broker or "unknown"
