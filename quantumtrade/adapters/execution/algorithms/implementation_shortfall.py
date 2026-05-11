"""
Implementation Shortfall (Almgren-Chriss) Algorithm.

Optimizes the trade-off between market impact (large immediate orders)
and timing risk (holding over time). Uses closed-form solution of Almgren-Chriss
to schedule optimal liquidation path.

Minimizes: E[Impact Cost] + λ * Var[Timing Risk]

Best for: accurate price target fulfillment; risk-averse execution
"""

from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict
import math
import numpy as np

from quantumtrade.adapters.execution.models import BrokerOrder, ChildOrder, OrderSide
from quantumtrade.adapters.execution.algorithms.base import OrderAlgorithm


class ImplementationShortfallAlgorithm(OrderAlgorithm):
    """
    Implementation Shortfall / Optimal Execution algorithm.
    
    Based on Almgren-Chriss model for optimal order execution.
    
    Parameters:
        risk_aversion: λ parameter — higher means more urgent, front-loaded
            (typical range: 0.0001 to 0.01)
        urgency: Time horizon multiplier
        market_impact_coeff: Permanent impact coefficient η
        temporary_impact_coeff: Temporary impact coefficient ε
        volatility: Expected price volatility (per period)
    """
    
    def __init__(
        self,
        data_client=None,
        risk_aversion: float = 0.001,
        urgency: float = 1.0,
        market_impact_coeff: float = 0.1,
        temporary_impact_coeff: float = 0.05,
        volatility: float = 0.02,
        num_periods: int = 10,
    ):
        super().__init__(name="ImplementationShortfall", data_client=data_client)
        self.risk_aversion = risk_aversion
        self.urgency = urgency
        self.impact_coeff = market_impact_coeff
        self.temp_impact_coeff = temporary_impact_coeff
        self.annual_vol = volatility
        self.num_periods = num_periods
    
    def generate_schedule(
        self,
        order: BrokerOrder,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        **params
    ) -> List[ChildOrder]:
        """
        Generate optimal liquidation schedule using Almgren-Chriss.
        
        Args:
            order: Parent order (assumed to be closing/liquidating)
            start_time: Execution start
            end_time: Execution horizon
            **params: Override risk_aversion, urgency, num_periods
            
        Returns:
            List of child orders with optimal sizes
        """
        self.initialize(order)
        
        risk_aversion = params.get("risk_aversion", self.risk_aversion)
        urgency = params.get("urgency", self.urgency)
        num_periods = params.get("num_periods", self.num_periods)
        
        if end_time is None:
            end_time = start_time + timedelta(minutes=60)
        
        # Time between periods
        total_seconds = (end_time - start_time).total_seconds()
        tau = total_seconds / num_periods  # seconds per period
        
        # Volatility per period
        daily_vol = self.annual_vol / np.sqrt(252)
        seconds_in_day = 24 * 3600
        sigma = daily_vol * np.sqrt(tau / seconds_in_day)
        
        # Almgren-Chriss optimal trading trajectory
        # x_k = X * sinh(α (T - t_k)) / sinh(α T)  for buys
        # For sells: q_k = X * sinh(α t_k) / sinh(α T)
        # where α = sqrt(λ * σ² / η)
        
        eta = self.impact_coeff
        epsilon = self.temp_impact_coeff
        
        # risk aversion adjusted
        alpha = np.sqrt(risk_aversion * sigma**2 / eta)
        T = num_periods
        
        children = []
        X = order.quantity
        
        for k in range(1, num_periods + 1):
            # t_k in periods (1..T)
            # Sell algorithm: sell most early
            if order.is_sell:
                fraction = math.sinh(alpha * (T - k + 1)) / math.sinh(alpha * T)
                # Alternate: linear decay might be simpler, but here:
                qty = X * (1 - fraction)
            else:
                # Buy algorithm: buy most early
                fraction = math.sinh(alpha * (T - k + 1)) / math.sinh(alpha * T)
                qty = X * fraction
            
            # Round to integer if applicable
            if X == int(X):
                qty = int(qty)
            
            # Adjust schedule to ensure total = X
            if k == num_periods:
                qty = X - sum(c.quantity for c in children)
            
            scheduled_time = start_time + timedelta(seconds=tau * (k - 1))
            
            child = ChildOrder(
                quantity=max(0, qty),
                scheduled_time=scheduled_time,
                order_type=order.order_type,
                parent_order_id=order.order_id or "",
                slice_number=k,
                total_slices=num_periods,
                child_order_id=f"{order.order_id or 'is'}_child_{k}",
            )
            children.append(child)
            self.child_orders.append(child)
        
        # Rebalance if drift
        total = sum(c.quantity for c in children)
        if abs(total - X) > 0.001:
            if children:
                children[-1].quantity += (X - total)
        
        return children
    
    def get_optimal_risk_aversion(
        self,
        urgency: float = 1.0,
        horizon_days: float = 1.0,
        volatility: float = 0.02,
        market_impact: float = 0.1,
    ) -> float:
        """
        Compute optimal risk aversion λ from urgency.
        
        λ = Urgency / (Var * T)
        """
        T = horizon_days
        sigma_sq = volatility ** 2 * T
        lam = urgency / sigma_sq if sigma_sq > 0 else 0.001
        return lam
    
    def get_statistics(self) -> Dict[str, Any]:
        stats = super().get_statistics()
        stats.update({
            "algorithm": self.name,
            "risk_aversion": self.risk_aversion,
            "urgency": self.urgency,
            "market_impact_coeff": self.impact_coeff,
            "temporary_impact_coeff": self.temp_impact_coeff,
            "volatility": self.annual_vol,
            "num_periods": self.num_periods,
        })
        return stats
