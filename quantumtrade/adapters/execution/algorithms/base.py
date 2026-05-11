"""
Base class for all order execution algorithms.

Defines the common interface that all execution algorithms must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict
import uuid

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    ChildOrder,
    OrderSide,
    OrderStatus,
)


class OrderAlgorithm(ABC):
    """
    Abstract base class for order execution algorithms.
    
    Algorithms take a parent order and split it into child orders
    according to their specific logic (time, volume, participation, etc.)
    """
    
    def __init__(
        self,
        name: str,
        data_client=None,  # For market data access
    ):
        self.name = name
        self.data_client = data_client
        self.child_orders: List[ChildOrder] = []
        self._parent_order: Optional[BrokerOrder] = None
    
    @abstractmethod
    def generate_schedule(
        self,
        order: BrokerOrder,
        start_time: datetime,
        end_time: datetime,
        **params
    ) -> List[ChildOrder]:
        """
        Generate the schedule of child orders for the parent order.
        
        Args:
            order: Parent order to be split
            start_time: When to start executing
            end_time: Deadline for completion
            **params: Algorithm-specific parameters
            
        Returns:
            List of ChildOrder objects with scheduled quantities and times
        """
        pass
    
    def initialize(self, order: BrokerOrder):
        """Initialize algorithm with parent order."""
        self._parent_order = order
        self.child_orders = []
    
    def get_next_child(
        self,
        current_time: datetime,
        remaining_quantity: float,
    ) -> Optional[ChildOrder]:
        """
        Get the next child order ready to submit.
        
        Args:
            current_time: Current simulation/trading time
            remaining_quantity: How much of parent order remains
            
        Returns:
            ChildOrder if one is ready, else None
        """
        for child in self.child_orders:
            if child.status == OrderStatus.PENDING and child.scheduled_time <= current_time:
                if remaining_quantity >= child.quantity:
                    child.status = OrderStatus.SUBMITTED
                    child.submitted_at = current_time
                    return child
        return None
    
    def update_fill(
        self,
        child_order_id: str,
        filled_quantity: float,
        fill_price: float,
        fill_time: datetime,
    ):
        """Update child order with fill information."""
        for child in self.child_orders:
            if child.child_order_id == child_order_id:
                child.filled_quantity += filled_quantity
                child.fill_price = fill_price
                child.status = OrderStatus.FILLED if child.filled_quantity >= child.quantity else OrderStatus.PARTIAL
                child.filled_at = fill_time
                break
    
    def is_complete(self) -> bool:
        """Check if all child orders have been filled."""
        if not self._parent_order:
            return False
        total_filled = sum(c.filled_quantity for c in self.child_orders)
        return total_filled >= self._parent_order.quantity
    
    def get_remaining_quantity(self) -> float:
        """Get remaining quantity in parent order."""
        if not self._parent_order:
            return 0.0
        total_filled = sum(c.filled_quantity for c in self.child_orders)
        return self._parent_order.quantity - total_filled
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get algorithm execution statistics."""
        if not self.child_orders:
            return {}
        
        total_filled = sum(c.filled_quantity for c in self.child_orders)
        submitted = [c for c in self.child_orders if c.status != OrderStatus.PENDING]
        
        return {
            "algorithm": self.name,
            "total_child_orders": len(self.child_orders),
            "submitted_child_orders": len(submitted),
            "filled_child_orders": len([c for c in self.child_orders if c.is_filled]),
            "total_filled_quantity": total_filled,
            "total_parent_quantity": self._parent_order.quantity if self._parent_order else 0,
            "completion_pct": (total_filled / self._parent_order.quantity * 100) if self._parent_order else 0,
        }
