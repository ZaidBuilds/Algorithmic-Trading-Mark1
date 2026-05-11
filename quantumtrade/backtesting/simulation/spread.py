"""
Bid-ask spread cost modeling.

Market orders pay the spread:
- Buy at ask (higher than mid)
- Sell at bid (lower than mid)

Spread cost = (fill_price - mid_price) for buys
            = (mid_price - fill_price) for sells

For limit orders: may miss spread if not filled, but when filled
often receive price improvement (trade inside spread).
"""

from typing import Optional, Tuple
import numpy as np

from quantumtrade.adapters.execution.models import OrderSide, OrderType


class SpreadCostModel:
    """
    Model bid-ask spread costs for market and limit orders.

    For market orders: guaranteed spread payment (fill at worst price).
    For limit orders: probabilistic spread capture (may get price improvement).
    """

    def __init__(
        self,
        default_spread_bps: float = 1.0,
        limit_order_price_improvement_bps: float = 0.5,
    ):
        """
        Args:
            default_spread_bps: Default spread when order book unavailable
            limit_order_price_improvement_bps: Avg improvement for limit fills
        """
        self.default_spread_bps = default_spread_bps
        self.limit_improvement_bps = limit_order_price_improvement_bps

    def calculate_spread_cost(
        self,
        side: OrderSide,
        fill_price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET,
    ) -> Tuple[float, float]:
        """
        Compute spread cost in basis points.

        Args:
            side: Order side
            fill_price: Actual execution price
            bid_price: Current bid (best bid)
            ask_price: Current ask (best ask)
            order_type: MARKET or LIMIT (affects cost calculation)

        Returns:
            (spread_cost_bps, spread_cost_dollars)
                spread_cost_bps is always positive = cost amount
        """
        # If no order book, infer mid from fill_price if we know spread
        if bid_price is None or ask_price is None:
            # Assume symmetric spread around fill_price
            half_spread_bps = self.default_spread_bps / 2
            mid_price = fill_price / (1 + half_spread_bps / 10000) if side == OrderSide.BUY else fill_price / (1 - half_spread_bps / 10000)
            bid_price = mid_price * (1 - half_spread_bps / 10000)
            ask_price = mid_price * (1 + half_spread_bps / 10000)

        mid_price = (bid_price + ask_price) / 2

        if mid_price <= 0:
            return 0.0, 0.0

        if order_type == OrderType.LIMIT:
            # Limit orders often get price improvement
            if side == OrderSide.BUY:
                # Buy limit: we set max price, may fill at or below limit
                # Assume improvement: fill at mid or better
                effective_price = min(fill_price, mid_price)
                spread_cost_bps = max(0.0, (ask_price - effective_price) / mid_price * 10000)
            else:
                # Sell limit: we set min price, may fill at or above limit
                effective_price = max(fill_price, mid_price)
                spread_cost_bps = max(0.0, (effective_price - bid_price) / mid_price * 10000)
        else:
            # Market orders: buy at ask, sell at bid
            if side == OrderSide.BUY:
                spread_cost_bps = (ask_price - mid_price) / mid_price * 10000
            else:
                spread_cost_bps = (mid_price - bid_price) / mid_price * 10000

        spread_cost_dollars = abs(fill_price - mid_price) * (
            # Quantity not known here; caller will scale
        )

        return spread_cost_bps, 0.0  # Dollar amount computed by caller with quantity

    def get_mid_price(
        self,
        bid: Optional[float],
        ask: Optional[float],
        last_price: Optional[float] = None,
    ) -> float:
        """
        Get mid price from bid/ask, with fallback.

        Args:
            bid: Bid price
            ask: Ask price
            last_price: Last traded price (fallback)

        Returns:
            Mid price or best available estimate
        """
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        elif bid is not None:
            return bid
        elif ask is not None:
            return ask
        elif last_price is not None:
            return last_price
        else:
            raise ValueError("No price data available")

    def estimate_spread_bps(
        self,
        symbol: str,
        exchange: str = "default",
        asset_type: str = "stock",
    ) -> float:
        """
        Estimate typical spread for a given instrument.

        This is a heuristic based on typical market conditions:
        - Large-cap US equities: 0.5–2 bps
        - Small caps: 2–10 bps
        - Crypto: 5–50 bps (depending on pair)
        - Forex: 0.1–2 bps (major pairs)

        Args:
            symbol: Trading symbol (e.g., "AAPL", "BTC-USDT")
            exchange: Exchange name
            asset_type: "stock", "crypto", "forex"

        Returns:
            Estimated spread in basis points
        """
        # Rough heuristics
        asset_type = asset_type.lower()

        if asset_type == "stock":
            # Large cap defaults to 1 bps
            return 1.0
        elif asset_type == "crypto":
            # Crypto typically wider spread
            return 20.0
        elif asset_type == "forex":
            # Major pairs very tight
            return 0.5
        else:
            return self.default_spread_bps


class OrderBookSpreadModel:
    """
    Model spread using order book depth.

    Considers the full L2 order book rather than just top-of-book.
    Useful for large orders where average spread paid depends on
    how quickly you consume the order book.
    """

    def __init__(
        self,
        base_spread_bps: float = 1.0,
        depth_penalty_factor: float = 2.0,
    ):
        """
        Args:
            base_spread_bps: Top-of-book spread in bps
            depth_penalty_factor: How much spread widens as you go deeper
                1.0 = spread constant, 2.0 = spread doubles at each level
        """
        self.base_spread = base_spread_bps
        self.depth_factor = depth_penalty_factor

    def calculate_average_spread_for_quantity(
        self,
        side: OrderSide,
        quantity: float,
        order_book: dict,
    ) -> Tuple[float, float]:
        """
        Compute average spread cost for filling a given quantity.

        Walks the order book to determine average execution price.

        Args:
            side: BUY or SELL
            quantity: Total quantity to fill
            order_book: Order book dict with 'bids' and 'asks' lists
                Each list contains {'price': float, 'size': float}

        Returns:
            (avg_spread_bps, avg_fill_price)
        """
        if side == OrderSide.BUY:
            levels = order_book.get("asks", [])
        else:
            levels = order_book.get("bids", [])

        if not levels:
            return self.base_spread, 0.0

        remaining = quantity
        total_notional = 0.0
        mid_price = (order_book.get("bid_price", levels[0]["price"]) +
                     order_book.get("ask_price", levels[0]["price"])) / 2

        for level in levels:
            level_size = level.get("size", 0)
            level_price = level.get("price", 0)

            if remaining <= 0:
                break

            filled = min(remaining, level_size)
            total_notional += filled * level_price
            remaining -= filled

        if quantity - remaining <= 0:
            # Couldn't fill anything
            return self.base_spread, mid_price

        avg_fill_price = total_notional / (quantity - remaining)

        # Spread cost vs mid
        if side == OrderSide.BUY:
            spread_cost_per_share = avg_fill_price - mid_price
        else:
            spread_cost_per_share = mid_price - avg_fill_price

        spread_cost_bps = (spread_cost_per_share / mid_price) * 10000 if mid_price > 0 else 0.0

        return max(0.0, spread_cost_bps), avg_fill_price
