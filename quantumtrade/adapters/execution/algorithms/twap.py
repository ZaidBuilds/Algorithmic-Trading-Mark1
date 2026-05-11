"""
Time-Weighted Average Price (TWAP) Algorithm.

Splits order into equal-sized slices distributed evenly over time.
Ignores volume — simply average time to minimize market impact.

Best for: illiquid instruments, minimizing footprint, predictable schedule.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Any
import math

from quantumtrade.adapters.execution.models import BrokerOrder, ChildOrder, OrderSide
from quantumtrade.adapters.execution.algorithms.base import OrderAlgorithm


class TWAPAlgorithm(OrderAlgorithm):
    """
    Time-Weighted Average Price execution algorithm.
    
    Divides the order into N equal slices and spaces them evenly over
    the specified duration. Execution ignores volume.
    
    Parameters:
        num_slices: Number of child orders (default: auto-calc from duration)
        duration_minutes: Total execution window in minutes
        interval_minutes: Time between slices (derived if not specified)
    """
    
    def __init__(
        self,
        data_client=None,
        num_slices: Optional[int] = None,
        duration_minutes: int = 30,
        interval_minutes: Optional[int] = None,
    ):
        super().__init__(name="TWAP", data_client=data_client)
        self.num_slices = num_slices
        self.duration_minutes = duration_minutes
        self.interval_minutes = interval_minutes
    
    def generate_schedule(
        self,
        order: BrokerOrder,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        **params
    ) -> List[ChildOrder]:
        """
        Generate TWAP schedule.
        
        Args:
            order: Parent order
            start_time: Execution start time
            end_time: Optional end time. If not provided, uses start + duration
            **params: Can override num_slices, duration_minutes
            
        Returns:
            List of child orders
        """
        self.initialize(order)
        
        # Allow parameter overrides
        num_slices = params.get("num_slices", self.num_slices)
        duration_minutes = params.get("duration_minutes", self.duration_minutes)
        interval_minutes = params.get("interval_minutes", self.interval_minutes)
        
        # Calculate end_time
        if end_time is None:
            end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Determine number of slices
        if num_slices is None:
            if interval_minutes is not None:
                total_minutes = duration_minutes
                num_slices = max(1, int(total_minutes / interval_minutes))
            else:
                # Auto-calculate: 1 slice per 5 minutes minimum
                num_slices = max(1, int(duration_minutes / 5))
        num_slices = max(1, num_slices)
        
        # Calculate slice size
        slice_quantity = order.quantity / num_slices
        
        # Round to integer if quantity is integer-like
        if order.quantity == int(order.quantity):
            slice_quantity = int(slice_quantity)
            # Adjust last slice for remainder
            total = slice_quantity * (num_slices - 1)
            last_slice = int(order.quantity) - total
        else:
            # Float quantities — keep as is
            last_slice = order.quantity - (slice_quantity * (num_slices - 1))
        
        # Compute interval
        if interval_minutes is not None:
            interval = timedelta(minutes=interval_minutes)
        else:
            total_seconds = (end_time - start_time).total_seconds()
            interval = timedelta(seconds=total_seconds / (num_slices - 1 if num_slices > 1 else 1))
        
        # Generate child orders
        children = []
        for i in range(num_slices):
            scheduled_time = start_time + (interval * i)
            qty = last_slice if i == num_slices - 1 else slice_quantity
            
            # Ensure qty not negative
            if qty <= 0:
                continue
            
            child = ChildOrder(
                quantity=qty,
                scheduled_time=scheduled_time,
                order_type=order.order_type,
                parent_order_id=order.order_id or "",
                slice_number=i + 1,
                total_slices=num_slices,
                child_order_id=f"{order.order_id or 'twap'}_child_{i+1}",
            )
            children.append(child)
            self.child_orders.append(child)
        
        return children
    
    def get_statistics(self) -> dict:
        stats = super().get_statistics()
        stats.update({
            "algorithm": self.name,
            "num_slices": self.num_slices,
            "duration_minutes": self.duration_minutes,
            "interval_minutes": self.interval_minutes,
        })
        return stats
