"""
Transaction Cost Analysis (TCA).

Analyzes true cost of trades broken down into:
- Explicit costs: commissions, fees, taxes
- Implicit costs: slippage, bid-ask spread, market impact, timing cost

Generates TransactionCostReport for post-trade analysis and compliance.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    Fill,
    ExecutionReport,
    TransactionCostReport,
    OrderSide,
)
from quantumtrade.adapters.execution.cost_models import (
    SpreadCostModel,
    calculate_implementation_shortfall,
    calculate_total_implicit_cost,
)


class TransactionCostAnalyzer:
    """
    Analyzes transaction costs for executed orders.
    
    Computes comprehensive cost breakdown from fills, market data, and benchmarks.
    """
    
    def __init__(
        self,
        benchmark: str = "arrival",
        spread_model: str = "mid",
        include_volatility_cost: bool = False,
    ):
        """
        Initialize TCA engine.
        
        Args:
            benchmark: Which benchmark to use for cost calculation
                "arrival" — order arrival mid price
                "vwap" — volume-weighted avg during execution
                "twap" — time-weighted avg
                "pre_mid" — pre-trade midpoint
            spread_model: How to compute spread cost
                "mid" — mid price
                "arrival" — arrival mid
            include_volatility_cost: Include opportunity cost of timing risk
        """
        self.benchmark_type = benchmark
        self.spread_model = spread_model
        self.include_volatility_cost = include_volatility_cost
        self.spread_calculator = SpreadCostModel()
    
    def analyze_execution(
        self,
        order: BrokerOrder,
        fills: List[Fill],
        market_data: pd.DataFrame,
        pre_trade_benchmark: Optional[float] = None,
        post_trade_benchmark: Optional[float] = None,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        avg_daily_volume: Optional[float] = None,
        participation_rate: Optional[float] = None,
    ) -> TransactionCostReport:
        """
        Perform full TCA on an executed order.
        
        Args:
            order: Original order
            fills: List of fills
            market_data: Price data around execution period (DataFrame)
            pre_trade_benchmark: Pre-trade benchmark price
            post_trade_benchmark: Post-trade benchmark price (for permanent impact)
            bid_price: Bid price at arrival
            ask_price: Ask price at arrival
            avg_daily_volume: Average daily volume (for participation calc)
            participation_rate: Actual participation rate (set if known)
            
        Returns:
            TransactionCostReport with full cost breakdown
        """
        if not fills:
            return self._empty_report(order)
        
        # Compute weighted average fill price
        total_qty = sum(f.quantity for f in fills)
        total_notional = sum(f.quantity * f.price for f in fills)
        avg_fill_price = total_notional / total_qty if total_qty > 0 else 0.0
        
        # Determine arrival/benchmark prices
        arrival_price = order.arrival_price or pre_trade_benchmark or market_data["open"].iloc[0]
        if not pre_trade_benchmark:
            pre_trade_benchmark = arrival_price
        
        if not post_trade_benchmark:
            # Use last close
            post_trade_benchmark = market_data["close"].iloc[-1]
        
        if not bid_price:
            bid_price = market_data.get("bid", arrival_price - 0.01).iloc[0] if "bid" in market_data else arrival_price * 0.9995
        if not ask_price:
            ask_price = market_data.get("ask", arrival_price + 0.01).iloc[0] if "ask" in market_data else arrival_price * 1.0005
        
        # Explicit costs
        explicit_commission = sum(f.commission for f in fills)
        explicit_fees = sum(f.fees for f in fills)
        explicit_total = explicit_commission + explicit_fees
        explicit_bps = (explicit_total / total_notional) * 10000 if total_notional > 0 else 0.0
        
        # Implicit costs
        
        # 1. Slippage
        slippage_dollars, slippage_bps = self.calculate_slippage(
            side=order.side,
            arrival_price=arrival_price,
            avg_fill_price=avg_fill_price,
            quantity=total_qty,
        )
        
        # 2. Spread cost
        spread_cost_dollars = self._calculate_spread_cost_dollars(
            side=order.side,
            fill_prices=[f.price for f in fills],
            quantities=[f.quantity for f in fills],
            bid_price=bid_price,
            ask_price=ask_price,
        )
        spread_cost_bps = (spread_cost_dollars / total_notional) * 10000 if total_notional > 0 else 0.0
        
        # 3. Market impact (permanent)
        impact_dollars, impact_bps = self._calculate_market_impact(
            side=order.side,
            arrival_price=arrival_price,
            post_trade_price=post_trade_benchmark,
            quantity=total_qty,
            avg_daily_volume=avg_daily_volume,
        )
        
        # 4. Implementation shortfall (aggregate)
        is_result = calculate_implementation_shortfall(
            arrival_price=arrival_price,
            average_fill_price=avg_fill_price,
            side=order.side,
            quantity=total_qty,
        )
        is_dollars = is_result["shortfall_dollars"]
        is_bps = is_result["shortfall_bps"]
        
        # Total implicit
        total_implicit = slippage_dollars + spread_cost_dollars + impact_dollars
        total_implicit_bps = slippage_bps + spread_cost_bps + impact_bps
        
        # Total
        total_cost = explicit_total + total_implicit
        total_cost_bps = explicit_bps + total_implicit_bps
        
        # Timing metrics
        first_fill = min(f.trade_timestamp for f in fills)
        last_fill = max(f.trade_timestamp for f in fills)
        duration_secs = (last_fill - first_fill).total_seconds() if fills else 0
        
        return TransactionCostReport(
            # identifiers
            order_id=order.order_id or "",
            symbol=order.symbol,
            side=order.side,
            strategy=order.strategy,
            # order parameters
            order_quantity=order.quantity,
            order_type=order.order_type,
            algorithm=order.algorithm,
            # market data
            arrival_price=arrival_price,
            pre_trade_benchmark=pre_trade_benchmark,
            post_trade_benchmark=post_trade_benchmark,
            bid_price=bid_price,
            ask_price=ask_price,
            # execution
            filled_quantity=total_qty,
            weighted_avg_price=avg_fill_price,
            total_notional=total_notional,
            # explicit costs
            explicit_commission=explicit_commission,
            explicit_fees=explicit_fees,
            explicit_cost_bps=explicit_bps,
            # implicit costs
            implicit_slippage=slippage_dollars,
            implicit_slippage_bps=slippage_bps,
            implicit_spread=spread_cost_dollars,
            implicit_spread_bps=spread_cost_bps,
            implicit_impact=impact_dollars,
            implicit_impact_bps=impact_bps,
            total_implicit_cost=total_implicit,
            total_implicit_cost_bps=total_implicit_bps,
            # aggregate
            total_cost=total_cost,
            total_cost_bps=total_cost_bps,
            # timing
            submitted_at=order.timestamp,
            first_fill_at=first_fill,
            last_fill_at=last_fill,
            execution_duration_seconds=duration_secs,
            # benchmarks
            implementation_shortfall=is_dollars,
            implementation_shortfall_bps=is_bps,
            participation_rate=participation_rate,
            # broker
            broker=order.broker or "unknown",
            child_orders_count=len(order.algo_params.get("child_orders", [])),
            fills_count=len(fills),
        )
    
    def analyze_fill(
        self,
        order: BrokerOrder,
        fill: Fill,
        expected_price: float,
        bid: float,
        ask: float,
        avg_daily_volume: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Analyze a single fill.
        
        Returns dict with slippage_bps, spread_cost_bps, impact_bps.
        """
        # Slippage
        slippage_dollars, slippage_bps = self.calculate_slippage(
            side=order.side,
            arrival_price=expected_price,
            avg_fill_price=fill.price,
            quantity=fill.quantity,
        )
        
        # Spread cost
        spread_cost_dollars = self._calculate_spread_cost_dollars(
            side=order.side,
            fill_prices=[fill.price],
            quantities=[fill.quantity],
            bid_price=bid,
            ask_price=ask,
        )
        spread_bps = (spread_cost_dollars / (fill.quantity * fill.price)) * 10000 if fill.quantity * fill.price > 0 else 0.0
        
        # Impact
        impact_dollars, impact_bps = self._calculate_market_impact(
            side=order.side,
            arrival_price=expected_price,
            post_trade_price=fill.price,  # temporary impact only
            quantity=fill.quantity,
            avg_daily_volume=avg_daily_volume,
        )
        
        return {
            "slippage_bps": slippage_bps,
            "spread_cost_bps": spread_bps,
            "impact_bps": impact_bps,
        }
    
    def calculate_slippage(
        self,
        side: OrderSide,
        arrival_price: float,
        avg_fill_price: float,
        quantity: float,
    ) -> Tuple[float, float]:
        """
        Calculate slippage cost.
        
        Slippage = (fill_price - benchmark) * quantity
        For buys: adverse means higher price
        For sells: adverse means lower price
        """
        if arrival_price <= 0:
            return 0.0, 0.0
        
        price_diff = avg_fill_price - arrival_price
        if side == OrderSide.SELL:
            price_diff = -price_diff
        
        slippage_dollars = price_diff * quantity
        slippage_bps = (price_diff / arrival_price) * 10000
        
        return slippage_dollars, slippage_bps
    
    def _calculate_spread_cost_dollars(
        self,
        side: OrderSide,
        fill_prices: List[float],
        quantities: List[float],
        bid_price: float,
        ask_price: float,
    ) -> float:
        """Calculate spread cost in dollars."""
        mid_price = (bid_price + ask_price) / 2
        
        if side == OrderSide.BUY:
            # Pay ask, ideal is mid
            spread_per_share = ask_price - mid_price
        else:
            # Receive bid, ideal is mid
            spread_per_share = mid_price - bid_price
        
        total_qty = sum(quantities)
        return spread_per_share * total_qty
    
    def _calculate_market_impact(
        self,
        side: OrderSide,
        arrival_price: float,
        post_trade_price: float,
        quantity: float,
        avg_daily_volume: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Calculate permanent market impact.
        
        Impact = (post_trade_price - arrival_price) * quantity
        Single-sided: permanent price change after the trade.
        """
        if arrival_price <= 0:
            return 0.0, 0.0
        
        price_diff = post_trade_price - arrival_price
        # For sell, negative price change is bad → flip sign
        if side == OrderSide.SELL:
            price_diff = -price_diff
        
        impact_dollars = price_diff * quantity
        impact_bps = (price_diff / arrival_price) * 10000 if arrival_price > 0 else 0.0
        
        return impact_dollars, impact_bps
    
    def _empty_report(self, order: BrokerOrder) -> TransactionCostReport:
        """Return empty report for unfilled order."""
        return TransactionCostReport(
            order_id=order.order_id or "",
            symbol=order.symbol,
            side=order.side,
            strategy=order.strategy,
            order_quantity=order.quantity,
            order_type=order.order_type,
            algorithm=order.algorithm,
            arrival_price=order.arrival_price or 0.0,
            pre_trade_benchmark=0.0,
            post_trade_benchmark=0.0,
            bid_price=0.0,
            ask_price=0.0,
            filled_quantity=0.0,
            weighted_avg_price=0.0,
            total_notional=0.0,
            explicit_commission=0.0,
            explicit_fees=0.0,
            explicit_cost_bps=0.0,
            implicit_slippage=0.0,
            implicit_slippage_bps=0.0,
            implicit_spread=0.0,
            implicit_spread_bps=0.0,
            implicit_impact=0.0,
            implicit_impact_bps=0.0,
            total_implicit_cost=0.0,
            total_implicit_cost_bps=0.0,
            total_cost=0.0,
            total_cost_bps=0.0,
            submitted_at=order.timestamp,
            first_fill_at=None,
            last_fill_at=None,
            execution_duration_seconds=None,
            implementation_shortfall=0.0,
            implementation_shortfall_bps=0.0,
            participation_rate=None,
            broker=order.broker or "unknown",
            child_orders_count=0,
            fills_count=0,
        )
    
    def compare_algorithms(
        self,
        orders: List[BrokerOrder],
        all_fills: Dict[str, List[Fill]],
        market_data: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Compare TCA metrics across multiple algorithm runs.
        
        Returns DataFrame with cost metrics for comparison.
        """
        results = []
        
        for order in orders:
            fills = all_fills.get(order.order_id, [])
            md = market_data.get(order.symbol, pd.DataFrame())
            report = self.analyze_execution(order, fills, md)
            
            results.append({
                "order_id": order.order_id,
                "symbol": order.symbol,
                "algorithm": order.algorithm.value,
                "quantity": order.quantity,
                "total_cost_bps": report.total_cost_bps,
                "explicit_bps": report.explicit_cost_bps,
                "slippage_bps": report.implicit_slippage_bps,
                "spread_bps": report.implicit_spread_bps,
                "impact_bps": report.implicit_impact_bps,
                "implementation_shortfall_bps": report.implementation_shortfall_bps,
                "execution_duration_secs": report.execution_duration_seconds,
                "fill_rate_pct": report.fills_count / max(1, order.quantity / 100) * 100,
            })
        
        return pd.DataFrame(results)
