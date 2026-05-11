"""
Execution domain models — orders, fills, execution reports, TCA reports.

These dataclasses represent the core abstractions for order execution,
fill simulation, and transaction cost analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class AlgorithmType(str, Enum):
    """Execution algorithm types."""
    MARKET = "market"
    TWAP = "twap"
    VWAP = "vwap"
    POV = "pov"
    IMPLEMENTATION_SHORTFALL = "implementation_shortfall"
    ICEBERG = "iceberg"


@dataclass
class BrokerOrder:
    """
    Represents an order to be executed by a broker.
    
    This is the canonical order object used throughout the execution layer.
    It extends the basic OrderEvent with additional metadata for routing and TCA.
    """
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    # Metadata
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    broker: Optional[str] = None  # Target broker
    strategy: Optional[str] = None  # Originating strategy
    
    # timestamps
    timestamp: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    # status tracking
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    average_fill_price: Optional[float] = None
    
    # algorithm routing
    algorithm: AlgorithmType = AlgorithmType.MARKET
    algo_params: Dict[str, Any] = field(default_factory=dict)
    
    # TCA fields
    arrival_price: Optional[float] = None  # Price at order arrival
    pre_trade_benchmark: Optional[float] = None  # Benchmark before execution
    post_trade_benchmark: Optional[float] = None  # Benchmark after execution
    
    def __post_init__(self):
        """Validate order parameters."""
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")
        if self.side not in (OrderSide.BUY, OrderSide.SELL):
            raise ValueError(f"Invalid order side: {self.side}")
    
    @property
    def is_buy(self) -> bool:
        return self.side == OrderSide.BUY
    
    @property
    def is_sell(self) -> bool:
        return self.side == OrderSide.SELL
    
    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity
    
    @property
    def is_filled(self) -> bool:
        return self.filled_quantity >= self.quantity
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "broker": self.broker,
            "strategy": self.strategy,
            "timestamp": self.timestamp.isoformat(),
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "average_fill_price": self.average_fill_price,
            "algorithm": self.algorithm.value,
            "algo_params": self.algo_params,
            "arrival_price": self.arrival_price,
            "pre_trade_benchmark": self.pre_trade_benchmark,
            "post_trade_benchmark": self.post_trade_benchmark,
        }


@dataclass
class Fill:
    """
    Represents a single fill (execution) of an order.
    
    Fills can be partial; multiple fills combine to satisfy the original order.
    """
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    
    # timestamps
    trade_timestamp: datetime
    received_timestamp: datetime
    
    # broker info
    broker: str
    broker_order_id: Optional[str] = None
    broker_fill_id: Optional[str] = None
    
    # fees
    commission: float = 0.0
    fees: float = 0.0  # Exchange/regulatory fees
    
    # TCA fields
    slippage_bps: Optional[float] = None  # Slippage from benchmark in basis points
    spread_cost_bps: Optional[float] = None  # Spread cost in bps
    impact_bps: Optional[float] = None  # Market impact in bps
    
    def __post_init__(self):
        """Validate fill data."""
        if self.quantity <= 0:
            raise ValueError("Fill quantity must be positive")
        if self.price <= 0:
            raise ValueError("Fill price must be positive")
    
    @property
    def notional_value(self) -> float:
        """Total value of the fill."""
        return self.quantity * self.price
    
    @property
    def total_cost(self) -> float:
        """Total explicit cost (commission + fees)."""
        return self.commission + self.fees
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "trade_timestamp": self.trade_timestamp.isoformat(),
            "received_timestamp": self.received_timestamp.isoformat(),
            "broker": self.broker,
            "broker_order_id": self.broker_order_id,
            "broker_fill_id": self.broker_fill_id,
            "commission": self.commission,
            "fees": self.fees,
            "slippage_bps": self.slippage_bps,
            "spread_cost_bps": self.spread_cost_bps,
            "impact_bps": self.impact_bps,
            "notional_value": self.notional_value,
            "total_cost": self.total_cost,
        }


@dataclass
class ExecutionReport:
    """
    Comprehensive report for a completed order execution.
    
    Aggregates all fills, calculates aggregated metrics, and includes TCA analysis.
    """
    order: BrokerOrder
    fills: List[Fill] = field(default_factory=list)
    
    # aggregated fields
    total_filled_quantity: float = field(init=False)
    weighted_avg_price: float = field(init=False)
    total_commission: float = field(init=False)
    total_fees: float = field(init=False)
    total_notional: float = field(init=False)
    
    # timing
    first_fill_timestamp: Optional[datetime] = field(init=False, default=None)
    last_fill_timestamp: Optional[datetime] = field(init=False, default=None)
    execution_duration_seconds: Optional[float] = field(init=False, default=None)
    
    # TCA aggregated
    total_slippage_bps: float = field(init=False, default=0.0)
    total_spread_cost_bps: float = field(init=False, default=0.0)
    total_impact_bps: float = field(init=False, default=0.0)
    
    def __post_init__(self):
        """Calculate aggregated metrics."""
        self._calculate_aggregates()
    
    def _calculate_aggregates(self):
        """Compute aggregated metrics from fills."""
        if not self.fills:
            self.total_filled_quantity = 0.0
            self.weighted_avg_price = 0.0
            self.total_commission = 0.0
            self.total_fees = 0.0
            self.total_notional = 0.0
            return
        
        self.total_filled_quantity = sum(f.quantity for f in self.fills)
        self.total_notional = sum(f.notional_value for f in self.fills)
        self.total_commission = sum(f.commission for f in self.fills)
        self.total_fees = sum(f.fees for f in self.fills)
        
        if self.total_filled_quantity > 0:
            self.weighted_avg_price = self.total_notional / self.total_filled_quantity
        
        # timestamps
        trade_timestamps = [f.trade_timestamp for f in self.fills]
        self.first_fill_timestamp = min(trade_timestamps)
        self.last_fill_timestamp = max(trade_timestamps)
        if self.first_fill_timestamp and self.last_fill_timestamp:
            delta = self.last_fill_timestamp - self.first_fill_timestamp
            self.execution_duration_seconds = delta.total_seconds()
        
        # weighted average of bps costs (by notional value)
        if self.total_notional > 0:
            self.total_slippage_bps = sum(
                f.slippage_bps * f.notional_value for f in self.fills if f.slippage_bps is not None
            ) / self.total_notional
            self.total_spread_cost_bps = sum(
                f.spread_cost_bps * f.notional_value for f in self.fills if f.spread_cost_bps is not None
            ) / self.total_notional
            self.total_impact_bps = sum(
                f.impact_bps * f.notional_value for f in self.fills if f.impact_bps is not None
            ) / self.total_notional
    
    @property
    def total_explicit_cost_bps(self) -> float:
        """Explicit costs (commission+fees) in bps of notional."""
        if self.total_notional == 0:
            return 0.0
        explicit_cost = self.total_commission + self.total_fees
        return (explicit_cost / self.total_notional) * 10000  # to bps
    
    @property
    def total_implicit_cost_bps(self) -> float:
        """Implicit costs (slippage + spread + impact) in bps."""
        return self.total_slippage_bps + self.total_spread_cost_bps + self.total_impact_bps
    
    @property
    def total_cost_bps(self) -> float:
        """All costs combined in bps."""
        return self.total_explicit_cost_bps + self.total_implicit_cost_bps
    
    @property
    def implementation_shortfall_bps(self) -> float:
        """
        Implementation shortfall = (avg_fill_price - arrival_price) / arrival_price * 10000
        Only meaningful for buy orders; for sell, invert sign.
        """
        if not self.order.arrival_price or self.order.arrival_price == 0:
            return 0.0
        price_diff = self.weighted_avg_price - self.order.arrival_price
        if self.order.is_sell:
            price_diff = -price_diff
        return (price_diff / self.order.arrival_price) * 10000
    
    @property
    def fill_rate_pct(self) -> float:
        """Percentage of order filled."""
        if self.order.quantity == 0:
            return 0.0
        return (self.total_filled_quantity / self.order.quantity) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "order": self.order.to_dict(),
            "fills": [f.to_dict() for f in self.fills],
            "total_filled_quantity": self.total_filled_quantity,
            "weighted_avg_price": self.weighted_avg_price,
            "total_commission": self.total_commission,
            "total_fees": self.total_fees,
            "total_notional": self.total_notional,
            "first_fill_timestamp": self.first_fill_timestamp.isoformat() if self.first_fill_timestamp else None,
            "last_fill_timestamp": self.last_fill_timestamp.isoformat() if self.last_fill_timestamp else None,
            "execution_duration_seconds": self.execution_duration_seconds,
            "total_slippage_bps": self.total_slippage_bps,
            "total_spread_cost_bps": self.total_spread_cost_bps,
            "total_impact_bps": self.total_impact_bps,
            "total_explicit_cost_bps": self.total_explicit_cost_bps,
            "total_implicit_cost_bps": self.total_implicit_cost_bps,
            "total_cost_bps": self.total_cost_bps,
            "implementation_shortfall_bps": self.implementation_shortfall_bps,
            "fill_rate_pct": self.fill_rate_pct,
        }


@dataclass
class TransactionCostReport:
    """
    Detailed transaction cost analysis report.
    
    Provides a comprehensive breakdown of all costs associated with an execution,
    suitable for performance reporting and compliance.
    """
    # identifiers
    order_id: str
    symbol: str
    side: OrderSide
    strategy: Optional[str] = None
    
    # order parameters
    order_quantity: float = 0.0
    order_type: OrderType = OrderType.MARKET
    algorithm: AlgorithmType = AlgorithmType.MARKET
    
    # market data
    arrival_price: float = 0.0  # Mid price when order entered system
    pre_trade_benchmark: float = 0.0  # Benchmark used for cost calc (e.g., mid, vwap)
    post_trade_benchmark: Optional[float] = None  # Benchmark after execution
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    
    # execution results
    filled_quantity: float = 0.0
    weighted_avg_price: float = 0.0
    total_notional: float = 0.0
    
    # explicit costs
    explicit_commission: float = 0.0
    explicit_fees: float = 0.0
    explicit_cost_bps: float = 0.0
    
    # implicit costs
    implicit_slippage: float = 0.0  # in $
    implicit_slippage_bps: float = 0.0
    implicit_spread: float = 0.0  # in $
    implicit_spread_bps: float = 0.0
    implicit_impact: float = 0.0  # in $
    implicit_impact_bps: float = 0.0
    total_implicit_cost: float = 0.0
    total_implicit_cost_bps: float = 0.0
    
    # aggregate
    total_cost: float = 0.0
    total_cost_bps: float = 0.0
    
    # timing
    submitted_at: datetime = field(default_factory=datetime.now)
    first_fill_at: Optional[datetime] = None
    last_fill_at: Optional[datetime] = None
    execution_duration_seconds: Optional[float] = None
    
    # benchmarks
    implementation_shortfall: float = 0.0  # in $
    implementation_shortfall_bps: float = 0.0
    participation_rate: Optional[float] = None  # % of market volume
    
    # metadata
    broker: str = ""
    child_orders_count: int = 0
    fills_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/transmission."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "strategy": self.strategy,
            "order_quantity": self.order_quantity,
            "order_type": self.order_type.value,
            "algorithm": self.algorithm.value,
            "arrival_price": self.arrival_price,
            "pre_trade_benchmark": self.pre_trade_benchmark,
            "post_trade_benchmark": self.post_trade_benchmark,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "filled_quantity": self.filled_quantity,
            "weighted_avg_price": self.weighted_avg_price,
            "total_notional": self.total_notional,
            "explicit_commission": self.explicit_commission,
            "explicit_fees": self.explicit_fees,
            "explicit_cost_bps": self.explicit_cost_bps,
            "implicit_slippage": self.implicit_slippage,
            "implicit_slippage_bps": self.implicit_slippage_bps,
            "implicit_spread": self.implicit_spread,
            "implicit_spread_bps": self.implicit_spread_bps,
            "implicit_impact": self.implicit_impact,
            "implicit_impact_bps": self.implicit_impact_bps,
            "total_implicit_cost": self.total_implicit_cost,
            "total_implicit_cost_bps": self.total_implicit_cost_bps,
            "total_cost": self.total_cost,
            "total_cost_bps": self.total_cost_bps,
            "submitted_at": self.submitted_at.isoformat(),
            "first_fill_at": self.first_fill_at.isoformat() if self.first_fill_at else None,
            "last_fill_at": self.last_fill_at.isoformat() if self.last_fill_at else None,
            "execution_duration_seconds": self.execution_duration_seconds,
            "implementation_shortfall": self.implementation_shortfall,
            "implementation_shortfall_bps": self.implementation_shortfall_bps,
            "participation_rate": self.participation_rate,
            "broker": self.broker,
            "child_orders_count": self.child_orders_count,
            "fills_count": self.fills_count,
        }


@dataclass
class ChildOrder:
    """
    A child order generated by an algorithm.
    
    Algorithms split parent orders into child orders with specific quantities
    and scheduled execution times.
    """
    quantity: float
    scheduled_time: datetime
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    
    # tracking
    child_order_id: Optional[str] = None
    parent_order_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_quantity: float = 0.0
    fill_price: Optional[float] = None
    
    # metadata
    slice_number: int = 0
    total_slices: int = 0
    
    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("Child order quantity must be positive")
    
    @property
    def is_filled(self) -> bool:
        return self.filled_quantity >= self.quantity
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "child_order_id": self.child_order_id,
            "parent_order_id": self.parent_order_id,
            "quantity": self.quantity,
            "scheduled_time": self.scheduled_time.isoformat(),
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "status": self.status.value,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "filled_quantity": self.filled_quantity,
            "fill_price": self.fill_price,
            "slice_number": self.slice_number,
            "total_slices": self.total_slices,
        }
