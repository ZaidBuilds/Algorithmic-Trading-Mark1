"""
Unified market simulator — orchestrates all execution cost components.

The MarketSimulator is the main entry point for realistic fill simulation.
It combines:
- Slippage models (fixed, volume-based, Almgren-Chriss)
- Latency (execution delay with price movement)
- Spread costs (bid-ask)
- Market impact (permanent + temporary)
- Liquidity constraints (partial fills, order book depth)
- Gap risk (overnight moves, limit moves)

Simulation flow for a single order:
  1. Check liquidity constraints → determine fill quantity
  2. Apply spread cost (buy at ask, sell at bid) → base fill price
  3. Add slippage (order size → price impact)
  4. Apply latency-induced price shift (price moved during delay)
  5. Add market impact (permanent & temporary)
  6. Apply gap adjustment if crossing sessions
  7. Return Fill with full cost breakdown
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import numpy as np
import pandas as pd

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    Fill,
    OrderSide,
    OrderType,
)
from .slippage import (
    BaseSlippageModel,
    FixedSlippageModel,
    VolumeBasedSlippageModel,
    SquareRootSlippageModel,
    AlmgrenChrissSlippageModel,
    create_slippage_model,
)
from .latency import LatencyModel
from .spread import SpreadCostModel, OrderBookSpreadModel
from .market_impact import AlmgrenChrissImpact, ImpactCalibrator
from .liquidity import LiquidityModel, LimitOrderFillModel, GapRiskModel, CircuitBreakerModel


class MarketFill:
    """
    Rich fill object with full cost breakdown.

    Extends the base Fill model with simulation metadata.
    """

    def __init__(
        self,
        base_fill: Fill,
        *,
        slippage_bps: float = 0.0,
        spread_cost_bps: float = 0.0,
        impact_bps: float = 0.0,
        latency_ms: float = 0.0,
        partial: bool = False,
        gap_adjustment: bool = False,
        order_book_used: bool = False,
        simulation_details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize market fill with extended attributes.

        Args:
            base_fill: Underlying Fill object
            slippage_bps: Slippage cost in basis points
            spread_cost_bps: Spread cost in basis points
            impact_bps: Market impact cost in basis points
            latency_ms: Latency incurred
            partial: Was this a partial fill?
            gap_adjustment: Did overnight gap affect price?
            order_book_used: Was order book data used?
            simulation_details: Arbitrary debug info (optional)
        """
        self.fill = base_fill
        self.slippage_bps = slippage_bps
        self.spread_cost_bps = spread_cost_bps
        self.impact_bps = impact_bps
        self.latency_ms = latency_ms
        self.partial = partial
        self.gap_adjustment = gap_adjustment
        self.order_book_used = order_book_used
        self.simulation_details = simulation_details or {}

    @property
    def price(self) -> float:
        return self.fill.price

    @property
    def quantity(self) -> float:
        return self.fill.quantity

    @property
    def notional_value(self) -> float:
        return self.fill.notional_value

    @property
    def total_implicit_cost_bps(self) -> float:
        """Total implicit cost (slippage + spread + impact)."""
        return self.slippage_bps + self.spread_cost_bps + self.impact_bps

    @property
    def total_implicit_cost_dollars(self) -> float:
        """Total implicit cost in dollars."""
        return self.notional_value * self.total_implicit_cost_bps / 10000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            **self.fill.to_dict(),
            "slippage_bps": self.slippage_bps,
            "spread_cost_bps": self.spread_cost_bps,
            "impact_bps": self.impact_bps,
            "latency_ms": self.latency_ms,
            "partial": self.partial,
            "gap_adjustment": self.gap_adjustment,
            "order_book_used": self.order_book_used,
            "total_implicit_cost_bps": self.total_implicit_cost_bps,
            "total_implicit_cost_dollars": self.total_implicit_cost_dollars,
        }


