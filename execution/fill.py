"""
Order fill simulation module.

This module simulates order fills for paper trading:
- Market orders: Fill at current price (with optional slippage)
- Limit orders: Fill only if price is favorable
- Commission calculation
"""

from typing import Optional
import random
from datetime import datetime

from .order import Order, OrderType, OrderStatus, OrderSide


class OrderFiller:
    """
    Simulate order fills for paper trading.
    
    Paper Trading Fill Simulation:
    ------------------------------
    - Market orders: Fill immediately at current price
    - Slippage: Optional price impact (default: 0%)
    - Commission: Fee per trade (default: 0.1%)
    - Limit orders: Fill if price is at or better than limit
    
    Why Simulate Fills?
    -------------------
    1. Realistic testing without real money
    2. Understand execution costs (slippage, commission)
    3. Test strategy in safe environment
    4. Validate risk management before live trading
    """
    
    def __init__(
        self,
        commission: float = 0.001,  # 0.1% commission
        slippage_pct: float = 0.0,  # 0% slippage by default
        enable_slippage: bool = False
    ):
        """
        Initialize order filler.
        
        Args:
            commission: Commission rate as decimal (0.001 = 0.1%)
            slippage_pct: Slippage percentage (0.001 = 0.1%)
            enable_slippage: Whether to apply slippage to market orders
        """
        self.commission = commission
        self.slippage_pct = slippage_pct
        self.enable_slippage = enable_slippage
    
    def fill_market_order(
        self,
        order: Order,
        current_price: float,
        current_high: Optional[float] = None,
        current_low: Optional[float] = None
    ) -> Order:
        """
        Fill a market order.
        
        Args:
            order: Order to fill
            current_price: Current market price (closing price)
            current_high: Current high price (optional, for more realistic fills)
            current_low: Current low price (optional, for more realistic fills)
        
        Returns:
            Updated order with fill information
        
        Market Order Fill Logic:
        -----------------------
        - BUY orders: Fill at ask price (current_price or high)
        - SELL orders: Fill at bid price (current_price or low)
        - Apply slippage if enabled
        - Calculate commission
        """
        if order.status != OrderStatus.PENDING:
            return order
        
        if order.order_type != OrderType.MARKET:
            # Market order filler shouldn't handle limit orders
            return order
        
        # Determine fill price
        if order.is_buy():
            # BUY orders typically fill at ask (slightly above bid)
            fill_price = current_high if current_high is not None else current_price
            
            # Apply slippage (buy orders typically pay slightly more)
            if self.enable_slippage:
                slippage = fill_price * self.slippage_pct
                fill_price += slippage
        else:
            # SELL orders typically fill at bid (slightly below ask)
            fill_price = current_low if current_low is not None else current_price
            
            # Apply slippage (sell orders typically receive slightly less)
            if self.enable_slippage:
                slippage = fill_price * self.slippage_pct
                fill_price -= slippage
        
        # Fill entire order
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        
        # Calculate commission
        order_value = order.filled_quantity * order.filled_price
        order.commission = order_value * self.commission
        
        return order
    
    def fill_limit_order(
        self,
        order: Order,
        current_price: float,
        current_high: Optional[float] = None,
        current_low: Optional[float] = None
    ) -> Order:
        """
        Fill a limit order if price is favorable.
        
        Args:
            order: Limit order to fill
            current_price: Current market price
            current_high: Current high price
            current_low: Current low price
        
        Returns:
            Updated order (filled if price conditions met)
        
        Limit Order Fill Logic:
        ----------------------
        - BUY limit: Fill if current_price <= limit_price
        - SELL limit: Fill if current_price >= limit_price
        - Can use high/low to simulate intraday fills
        """
        if order.status != OrderStatus.PENDING:
            return order
        
        if order.order_type != OrderType.LIMIT:
            return order
        
        if order.price is None:
            order.status = OrderStatus.REJECTED
            return order
        
        # Check if limit order can be filled
        can_fill = False
        
        if order.is_buy():
            # BUY limit: fill if price is at or below limit
            # Use low price if available (more realistic)
            check_price = current_low if current_low is not None else current_price
            can_fill = check_price <= order.price
        else:
            # SELL limit: fill if price is at or above limit
            # Use high price if available (more realistic)
            check_price = current_high if current_high is not None else current_price
            can_fill = check_price >= order.price
        
        if can_fill:
            # Fill at limit price (or better)
            fill_price = order.price
            order.filled_quantity = order.quantity
            order.filled_price = fill_price
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now()
            
            # Calculate commission
            order_value = order.filled_quantity * order.filled_price
            order.commission = order_value * self.commission
        # If can't fill, order remains PENDING
        
        return order
    
    def fill_order(
        self,
        order: Order,
        current_price: float,
        current_high: Optional[float] = None,
        current_low: Optional[float] = None
    ) -> Order:
        """
        Fill an order based on its type.
        
        Args:
            order: Order to fill
            current_price: Current market price
            current_high: Current high price (optional)
            current_low: Current low price (optional)
        
        Returns:
            Updated order
        """
        if order.order_type == OrderType.MARKET:
            return self.fill_market_order(order, current_price, current_high, current_low)
        elif order.order_type == OrderType.LIMIT:
            return self.fill_limit_order(order, current_price, current_high, current_low)
        else:
            # Unknown order type
            return order
    
    def __str__(self) -> str:
        """String representation."""
        slippage_str = f", slippage={self.slippage_pct*100:.2f}%" if self.enable_slippage else ""
        return f"OrderFiller(commission={self.commission*100:.2f}%{slippage_str})"

