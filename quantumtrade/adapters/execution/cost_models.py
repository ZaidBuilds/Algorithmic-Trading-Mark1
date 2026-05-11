"""
Cost models for simulating market impact, slippage, and spread costs.

These models estimate implicit transaction costs based on order characteristics,
market conditions, and historical relationships.
"""

from typing import Optional
import numpy as np

from .models import OrderSide

from .models import OrderSide


class SlippageModel:
    """
    Base class for slippage models.
    
    Slippage is the difference between expected execution price and actual fill price,
    typically expressed in basis points (bps).
    """
    
    def calculate_slippage(
        self,
        side: str,
        expected_price: float,
        actual_price: float,
        quantity: float,
        **kwargs
    ) -> float:
        """
        Calculate slippage in basis points.
        
        Args:
            side: OrderSide.BUY or OrderSide.SELL
            expected_price: Price before slippage (arrival or mid)
            actual_price: Actual fill price
            quantity: Order size
            **kwargs: Additional market context
            
        Returns:
            Slippage in basis points (positive = adverse)
        """
        raise NotImplementedError


class FixedSlippageModel(SlippageModel):
    """Fixed slippage model — adds/subtracts fixed bps."""
    
    def __init__(self, bps: float = 1.0):
        """
        Args:
            bps: Fixed slippage in basis points
        """
        self.bps = bps
    
    def calculate_slippage(
        self,
        side: str,
        expected_price: float,
        actual_price: float,
        quantity: float,
        **kwargs
    ) -> float:
        """Return configured fixed slippage."""
        return self.bps


class VolumeBasedSlippageModel(SlippageModel):
    """
    Volume-based slippage model.
    
    Slippage scales with order size relative to average daily volume (ADV).
    Common heuristic: 1 bps slippage per 1% of ADV.
    Formula: slippage_bps = participation_rate * impact_factor
    """
    
    def __init__(self, impact_factor: float = 1.0):
        """
        Args:
            impact_factor: Multiplier for participation rate impact (default 1.0)
        """
        self.impact_factor = impact_factor
    
    def calculate_slippage(
        self,
        side: str,
        expected_price: float,
        actual_price: float,
        quantity: float,
        avg_daily_volume: float = 0.0,
        **kwargs
    ) -> float:
        """
        Calculate slippage based on order size relative to ADV.
        
        If ADV not provided, returns 0.
        """
        if avg_daily_volume <= 0:
            return 0.0
        
        participation_rate = quantity / avg_daily_volume
        slippage_bps = participation_rate * self.impact_factor * 10000
        return slippage_bps


class SquareRootSlippageModel(SlippageModel):
    """
    Square-root slippage model (common in algo trading).
    
    Market impact ~ sqrt(quantity / ADV).
    """
    
    def __init__(self, coefficient: float = 0.1):
        """
        Args:
            coefficient: Impact coefficient (sigma of price)
        """
        self.coefficient = coefficient
    
    def calculate_slippage(
        self,
        side: str,
        expected_price: float,
        actual_price: float,
        quantity: float,
        avg_daily_volume: float = 0.0,
        **kwargs
    ) -> float:
        """Square-root impact model."""
        if avg_daily_volume <= 0 or quantity <= 0:
            return 0.0
        
        participation_rate = quantity / avg_daily_volume
        # Sqrt model
        impact = self.coefficient * np.sqrt(participation_rate)
        return impact * 10000


class LinearSlippageModel(SlippageModel):
    """
    Linear slippage model (simplest).
    
    Slippage proportional to quantity.
    """
    
    def __init__(self, bps_per_unit: float = 0.01):
        """
        Args:
            bps_per_unit: Slippage bps per unit quantity
        """
        self.bps_per_unit = bps_per_unit
    
    def calculate_slippage(
        self,
        side: str,
        expected_price: float,
        actual_price: float,
        quantity: float,
        **kwargs
    ) -> float:
        """Linear slippage."""
        return quantity * self.bps_per_unit


