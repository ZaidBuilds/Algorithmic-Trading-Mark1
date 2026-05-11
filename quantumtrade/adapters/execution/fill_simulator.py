"""
Fill simulator for backtesting order execution.

Simulates order fills with realistic slippage, spread costs, and market impact
using various models. Supports partial fills and timing simulation.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import random
import numpy as np

from .models import BrokerOrder, Fill, OrderSide
from .cost_models import (
    SlippageModel,
    FixedSlippageModel,
    VolumeBasedSlippageModel,
    MarketImpactModel,
    SpreadCostModel,
    calculate_total_implicit_cost,
)


class FillSimulator:
    """
    Simulates order fills during backtesting.
    
    Takes an order and a market data bar (or order book snapshot) and
    produces simulated fills with configurable slippage and partial fill behavior.
    
    Key Features:
    - Multiple slippage models (fixed, volume-based, impact-based)
    - Partial fill simulation
    - Spread cost modeling
    - Time-based fill probability
    """
    
    def __init__(
        self,
        slippage_model: str = "volume",
        fixed_slippage_bps: float = 1.0,
        enable_spread_cost: bool = True,
        enable_market_impact: bool = True,
        impact_coefficient: float = 0.1,
        fill_probability: float = 0.95,
        min_fill_quantity: float = 1.0,
        unlimited_liquidity: bool = False,
        seed: Optional[int] = None,
    ):
        """
        Initialize the fill simulator.

        Args:
            slippage_model: "fixed", "volume", "sqrt", "linear"
            fixed_slippage_bps: Fixed slippage (when using "fixed" model)
            enable_spread_cost: Add bid-ask spread cost simulation
            enable_market_impact: Apply market impact model
            impact_coefficient: Coefficient for impact model
            fill_probability: Base probability of fill per bar (for liquidity simulation)
            min_fill_quantity: Minimum quantity for a partial fill
            unlimited_liquidity: If True, ignore bar volume limits and always fill full quantity
            seed: Random seed for reproducibility
        """
        self.slippage_model_type = slippage_model
        self.fixed_slippage_bps = fixed_slippage_bps
        self.enable_spread_cost = enable_spread_cost
        self.enable_market_impact = enable_market_impact
        self.fill_probability = fill_probability
        self.min_fill_quantity = min_fill_quantity
        self.unlimited_liquidity = unlimited_liquidity

        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        # Initialize underlying models
        if slippage_model == "fixed":
            self.slippage_model = FixedSlippageModel(bps=fixed_slippage_bps)
        elif slippage_model == "volume" or slippage_model == "sqrt":
            self.slippage_model = VolumeBasedSlippageModel(impact_factor=1.0)
        elif slippage_model == "linear":
            self.slippage_model = LinearSlippageModel(bps_per_unit=0.01)
        else:
            self.slippage_model = FixedSlippageModel(bps=1.0)
        
        self.impact_model = MarketImpactModel(permanent_coeff=impact_coefficient)
        self.spread_model = SpreadCostModel()
    
    def simulate_fill(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]] = None,
        avg_daily_volume: Optional[float] = None,
    ) -> Optional[Fill]:
        """
        Simulate a single fill for an order given market data.
        
        Args:
            order: The order to simulate
            bar: OHLCV bar data (requires at least: close, volume)
                Example: {"close": 100.0, "volume": 1000000, "timestamp": ...}
            order_book: Optional order book snapshot with bid/ask
                Example: {"bid": 99.9, "ask": 100.1, "bid_size": 1000, "ask_size": 1000}
            avg_daily_volume: Optional ADV for volume-based models
            
        Returns:
            Fill object if fill occurs, None if order remains unfilled
        """
        # Determine if order fills in this bar based on liquidity
        if random.random() > self.fill_probability:
            return None  # No fill this bar
        
        # Determine fill quantity (could be partial)
        remaining_qty = order.remaining_quantity
        if remaining_qty <= 0:
            return None
        
        # Partial fill logic: smaller orders fill completely, larger may partially fill
        fill_qty = self._determine_fill_quantity(order, bar, order_book)
        if fill_qty <= 0:
            return None
        
        fill_qty = min(fill_qty, remaining_qty)
        
        # Determine fill price with slippage
        base_price = bar["close"]
        fill_price = self._calculate_fill_price(order, bar, order_book, avg_daily_volume, fill_qty)
        
        # Create fill object
        fill_id = f"fill_{order.order_id or 'sim'}_{random.randint(100000, 999999)}"
        trade_timestamp = bar.get("timestamp", datetime.now())
        if isinstance(trade_timestamp, (int, float)):
            # Assume timestamp in millis if numeric
            trade_timestamp = datetime.fromtimestamp(trade_timestamp / 1000)
        
        fill = Fill(
            fill_id=fill_id,
            order_id=order.order_id or "sim",
            symbol=order.symbol,
            side=order.side,
            quantity=fill_qty,
            price=fill_price,
            trade_timestamp=trade_timestamp,
            received_timestamp=datetime.now(),
            broker=order.broker or "simulated",
        )
        
        return fill
    
    def _determine_fill_quantity(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]],
    ) -> float:
        """Determine how much of the order fills in this bar."""
        remaining = order.remaining_quantity

        # Unlimited liquidity mode: fill everything immediately
        if self.unlimited_liquidity:
            return remaining

        # Simple model: fill up to min(remaining, bar_volume * participation_rate)
        bar_volume = bar.get("volume", 0)
        participation_rate = 0.10  # Assume 10% of bar volume

        # Check order book depth if available
        if order_book:
            depth = self._get_available_depth(order, order_book)
            if depth > 0:
                fill_qty = min(remaining, depth * participation_rate)
            else:
                fill_qty = min(remaining, bar_volume * participation_rate)
        else:
            fill_qty = min(remaining, bar_volume * participation_rate)

        # Enforce minimum fill quantity
        if fill_qty < self.min_fill_quantity:
            return 0.0

        # Cap at remaining
        return min(fill_qty, remaining)
    
    def _get_available_depth(
        self,
        order: BrokerOrder,
        order_book: Dict[str, Any],
    ) -> float:
        """Get available liquidity at best price from order book."""
        if order.is_buy:
            available = order_book.get("ask_size", 0)
        else:
            available = order_book.get("bid_size", 0)
        return available
    
    def _calculate_fill_price(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]],
        avg_daily_volume: Optional[float],
        quantity: float,
    ) -> float:
        """
        Calculate fill price including slippage.
        
        Base price depends on order book or close price.
        Slippage pushes price away from mid for buy/sell.
        """
        base_price = bar["close"]
        
        # Use order book if available
        if order_book:
            mid_price = (order_book.get("bid", base_price) + order_book.get("ask", base_price)) / 2
            if order.is_buy:
                base_price = order_book.get("ask", base_price)
            else:
                base_price = order_book.get("bid", base_price)
        else:
            mid_price = base_price
        
        # Calculate slippage bps
        slippage_bps = self.slippage_model.calculate_slippage(
            side=order.side,
            expected_price=mid_price,
            actual_price=base_price,
            quantity=quantity,
            avg_daily_volume=avg_daily_volume,
        )
        
        # Calculate market impact (if enabled and meaningful quantity)
        impact_bps = 0.0
        if self.enable_market_impact and avg_daily_volume and quantity > 0:
            impact_result = self.impact_model.calculate_impact(
                side=order.side,
                order_quantity=quantity,
                avg_daily_volume=avg_daily_volume,
                price=base_price,
            )
            impact_bps = impact_result["total_bps"]
        
        # Calculate spread cost separately
        spread_cost_bps = 0.0
        if self.enable_spread_cost and order_book:
            spread_cost_bps = self.spread_model.calculate_spread_cost(
                side=order.side,
                fill_price=base_price,
                bid_price=order_book.get("bid", base_price),
                ask_price=order_book.get("ask", base_price),
                quantity=quantity,
            )
        
        # Total adverse movement in bps
        total_adverse_bps = slippage_bps + impact_bps
        
        # Apply slippage to base price
        if order.is_buy:
            # Buy: pay more → increase price
            fill_price = base_price * (1 + total_adverse_bps / 10000)
        else:
            # Sell: receive less → decrease price
            fill_price = base_price * (1 - total_adverse_bps / 10000)
        
        # Store cost metrics on fill (filled later in fill creation)
        # For now just return price
        return fill_price
    
    def simulate_order_execution(
        self,
        order: BrokerOrder,
        bars: List[Dict[str, Any]],
        order_books: Optional[List[Dict[str, Any]]] = None,
        avg_daily_volume: Optional[float] = None,
    ) -> List[Fill]:
        """
        Simulate full execution of an order over multiple bars.
        
        Args:
            order: The parent order
            bars: List of market data bars (chronological)
            order_books: Optional corresponding order book snapshots
            avg_daily_volume: Average daily volume for impact calculation
            
        Returns:
            List of fills collected over time
        """
        fills = []
        remaining = order.quantity
        
        for i, bar in enumerate(bars):
            if remaining <= 0:
                break
            
            order_book = order_books[i] if order_books and i < len(order_books) else None
            fill = self.simulate_fill(order, bar, order_book, avg_daily_volume)
            
            if fill:
                fills.append(fill)
                remaining -= fill.quantity
        
        return fills


class HistoricalFillSimulator(FillSimulator):
    """
    Extends FillSimulator with historically-calibrated parameters.
    
    Uses historical trade data to calibrate slippage and fill probabilities.
    """
    
    def __init__(
        self,
        historical_slippage_stats: Optional[Dict[str, float]] = None,
        **kwargs
    ):
        """
        Args:
            historical_slippage_stats: Dict with 'mean', 'std', 'p95' slippage bps
        """
        super().__init__(**kwargs)
        self.historical_stats = historical_slippage_stats or {}
    
    def simulate_fill(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]] = None,
        avg_daily_volume: Optional[float] = None,
    ) -> Optional[Fill]:
        """Override to incorporate historical distributions."""
        # Could sample from historical slippage distribution
        # For now, use parent method
        return super().simulate_fill(order, bar, order_book, avg_daily_volume)


def create_simulator(
    config: Dict[str, Any],
) -> FillSimulator:
    """
    Factory function to create FillSimulator from configuration.

    Example config:
    {
        "slippage_model": "volume",
        "fixed_slippage_bps": 1.0,
        "enable_spread_cost": True,
        "enable_market_impact": True,
        "fill_probability": 0.95,
        "unlimited_liquidity": True,  # for backtest mode
    }
    """
    return FillSimulator(
        slippage_model=config.get("slippage_model", "volume"),
        fixed_slippage_bps=config.get("fixed_slippage_bps", 1.0),
        enable_spread_cost=config.get("enable_spread_cost", True),
        enable_market_impact=config.get("enable_market_impact", True),
        impact_coefficient=config.get("impact_coefficient", 0.1),
        fill_probability=config.get("fill_probability", 0.95),
        min_fill_quantity=config.get("min_fill_quantity", 1.0),
        unlimited_liquidity=config.get("unlimited_liquidity", False),
        seed=config.get("seed"),
    )
