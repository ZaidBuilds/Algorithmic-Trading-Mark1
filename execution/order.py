"""
Order data structures for trading execution.

This module defines order types, sides, statuses, and the Order class.
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class OrderSide(Enum):
    """Order side (buy or sell)."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type."""
    MARKET = "MARKET"  # Execute at current market price
    LIMIT = "LIMIT"    # Execute at specified price or better
    STOP = "STOP"      # Stop order (triggers when price reaches level)


class OrderStatus(Enum):
    """Order status."""
    PENDING = "PENDING"      # Order submitted, waiting for fill
    FILLED = "FILLED"        # Order completely filled
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Order partially filled
    CANCELLED = "CANCELLED"  # Order cancelled
    REJECTED = "REJECTED"    # Order rejected


@dataclass
class Order:
    """
    Order data structure.
    
    Attributes:
        order_id: Unique order identifier
        symbol: Trading symbol
        side: BUY or SELL
        order_type: MARKET, LIMIT, or STOP
        quantity: Number of shares/units
        price: Limit price (for LIMIT orders)
        status: Current order status
        filled_quantity: Quantity that has been filled
        filled_price: Average fill price
        created_at: Order creation timestamp
        filled_at: Order fill timestamp (if filled)
        commission: Commission paid
    """
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None  # Limit price for LIMIT orders
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: Optional[float] = None
    created_at: datetime = None
    filled_at: Optional[datetime] = None
    commission: float = 0.0
    
    def __post_init__(self):
        """Initialize order."""
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def is_buy(self) -> bool:
        """Check if order is a buy order."""
        return self.side == OrderSide.BUY
    
    def is_sell(self) -> bool:
        """Check if order is a sell order."""
        return self.side == OrderSide.SELL
    
    def is_market(self) -> bool:
        """Check if order is a market order."""
        return self.order_type == OrderType.MARKET
    
    def is_limit(self) -> bool:
        """Check if order is a limit order."""
        return self.order_type == OrderType.LIMIT
    
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED
    
    def is_pending(self) -> bool:
        """Check if order is pending."""
        return self.status == OrderStatus.PENDING
    
    def get_remaining_quantity(self) -> float:
        """Get remaining quantity to fill."""
        return self.quantity - self.filled_quantity
    
    def get_value(self) -> float:
        """Get total order value (quantity * price)."""
        if self.filled_price:
            return self.filled_quantity * self.filled_price
        elif self.price:
            return self.quantity * self.price
        return 0.0
    
    def __str__(self) -> str:
        """String representation of order."""
        price_str = f"@ ${self.price:.2f}" if self.price else ""
        status_str = f" [{self.status.value}]"
        if self.filled_price:
            status_str += f" Filled: {self.filled_quantity:.2f} @ ${self.filled_price:.2f}"
        return f"{self.side.value} {self.quantity:.2f} {self.symbol} {price_str}{status_str}"

