"""
Percentage of Volume (POV) Algorithm.

Adaptive algorithm that targets a fixed percentage of the market's volume
as it occurs. If volume spikes, order scales up; if volume dries up, order scales down.
Good for hiding order size and participating opportunistically.

Best for: large orders in liquid markets, minimizing footprint, adaptive participation.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict
import random

from quantumtrade.adapters.execution.models import BrokerOrder, ChildOrder
from quantumtrade.adapters.execution.algorithms.base import OrderAlgorithm


class POVAlgorithm(OrderAlgorithm):
    """
    Percentage of Volume execution algorithm.
    
    Places orders sized as a percentage of the observed (or anticipated) volume.
    The algorithm continuously adapts to market volume.
    
    Parameters:
        participation_rate: Target participation rate (e.g., 0.10 = 10% of volume)
        min_slice_size: Minimum child order size
        max_slice_size: Maximum child order size
        lookahead_minutes: How far ahead to anticipate volume (for scheduling)
    """
    
    def __init__(
        self,
        data_client=None,
        participation_rate: float = 0.10,
        min_slice_size: float = 100,
        max_slice_size: float = 10000,
        lookahead_minutes: int = 5,
    ):
        super().__init__(name="POV", data_client=data_client)
        self.participation_rate = participation_rate
        self.min_slice_size = min_slice_size
        self.max_slice_size = max_slice_size
        self.lookahead_minutes = lookahead_minutes
    
    def generate_schedule(
        self,
        order: BrokerOrder,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        **params
    ) -> List[ChildOrder]:
        """
        Generate POV schedule.
        
        Since POV depends on real-time volume, the initial schedule is approximate.
        Child orders are sized based on volume profile, but actual quantities
        may be adjusted dynamically during execution.
        
        Args:
            order: Parent order
            start_time: Start of execution window
            end_time: End of execution window
            **params: Can override participation_rate, min/max_slice_size
            
        Returns:
            List of child orders with potentially flexible quantities
        """
        self.initialize(order)
        
        participation_rate = params.get("participation_rate", self.participation_rate)
        min_slice_size = params.get("min_slice_size", self.min_slice_size)
        max_slice_size = params.get("max_slice_size", self.max_slice_size)
        
        if end_time is None:
            end_time = start_time + timedelta(minutes=60)  # default 1 hour
        
        # POV doesn't have a fixed schedule like TWAP/VWAP.
        # Instead, we generate placeholder child orders that will be resized
        # dynamically based on actual volume.
        
        # Strategy: create frequent small orders that will be reprinted
        # or create child orders per bar in backtest
        total_duration_minutes = (end_time - start_time).total_seconds() / 60
        interval_minutes = 5  # Check every 5 minutes
        num_checks = max(1, int(total_duration_minutes / interval_minutes))
        
        children = []
        for i in range(num_checks):
            scheduled_time = start_time + timedelta(minutes=i * interval_minutes)
            
            # Use estimated volume for this interval (equal split as estimate)
            interval_volume_estimate = 1.0 / num_checks  # normalized to 1.0 total
            estimated_qty = order.quantity * participation_rate * interval_volume_estimate
            
            # Clamp to min/max
            estimated_qty = max(min_slice_size, min(max_slice_size, estimated_qty))
            
            child = ChildOrder(
                quantity=estimated_qty,
                scheduled_time=scheduled_time,
                order_type=order.order_type,
                parent_order_id=order.order_id or "",
                slice_number=i + 1,
                total_slices=num_checks,
                child_order_id=f"{order.order_id or 'pov'}_child_{i+1}",
            )
            children.append(child)
            self.child_orders.append(child)
        
        return children
    
    def adjust_child_quantity(
        self,
        child: ChildOrder,
        observed_volume: float,
        remaining_quantity: float,
    ) -> float:
        """
        Dynamically adjust child order quantity based on actual volume.
        
        Called during execution to resize child orders.
        
        Args:
            child: The child order to adjust
            observed_volume: Actual volume observed in this interval
            remaining_quantity: Remaining parent quantity
            
        Returns:
            New quantity for child order
        """
        # Target quantity = participation_rate * observed_volume
        target_qty = self.participation_rate * observed_volume
        
        # Clamp
        target_qty = max(self.min_slice_size, min(self.max_slice_size, target_qty))
        
        # Don't exceed remaining
        target_qty = min(target_qty, remaining_quantity)
        
        return target_qty
    
    def get_statistics(self) -> Dict[str, Any]:
        stats = super().get_statistics()
        stats.update({
            "algorithm": self.name,
            "participation_rate": self.participation_rate,
            "min_slice_size": self.min_slice_size,
            "max_slice_size": self.max_slice_size,
            "lookahead_minutes": self.lookahead_minutes,
        })
        return stats
