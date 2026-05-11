"""
Liquidity constraints and limit order fill simulation.

Models:
- Limit order fills only if price crosses limit
- Partial fills when order book depth insufficient
- Liquidity taking vs providing strategies
"""

from typing import Optional, Dict, List, Tuple
from datetime import datetime

import numpy as np

from quantumtrade.adapters.execution.models import OrderSide, OrderType, Fill


class LiquidityModel:
    """
    Models market liquidity constraints.

    Real markets have finite depth:
    - Large orders can't be filled instantly at one price
    - Order book depth limits immediate execution
    - Market orders may partially fill and continue

    This model simulates:
    - Participation rate limits (max % of bar volume)
    - Order book depth walking
    - Partial fills
    - Unfilled order remnants
    """

    def __init__(
        self,
        participation_rate: float = 0.10,
        min_fill_quantity: float = 1.0,
        allow_partial_fills: bool = True,
    ):
        """
        Args:
            participation_rate: Max fraction of bar volume (0.10 = 10%)
            min_fill_quantity: Minimum shares for a fill event
            allow_partial_fills: If False, all-or-nothing execution
        """
        self.participation_rate = participation_rate
        self.min_fill_quantity = min_fill_quantity
        self.allow_partial_fills = allow_partial_fills

    def determine_fill_quantity(
        self,
        order_quantity: float,
        bar_volume: float,
        order_book_depth: Optional[float] = None,
        remaining_quantity: float = None,
    ) -> Tuple[float, bool]:
        """
        Determine fill quantity for current bar/tick.

        Args:
            order_quantity: Original order size
            bar_volume: Trading volume in this bar
            order_book_depth: Available liquidity at best price (optional)
            remaining_quantity: How much of order remains (default = order_quantity)

        Returns:
            (fill_qty, is_complete): fill quantity and whether order is fully filled
        """
        if remaining_quantity is None:
            remaining_quantity = order_quantity

        if remaining_quantity <= 0:
            return 0.0, True

        # Base limit: % of bar volume
        max_by_volume = bar_volume * self.participation_rate

        # Order book depth constraint (if available)
        if order_book_depth is not None and order_book_depth > 0:
            max_by_depth = order_book_depth
        else:
            max_by_depth = max_by_volume

        # Max fill this bar = min(remaining, volume limit, depth)
        fill_qty = min(remaining_quantity, max_by_volume, max_by_depth)

        # Enforce minimum fill
        if fill_qty < self.min_fill_quantity:
            fill_qty = 0.0

        # Partial fill logic
        if self.allow_partial_fills and fill_qty > 0:
            is_complete = fill_qty >= remaining_quantity
            return fill_qty, is_complete
        else:
            # All-or-nothing: only fill if full quantity available
            if fill_qty >= remaining_quantity:
                return remaining_quantity, True
            else:
                return 0.0, False

    def simulate_order_execution_path(
        self,
        order_quantity: float,
        volume_series: List[float],
        order_book_depths: Optional[List[float]] = None,
    ) -> List[Tuple[int, float, datetime]]:
        """
        Simulate order filling over multiple bars.

        Returns list of (bar_index, fill_quantity, timestamp) for each fill.
        Bars are processed sequentially until order is filled or runs out.

        Args:
            order_quantity: Total order size
            volume_series: Volume for each bar in order
            order_book_depths: Optional depth per bar (same length as volume_series)

        Returns:
            List of fill events (bar_idx, qty, timestamp stub)
            Caller maps bar_idx → actual timestamp
        """
        fills = []
        remaining = order_quantity
        depths = order_book_depths or [None] * len(volume_series)

        for i, (vol, depth) in enumerate(zip(volume_series, depths)):
            if remaining <= 0:
                break

            fill_qty, is_complete = self.determine_fill_quantity(
                order_quantity=order_quantity,
                bar_volume=vol,
                order_book_depth=depth,
                remaining_quantity=remaining,
            )

            if fill_qty > 0:
                fills.append((i, fill_qty, None))  # timestamp filled by caller
                remaining -= fill_qty

            if is_complete:
                break

        return fills