class MarketSimulator:
    """
    Unified market simulator for backtesting execution.

    Simulates realistic order fills with:
    - Multiple slippage models
    - Latency simulation
    - Spread costs
    - Market impact (permanent + temporary)
    - Liquidity constraints
    - Gap risk
    - Circuit breakers

    Usage:
        simulator = MarketSimulator(
            slippage_model="impact",
            latency_ms=150,
            spread_bps=1.0,
            enable_impact=True,
        )
        fill = simulator.simulate_fill(order, bar, order_book, adv)
    """

    def __init__(
        self,
        slippage_model: str = "volume",
        fixed_slippage_bps: float = 1.0,
        latency_ms: float = 150.0,
        spread_bps: float = 1.0,
        enable_impact: bool = False,
        impact_eta: float = 0.01,
        impact_epsilon: float = 0.05,
        participation_rate: float = 0.10,
        min_fill_quantity: float = 1.0,
        enable_liquidity_constraints: bool = False,
        enable_gap_risk: bool = True,
        enable_circuit_breakers: bool = False,
        seed: Optional[int] = None,
    ):
        """
        Initialize market simulator.

        Args:
            slippage_model: "fixed", "volume", "sqrt", or "impact"
            fixed_slippage_bps: For fixed model
            latency_ms: Mean execution latency (ms)
            spread_bps: Bid-ask spread in basis points
            enable_impact: Enable market impact model
            impact_eta: Permanent impact coefficient
            impact_epsilon: Temporary impact coefficient
            participation_rate: Max % of bar volume to consume
            min_fill_quantity: Minimum qty for a fill event
            enable_liquidity_constraints: Respect volume limits / partial fills
            enable_gap_risk: Model overnight gaps
            enable_circuit_breakers: Model trading halts
            seed: Random seed for reproducibility
        """
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        # Slippage model
        slippage_kwargs = {
            "fixed_slippage_bps": fixed_slippage_bps,
            "impact_eta": impact_eta,
            "impact_epsilon": impact_epsilon,
        }
        self.slippage_model = create_slippage_model(slippage_model, **slippage_kwargs)

        # Latency model
        self.latency_model = LatencyModel(mean_latency_ms=latency_ms)

        # Spread model
        self.spread_model = SpreadCostModel(default_spread_bps=spread_bps)
        self.order_book_spread_model = OrderBookSpreadModel(base_spread_bps=spread_bps)

        # Impact model (separate from slippage — for permanent component)
        self.impact_model = AlmgrenChrissImpact(
            eta=impact_eta,
            epsilon=impact_epsilon,
        )

        # Liquidity
        self.liquidity_model = LiquidityModel(
            participation_rate=participation_rate,
            min_fill_quantity=min_fill_quantity,
            allow_partial_fills=enable_liquidity_constraints,
        )
        self.limit_order_model = LimitOrderFillModel()

        # Gap risk
        self.gap_model = GapRiskModel() if enable_gap_risk else None

        # Circuit breaker
        self.circuit_breaker = CircuitBreakerModel() if enable_circuit_breakers else None

        # Feature flags
        self.enable_liquidity_constraints = enable_liquidity_constraints
        self.enable_gap_risk = enable_gap_risk
        self.enable_circuit_breakers = enable_circuit_breakers

        # State
        self.last_latency_ms: float = 0.0
        self.last_gap_occurred: bool = False

    def simulate_fill(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]] = None,
        avg_daily_volume: Optional[float] = None,
        volatility: Optional[float] = None,
        previous_close: Optional[float] = None,
        is_gap: bool = False,
        rng: Optional[np.random.Generator] = None,
    ) -> Optional[MarketFill]:
        """
        Simulate order fill for a single bar/tick.

        Args:
            order: The order to execute
            bar: OHLCV bar dict with keys: open, high, low, close, volume, timestamp
            order_book: Optional order book (bid, ask, bid_size, ask_size, levels...)
            avg_daily_volume: ADV for volume-based models
            volatility: Annualized volatility for latency price shift
            previous_close: Previous close (for gap detection)
            is_gap: True if this bar follows a gap (overnight)
            rng: Optional random generator

        Returns:
            MarketFill object if fill occurs, None if unfilled
        """
        rng = rng or self.rng

        # 1. Check order type constraints (limit orders)
        if order.order_type == OrderType.LIMIT:
            return self._simulate_limit_order(order, bar, order_book, rng)

        # 2. Liquidity check — determine if and how much fills
        remaining = order.remaining_quantity
        if remaining <= 0:
            return None

        bar_volume = bar.get("volume", 0)
        order_book_depth = self._extract_order_book_depth(order, order_book)

        fill_qty, is_partial = self.liquidity_model.determine_fill_quantity(
            order_quantity=order.quantity,
            bar_volume=bar_volume,
            order_book_depth=order_book_depth,
            remaining_quantity=remaining,
        )

        if fill_qty <= 0:
            return None  # No fill this bar

        # 3. Determine base price (with order book if available)
        base_price, mid_price = self._determine_base_price(order, bar, order_book)

        # 4. Apply spread cost
        spread_cost_bps = 0.0
        if order_book:
            spread_cost_bps, _ = self.order_book_spread_model.calculate_average_spread_for_quantity(
                side=order.side,
                quantity=fill_qty,
                order_book=order_book,
            )
        else:
            spread_cost_bps, _ = self.spread_model.calculate_spread_cost(
                side=order.side,
                fill_price=base_price,
                bid_price=bar.get("bid", base_price * 0.9995),
                ask_price=bar.get("ask", base_price * 1.0005),
                order_type=order.order_type,
            )

        # Adjust base price for spread (buy at ask, sell at bid)
        spread_bps_half = spread_cost_bps / 2  # roughly half-spread
        if order.is_buy:
            base_price *= (1 + spread_bps_half / 10000)
        else:
            base_price *= (1 - spread_bps_half / 10000)

        # 5. Sample latency and apply price shift
        latency_ms = self.latency_model.sample_latency(rng)
        self.last_latency_ms = latency_ms

        if volatility is not None and latency_ms > 0:
            shifted_price = self.latency_model.calculate_price_shift(
                latency_ms=latency_ms,
                volatility=volatility,
                current_price=base_price,
                side=order.side,
            )
        else:
            shifted_price = base_price

        # 6. Calculate slippage (excluding spread already applied)
        slippage_bps = self.slippage_model.calculate_slippage_bps(
            side=order.side,
            quantity=fill_qty,
            price=mid_price or base_price,
            avg_daily_volume=avg_daily_volume,
            volatility=volatility,
        )

        # Apply slippage to shifted price
        if order.is_buy:
            fill_price = shifted_price * (1 + slippage_bps / 10000)
        else:
            fill_price = shifted_price * (1 - slippage_bps / 10000)

        # 7. Market impact (permanent price change due to trade itself)
        impact_bps = 0.0
        if self.enable_impact and avg_daily_volume:
            impact_result = self.impact_model.calculate_impact(
                side=order.side,
                order_quantity=fill_qty,
                avg_daily_volume=avg_daily_volume,
                price=fill_price,
            )
            impact_bps = impact_result["total_bps"]

            # Temporary impact affects fill price
            if order.is_buy:
                fill_price *= (1 + impact_bps / 10000)
            else:
                fill_price *= (1 - impact_bps / 10000)

        # 8. Gap adjustment (overnight)
        gap_adjusted = False
        if self.enable_gap_risk and is_gap and previous_close is not None:
            # Gap already happened; we assume fill at new open
            # For simulation, we blend: fill_price reflects gap but not further move
            # In practice, gap orders fill at opening price with uncertainty
            gap_adjusted = True
            # Don't override fill_price here; gap is handled at bar level

        # 9. Circuit breaker check
        if self.enable_circuit_breakers:
            # We'd need price change from previous bar → handle at engine level
            pass

        # 10. Create fill object
        fill_id = f"sim_{order.order_id or 'order'}_{datetime.now().timestamp()}"
        fill_timestamp = bar.get("timestamp", datetime.now())
        if isinstance(fill_timestamp, (int, float)):
            fill_timestamp = datetime.fromtimestamp(fill_timestamp / 1000)

        fill = Fill(
            fill_id=fill_id,
            order_id=order.order_id or "",
            symbol=order.symbol,
            side=order.side,
            quantity=fill_qty,
            price=fill_price,
            trade_timestamp=fill_timestamp,
            received_timestamp=fill_timestamp,
            broker=order.broker or "MarketSimulator",
        )

        market_fill = MarketFill(
            base_fill=fill,
            slippage_bps=slippage_bps,
            spread_cost_bps=spread_cost_bps,
            impact_bps=impact_bps,
            latency_ms=latency_ms,
            partial=is_partial,
            gap_adjustment=gap_adjusted,
            order_book_used=order_book is not None,
            simulation_details={
                "base_price": base_price,
                "mid_price": mid_price or base_price,
                "adv": avg_daily_volume,
                "volatility": volatility,
                "fill_qty": fill_qty,
                "remaining_after": remaining - fill_qty,
            },
        )

        return market_fill

    def _simulate_limit_order(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]],
        rng: np.random.Generator,
    ) -> Optional[MarketFill]:
        """Handle limit order fill simulation."""
        if order.limit_price is None:
            return None

        high = bar.get("high", bar.get("close"))
        low = bar.get("low", bar.get("close"))
        volume = bar.get("volume", 0)

        filled, fill_price = self.limit_order_model.simulate_limit_fill(
            side=order.side,
            limit_price=order.limit_price,
            high_price=high,
            low_price=low,
            volume=volume,
            rng=rng,
        )

        if not filled:
            return None

        # Limit orders get price improvement
        spread_cost_bps = 0.0  # Often negative (improvement)

        fill_id = f"lim_{order.order_id or 'order'}_{datetime.now().timestamp()}"
        fill_timestamp = bar.get("timestamp", datetime.now())
        if isinstance(fill_timestamp, (int, float)):
            fill_timestamp = datetime.fromtimestamp(fill_timestamp / 1000)

        fill = Fill(
            fill_id=fill_id,
            order_id=order.order_id or "",
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,  # Limit fills typically full
            price=fill_price,
            trade_timestamp=fill_timestamp,
            received_timestamp=fill_timestamp,
            broker=order.broker or "MarketSimulator",
        )

        return MarketFill(
            base_fill=fill,
            slippage_bps=0.0,  # No slippage, may even have negative
            spread_cost_bps=spread_cost_bps,
            impact_bps=0.0,
            latency_ms=0.0,
            partial=False,
            gap_adjustment=False,
            order_book_used=order_book is not None,
        )

    def _determine_base_price(
        self,
        order: BrokerOrder,
        bar: Dict[str, Any],
        order_book: Optional[Dict[str, Any]],
    ) -> Tuple[float, Optional[float]]:
        """
        Determine base execution price and reference mid price.

        Returns:
            (base_price, mid_price)
        """
        if order_book:
            bid = order_book.get("bid")
            ask = order_book.get("ask")
            if bid is not None and ask is not None:
                mid = (bid + ask) / 2
                if order.is_buy:
                    base = ask
                else:
                    base = bid
                return base, mid

        # Fall back to bar data
        close = bar.get("close", 0)
        # Estimate mid from typical spread if we know spread_bps
        bid = bar.get("bid", close * 0.9995)
        ask = bar.get("ask", close * 1.0005)
        mid = (bid + ask) / 2 if bid != ask else close
        base = ask if order.is_buy else bid

        return base or close, mid

    def _extract_order_book_depth(
        self,
        order: BrokerOrder,
        order_book: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        """Extract available liquidity at best price from order book."""
        if not order_book:
            return None

        if order.is_buy:
            depth = order_book.get("ask_size", 0)
        else:
            depth = order_book.get("bid_size", 0)

        return depth if depth and depth > 0 else None

    def calculate_total_cost_bps(
        self,
        order: BrokerOrder,
        fill: MarketFill,
        pre_trade_mid: float,
        post_trade_mid: Optional[float] = None,
    ) -> float:
        """
        Calculate total implicit cost in basis points.

        Args:
            order: Original order
            fill: MarketFill result
            pre_trade_mid: Mid price before order
            post_trade_mid: Mid price after order (for permanent impact)

        Returns:
            Total cost in basis points
        """
        if pre_trade_mid <= 0:
            return 0.0

        # Cost from fill price vs arrival mid
        if order.is_buy:
            adverse_move = fill.price - pre_trade_mid
        else:
            adverse_move = pre_trade_mid - fill.price

        cost_bps = (adverse_move / pre_trade_mid) * 10000

        return cost_bps
