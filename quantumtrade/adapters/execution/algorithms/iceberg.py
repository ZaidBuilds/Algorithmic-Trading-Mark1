"""
Iceberg Algorithm — Hidden order slicing.

Displays only a small portion (iceberg tip) of the total order quantity
in the market, refreshing displayed size after fills. Conceals true order size
from other market participants.

Best for: large orders, HFT-friendly exchanges, minimizing information leakage.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict
import random

from quantumtrade.adapters.execution.models import BrokerOrder, ChildOrder
from quantumtrade.adapters.execution.algorithms.base import OrderAlgorithm


class IcebergAlgorithm(OrderAlgorithm):
    """
    Iceberg (hidden) order execution algorithm.
    
    Only a small slice (display quantity) is visible at any time.
    After the visible slice fills, the next slice is submitted.
    Requires exchange support for iceberg/hidden orders. If not supported,
    emulates via sequential child orders.
    
    Parameters:
        display_qty: Visible quantity per order (iceberg tip)
        refresh_speed: Minimum time between refreshes (seconds)
        max_slippage_bps: Max acceptable slippage before pausing
        randomize_display: Randomize displayed size slightly to avoid pattern
        skip_interval: Number of fills before next refresh (for non-iceberg brokers)
    """
    
    def __init__(
        self,
        data_client=None,
        display_qty: Optional[int] = None,
        refresh_speed: int = 1,  # seconds
        max_slippage_bps: float = 10.0,
        randomize_display: bool = True,
        skip_interval: int = 1,
    ):
        super().__init__(name="Iceberg", data_client=data_client)
        self.display_qty = display_qty
        self.refresh_speed = refresh_speed  # seconds
        self.max_slippage_bps = max_slippage_bps
        self.randomize_display = randomize_display
        self.skip_interval = skip_interval
        self._last_refresh_time: Optional[datetime] = None
        self._fills_since_refresh = 0
    
    def _calculate_display_qty(self, order: BrokerOrder, display_qty: Optional[int]) -> int:
        """Determine display quantity — user-provided or heuristic."""
        if display_qty is not None:
            qty_display = int(display_qty)
        elif self.display_qty is not None:
            qty_display = int(self.display_qty)
        else:
            # Auto-calculate: 1-2% of total order, but at least 100 shares
            qty_display = max(100, int(order.quantity * 0.02))
        
        # Cap at total order quantity
        return min(qty_display, int(order.quantity))
    
    def generate_schedule(
        self,
        order: BrokerOrder,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        **params
    ) -> List[ChildOrder]:
        """
        Generate iceberg schedule.
        
        Unlike other algorithms, iceberg generates a series of child orders
        that will be submitted sequentially (not all at once).
        
        Returns list of child orders each equal to `display_qty`,
        except possibly the final remainder.
        """
        self.initialize(order)
        
        display_qty = params.get("display_qty", self._calculate_display_qty(order, self.display_qty))
        refresh_speed = params.get("refresh_speed", self.refresh_speed)
        
        # How many full slices
        num_full_slices = int(order.quantity) // display_qty
        remainder = int(order.quantity) % display_qty
        
        total_slices = num_full_slices + (1 if remainder > 0 else 0)
        
        children = []
        for i in range(num_full_slices):
            scheduled_time = start_time  # All initially unscheduled
            child = ChildOrder(
                quantity=display_qty,
                scheduled_time=scheduled_time,
                order_type=order.order_type,
                parent_order_id=order.order_id or "",
                slice_number=i + 1,
                total_slices=total_slices,
                child_order_id=f"{order.order_id or 'iceberg'}_child_{i+1}",
            )
            children.append(child)
            self.child_orders.append(child)
        
        if remainder > 0:
            child = ChildOrder(
                quantity=remainder,
                scheduled_time=start_time,
                order_type=order.order_type,
                parent_order_id=order.order_id or "",
                slice_number=total_slices,
                total_slices=total_slices,
                child_order_id=f"{order.order_id or 'iceberg'}_child_{total_slices}",
            )
            children.append(child)
            self.child_orders.append(child)
        
        # Store config for runtime use
        self._display_qty = display_qty
        self._refresh_speed = timedelta(seconds=refresh_speed)
        self._last_refresh_time = None
        self._fills_since_refresh = 0
        
        return children
    
    def get_next_child(
        self,
        current_time: datetime,
        remaining_quantity: float,
    ) -> Optional[ChildOrder]:
        """
        Get next child order respecting refresh constraints.
        
        Iceberg logic: only submit next child after refresh delay
        (or if not using native iceberg).
        """
        # Enforce refresh interval
        if self._last_refresh_time is not None:
            elapsed = current_time - self._last_refresh_time
            if elapsed < self._refresh_speed:
                return None  # Still in cooldown
        
        # Get next pending child
        child = super().get_next_child(current_time, remaining_quantity)
        if child:
            self._last_refresh_time = current_time
            self._fills_since_refresh = 0
        return child
    
    def should_refresh(
        self,
        child_order_id: str,
        fill_quantity: float,
        fill_time: datetime,
    ) -> bool:
        """
        Check if we should refresh (submit next slice) after a fill.
        
        For native iceberg brokers: no action needed (exchange handles refresh).
        For emulated: this triggers next child order.
        """
        self._fills_since_refresh += 1
        
        # If using skip interval: refresh every N fills
        if self._fills_since_refresh >= self.skip_interval:
            if self._last_refresh_time:
                elapsed = fill_time - self._last_refresh_time
                if elapsed >= self._refresh_speed:
                    return True
        else:
            # Also refresh if last child filled completely
            return True
        
        return False
    
    def get_statistics(self) -> Dict[str, Any]:
        stats = super().get_statistics()
        stats.update({
            "algorithm": self.name,
            "display_qty": self._display_qty if hasattr(self, "_display_qty") else self.display_qty,
            "refresh_speed_seconds": self.refresh_speed,
            "max_slippage_bps": self.max_slippage_bps,
        })
        return stats