class LimitOrderFillModel:
    """
    Model fills for limit orders (price-constrained).

    A limit order only fills if the market price reaches the limit price.
    Can receive price improvement if fill occurs inside spread.
    """

    def __init__(
        self,
        fill_probability: float = 0.5,
        price_improvement_bps: float = 0.5,
    ):
        """
        Args:
            fill_probability: Probability of fill if price touches limit (0-1)
            price_improvement_bps: Average improvement inside limit price
        """
        self.fill_probability = fill_probability
        self.improvement_bps = price_improvement_bps

    def simulate_limit_fill(
        self,
        side: OrderSide,
        limit_price: float,
        high_price: float,
        low_price: float,
        volume: float,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[bool, float]:
        """
        Determine if limit order fills during a bar.

        Args:
            side: BUY or SELL
            limit_price: Order's limit price
            high_price: Bar high
            low_price: Bar low
            volume: Bar volume (for fill probability scaling)
            rng: Random generator

        Returns:
            (filled, fill_price): Whether filled and at what price
        """
        rng = rng or np.random.default_rng()

        # Check if limit price was reached
        if side == OrderSide.BUY:
            price_touched = low_price <= limit_price
        else:
            price_touched = high_price >= limit_price

        if not price_touched:
            return False, 0.0

        # If touched, probability of actual fill depends on:
        # - Time at that price level (often brief)
        # - Our position in order book queue
        # - Available volume at that price
        fill_prob = self.fill_probability

        if rng.random() > fill_prob:
            return False, 0.0

        # Fill occurred — determine price with improvement
        if side == OrderSide.BUY:
            # Buy limit: we get price <= limit_price
            # Price improvement: fill below limit (better for buyer)
            improvement = self.improvement_bps / 10000
            fill_price = limit_price * (1 - improvement)
            # But also cannot be below the market bid (would be too good)
            # Assume fill_price bounded by [low, limit]
            fill_price = max(fill_price, low_price)
        else:
            # Sell limit: we get price >= limit_price
            improvement = self.improvement_bps / 10000
            fill_price = limit_price * (1 + improvement)
            fill_price = min(fill_price, high_price)

        return True, fill_price


class GapRiskModel:
    """
    Model overnight/weekend gap risk.

    Gaps occur when price jumps between sessions (no trading in between).
    Can cause stop-loss orders to fill far from expected price.

    Gap characteristics:
    - Direction: can gap against you (stop loss triggered)
    - Size: typically larger than intra-day moves
    - Frequency: ~1-3% of days have >1% gaps for equities
    """

    def __init__(
        self,
        gap_probability: float = 0.02,
        mean_gap_pct: float = 0.5,
        gap_std_pct: float = 1.0,
        max_gap_pct: float = 10.0,
    ):
        """
        Args:
            gap_probability: Daily probability of a gap (e.g., 0.02 = 2%)
            mean_gap_pct: Average gap size (%) if gap occurs
            gap_std_pct: Std dev of gap size
            max_gap_pct: Maximum plausible gap (e.g., 10% for stocks)
        """
        self.gap_probability = gap_probability
        self.mean_gap = mean_gap_pct / 100  # Convert to decimal
        self.gap_std = gap_std_pct / 100
        self.max_gap = max_gap_pct / 100

    def simulate_gap(
        self,
        previous_close: float,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[bool, float, float]:
        """
        Simulate overnight price gap.

        Args:
            previous_close: Previous session's closing price
            rng: Random generator

        Returns:
            (gap_occurred, gap_pct, new_open):
                gap_pct as positive value (direction random)
                new_open is the post-gap opening price
        """
        rng = rng or np.random.default_rng()

        if rng.random() > self.gap_probability:
            return False, 0.0, previous_close

        # Sample gap size (lognormal: gaps are positively skewed)
        # Cap at max_gap
        raw_gap = rng.lognormal(
            mean=np.log(self.mean_gap + 1e-9),
            sigma=self.gap_std,
        )
        gap = np.clip(raw_gap, 0.0, self.max_gap)

        # Random direction (50/50 up/down)
        direction = 1 if rng.random() > 0.5 else -1
        gap_pct = direction * gap

        new_open = previous_close * (1 + gap_pct)

        return True, gap_pct, new_open

    def adjust_stop_loss_for_gaps(
        self,
        stop_price: float,
        previous_close: float,
        side: OrderSide,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[bool, float, float]:
        """
        Simulate gap through a stop-loss order.

        Args:
            stop_price: Stop-loss trigger price
            previous_close: Last close before gap
            side: Position side (BUY long or SELL short)
            rng: Random generator

        Returns:
            (stop_triggered, fill_price, slippage_bps):
                Whether stop was hit, actual fill price, slippage vs stop
        """
        rng = rng or np.random.default_rng()

        gap_occurred, gap_pct, open_price = self.simulate_gap(previous_close, rng)

        if not gap_occurred:
            return False, 0.0, 0.0

        # Did the gap trigger the stop?
        if side == OrderSide.BUY:  # Long position → stop is sell below
            # Gap down: open < stop triggers
            triggered = open_price < stop_price
            if triggered:
                # Stop order becomes market order at open
                fill_price = open_price
                slippage_bps = (stop_price - fill_price) / stop_price * 10000 if stop_price > 0 else 0.0
            else:
                fill_price = 0.0
                slippage_bps = 0.0
        else:  # Short position → stop is buy above
            triggered = open_price > stop_price
            if triggered:
                fill_price = open_price
                slippage_bps = (fill_price - stop_price) / stop_price * 10000 if stop_price > 0 else 0.0
            else:
                fill_price = 0.0
                slippage_bps = 0.0

        return triggered, fill_price, slippage_bps


class CircuitBreakerModel:
    """
    Model exchange circuit breakers (trading halts).

    Halts occur when price moves > X% within N minutes.
    Common thresholds:
      - Level 1: 7% drop in S&P 500 (15-min halt)
      - Level 2: 13% drop (15-min halt)
      - Level 3: 20% drop (halt rest of day)

    Individual stocks may have limit-up/limit-down (LULD) bands.
    """

    def __init__(
        self,
        level1_threshold_pct: float = 7.0,
        level2_threshold_pct: float = 13.0,
        level3_threshold_pct: float = 20.0,
        halt_duration_minutes: int = 15,
    ):
        """
        Args:
            level1_threshold_pct: Level 1 move threshold
            level2_threshold_pct: Level 2 threshold
            level3_threshold_pct: Level 3 threshold (halt rest of day)
            halt_duration_minutes: How long Level 1/2 halts last
        """
        self.l1 = level1_threshold_pct / 100
        self.l2 = level2_threshold_pct / 100
        self.l3 = level3_threshold_pct / 100
        self.halt_duration_minutes = halt_duration_minutes

    def check_circuit_breaker(
        self,
        price_change_pct: float,
        current_time: datetime,
        last_halt_end: Optional[datetime] = None,
    ) -> Tuple[bool, str, Optional[datetime]]:
        """
        Check if circuit breaker triggers.

        Args:
            price_change_pct: Recent price move (positive or negative)
            current_time: Current timestamp
            last_halt_end: When previous halt ended (to avoid double-counting)

        Returns:
            (halt_triggered, level, resume_time):
                level: "L1", "L2", "L3", or None
                resume_time: When trading resumes (if Level 1/2)
        """
        abs_move = abs(price_change_pct)

        if abs_move >= self.l3:
            return True, "L3", None  # Halt rest of day
        elif abs_move >= self.l2:
            resume = current_time + timedelta(minutes=self.halt_duration_minutes)
            return True, "L2", resume
        elif abs_move >= self.l1:
            resume = current_time + timedelta(minutes=self.halt_duration_minutes)
            return True, "L1", resume
        else:
            return False, "", None
