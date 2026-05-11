"""
Volume-Weighted Average Price (VWAP) Algorithm.

Splits order according to historical volume profile — participates in
periods of high volume more heavily. Goal: execute at or better than VWAP.

Best for: liquid instruments, large orders, participation in volume spikes.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict
import math

from quantumtrade.adapters.execution.models import BrokerOrder, ChildOrder
from quantumtrade.adapters.execution.algorithms.base import OrderAlgorithm


class VWAPAlgorithm(OrderAlgorithm):
    """
    Volume-Weighted Average Price execution algorithm.
    
    Distributes child orders according to a volume profile (intraday pattern).
    Can use a standard profile or a custom profile provided via params.
    
    Parameters:
        target_participation_rate: % of market volume to target (0.0 - 1.0)
        duration_minutes: Execution window
        volume_profile: Dict mapping time bucket -> expected volume % (sum to 1.0)
        num_buckets: Number of time buckets for profile (default 13 for 5-min intervals in 1hr)
    """
    
    # Standard intraday volume profile (approximate US equities)
    DEFAULT_PROFILE = [
        0.06,  # 9:30-9:35  4.4%
        0.09,  # 9:35-9:40  6.6%
        0.11,  # 9:40-9:45  8.1%
        0.10,  # 9:45-9:50  7.4%
        0.09,  # 9:50-9:55  6.6%
        0.08,  # 10:00-10:05 (skip 10:00-10:00 = 5.8%)
        0.07,  # ...
        0.06,
        0.06,
        0.06,
        0.05,
        0.05,
        0.05,
        0.04,
        0.04,
        0.04,
    ]
    
    def __init__(
        self,
        data_client=None,
        target_participation_rate: float = 0.10,
        duration_minutes: int = 60,
        volume_profile: Optional[List[float]] = None,
        num_buckets: int = 12,
    ):
        super().__init__(name="VWAP", data_client=data_client)
        self.target_participation_rate = target_participation_rate
        self.duration_minutes = duration_minutes
        self.volume_profile = volume_profile or self.DEFAULT_PROFILE[:num_buckets]
        self.num_buckets = num_buckets
        
        # Normalize profile to sum to 1.0
        profile_sum = sum(self.volume_profile)
        if profile_sum > 0:
            self.volume_profile = [p / profile_sum for p in self.volume_profile]
    
    def generate_schedule(
        self,
        order: BrokerOrder,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        **params
    ) -> List[ChildOrder]:
        """
        Generate VWAP schedule based on volume profile.
        
        Args:
            order: Parent order
            start_time: Execution start
            end_time: Optional end time. If None, uses start + duration
            **params: May override target_participation_rate, volume_profile
            
        Returns:
            List of child orders timed per volume buckets
        """
        self.initialize(order)
        
        # Allow overrides
        target_participation = params.get("target_participation_rate", self.target_participation_rate)
        duration_minutes = params.get("duration_minutes", self.duration_minutes)
        volume_profile = params.get("volume_profile", self.volume_profile)
        
        if end_time is None:
            end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Determine number of buckets from profile length
        num_buckets = len(volume_profile)
        if num_buckets == 0:
            # Fallback: equal buckets
            num_buckets = max(1, int(duration_minutes / 5))
            volume_profile = [1.0 / num_buckets] * num_buckets
        
        bucket_minutes = duration_minutes / num_buckets
        total_volume_allocated = 0.0
        
        children = []
        for i in range(num_buckets):
            bucket_start = start_time + timedelta(minutes=i * bucket_minutes)
            bucket_end = start_time + timedelta(minutes=(i + 1) * bucket_minutes)
            bucket_mid = bucket_start + (bucket_end - bucket_start) / 2
            
            # Allocate quantity by profile weight
            profile_weight = volume_profile[i] if i < len(volume_profile) else 1.0 / num_buckets
            expected_bucket_qty = order.quantity * profile_weight
            total_volume_allocated += profile_weight
            
            child = ChildOrder(
                quantity=expected_bucket_qty,
                scheduled_time=bucket_mid,
                order_type=order.order_type,
                parent_order_id=order.order_id or "",
                slice_number=i + 1,
                total_slices=num_buckets,
                child_order_id=f"{order.order_id or 'vwap'}_child_{i+1}",
            )
            children.append(child)
            self.child_orders.append(child)
        
        # Adjust for any rounding drift — add to last bucket
        total_allocated_qty = sum(c.quantity for c in children)
        if abs(total_allocated_qty - order.quantity) > 0.001:
            diff = order.quantity - total_allocated_qty
            if children:
                children[-1].quantity += diff
        
        return children
    
    def get_statistics(self) -> Dict[str, Any]:
        stats = super().get_statistics()
        stats.update({
            "algorithm": self.name,
            "target_participation_rate": self.target_participation_rate,
            "duration_minutes": self.duration_minutes,
            "profile_buckets": len(self.volume_profile),
        })
        return stats