class MarketImpactModel:
    """
    Separate market impact model (permanent + temporary).
    
    Market impact is the sustained price change due to the trade itself.
    It has two components:
    - Permanent impact: lasting price change
    - Temporary impact: immediate price change that reverts
    """
    
    def __init__(
        self,
        permanent_coeff: float = 0.1,
        temporary_coeff: float = 0.05,
    ):
        """
        Args:
            permanent_coeff: Permanent impact coefficient
            temporary_coeff: Temporary impact coefficient
        """
        self.permanent_coeff = permanent_coeff
        self.temporary_coeff = temporary_coeff
    
    def calculate_impact(
        self,
        side: str,
        order_quantity: float,
        avg_daily_volume: float,
        price: float,
        volatility: float = 0.02,
    ) -> dict:
        """
        Calculate permanent and temporary market impact.
        
        Returns:
            dict with 'permanent_bps', 'temporary_bps', 'total_bps'
        """
        if avg_daily_volume <= 0:
            return {"permanent_bps": 0.0, "temporary_bps": 0.0, "total_bps": 0.0}
        
        participation = order_quantity / avg_daily_volume
        
        # Simplified Almgren-Chriss style impact
        permanent = self.permanent_coeff * participation * 10000
        temporary = self.temporary_coeff * np.sqrt(participation) * 10000
        total = permanent + temporary
        
        return {
            "permanent_bps": permanent,
            "temporary_bps": temporary,
            "total_bps": total,
        }


class SpreadCostModel:
    """
    Model for bid-ask spread costs.
    
    For a buy order: you pay the ask price; benchmark is mid price.
    Spread cost = (ask - mid) / mid * 10000 bps.
    For a sell order: you receive the bid price; benchmark is mid.
    """
    
    def calculate_spread_cost(
        self,
        side: str,
        fill_price: float,
        bid_price: float,
        ask_price: float,
        quantity: float,
    ) -> float:
        """
        Calculate spread cost in basis points.
        
        Args:
            side: BUY or SELL
            fill_price: Actual execution price
            bid_price: Current bid
            ask_price: Current ask
            quantity: Order size
            
        Returns:
            Spread cost in bps (always positive = cost)
        """
        mid_price = (bid_price + ask_price) / 2
        
        if side == OrderSide.BUY:
            # Buyer pays ask; ideal is mid
            ideal_price = mid_price
            actual = ask_price  # Market buy executes at ask
        elif side == OrderSide.SELL:
            # Seller receives bid; ideal is mid
            ideal_price = mid_price
            actual = bid_price  # Market sell executes at bid
        else:
            return 0.0
        
        if actual <= 0 or ideal_price <= 0:
            return 0.0
        
        spread_cost_bps = abs((actual - ideal_price) / ideal_price) * 10000
        return spread_cost_bps


def calculate_total_implicit_cost(
    slippage_bps: float,
    spread_cost_bps: float,
    impact_bps: float,
    notional_value: float,
) -> float:
    """
    Aggregate implicit costs into dollar amount.
    
    Args:
        slippage_bps: Slippage cost in basis points
        spread_cost_bps: Spread cost in basis points
        impact_bps: Market impact cost in basis points
        notional_value: Total trade value
        
    Returns:
        Total implicit cost in dollars
    """
    total_bps = slippage_bps + spread_cost_bps + impact_bps
    return notional_value * (total_bps / 10000)


def calculate_explicit_cost_bps(
    commission: float,
    fees: float,
    notional_value: float,
) -> float:
    """
    Calculate explicit costs (commissions + fees) in basis points.
    """
    if notional_value <= 0:
        return 0.0
    explicit_cost = commission + fees
    return (explicit_cost / notional_value) * 10000


def calculate_implementation_shortfall(
    arrival_price: float,
    average_fill_price: float,
    side: str,
    quantity: float,
) -> dict:
    """
    Calculate implementation shortfall — the total cost of executing an order
    compared to the arrival price.
    
    IS = (avg_fill_price - arrival_price) / arrival_price * quantity
    
    Returns both dollar and bps values.
    """
    if arrival_price <= 0:
        return {"shortfall_dollars": 0.0, "shortfall_bps": 0.0}
    
    price_diff = average_fill_price - arrival_price
    if side == OrderSide.SELL:
        # For sell, lower price is better → invert sign
        price_diff = -price_diff
    
    shortfall_dollars = price_diff * quantity
    shortfall_bps = (price_diff / arrival_price) * 10000
    
    return {
        "shortfall_dollars": shortfall_dollars,
        "shortfall_bps": shortfall_bps,
    }
