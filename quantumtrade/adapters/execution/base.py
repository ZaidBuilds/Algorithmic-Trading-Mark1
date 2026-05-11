"""
Base classes and abstract interfaces for execution layer.

Defines the core abstractions: ExecutionRouter, FillHandler, CostAnalyzer.
These serve as ports in the hexagonal architecture.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    Fill,
    ExecutionReport,
    TransactionCostReport,
)


class AbstractExecutionRouter(ABC):
    """
    Abstract port for order execution.
    
    Concrete adapters implement routing to specific exchanges/brokers.
    This interface allows swapping execution backends.
    """
    
    @abstractmethod
    def submit_order(
        self,
        order: BrokerOrder,
        algorithm: Optional[str] = None,
        **algo_params
    ) -> str:
        """
        Submit an order for execution.
        
        Args:
            order: Order to submit
            algorithm: Optional algo name
            **algo_params: Algorithm-specific parameters
            
        Returns:
            order_id for tracking
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a submitted order."""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of an order."""
        pass
    
    @abstractmethod
    def get_fills(self, order_id: str) -> List[Fill]:
        """Get fills for an order."""
        pass
    
    @abstractmethod
    def get_execution_report(self, order_id: str) -> Optional[ExecutionReport]:
        """Generate execution report for completed order."""
        pass
    
    @abstractmethod
    def is_active(self) -> bool:
        """Check if router is connected and operational."""
        pass


class AbstractFillHandler(ABC):
    """
    Abstract handler for processing incoming fills.
    
    Can be used to process fills from brokers and update internal state.
    """
    
    @abstractmethod
    def on_fill(
        self,
        order_id: str,
        fill: Fill,
    ) -> None:
        """Process an incoming fill."""
        pass
    
    @abstractmethod
    def on_order_status_change(
        self,
        order_id: str,
        status: str,
        message: Optional[str] = None,
    ) -> None:
        """Process order status update."""
        pass


class AbstractCostAnalyzer(ABC):
    """
    Abstract port for Transaction Cost Analysis.
    
    Allows plugging in different TCA implementations.
    """
    
    @abstractmethod
    def analyze(
        self,
        order: BrokerOrder,
        fills: List[Fill],
        market_data: Any,
    ) -> TransactionCostReport:
        """Perform TCA on an execution."""
        pass
    
    @abstractmethod
    def get_benchmark_price(self, symbol: str, timestamp: datetime) -> float:
        """Get benchmark price for a symbol at a given time."""
        pass


class ExecutionConfig:
    """
    Configuration container for execution layer.
    
    Centralizes all execution parameters in one place.
    """
    
    def __init__(
        self,
        default_algorithm: str = "twap",
        enable_smart_routing: bool = True,
        slippage_model: str = "volume",
        fixed_slippage_bps: float = 1.0,
        target_participation_rate: float = 0.10,
        twap_default_duration_minutes: int = 30,
        max_slippage_bps: float = 10.0,
        enable_iceberg: bool = False,
        iceberg_display_qty: int = 100,
        enable_tca: bool = True,
        enable_fill_simulation: bool = True,
        **kwargs,
    ):
        self.default_algorithm = default_algorithm
        self.enable_smart_routing = enable_smart_routing
        self.slippage_model = slippage_model
        self.fixed_slippage_bps = fixed_slippage_bps
        self.target_participation_rate = target_participation_rate
        self.twap_default_duration_minutes = twap_default_duration_minutes
        self.max_slippage_bps = max_slippage_bps
        self.enable_iceberg = enable_iceberg
        self.iceberg_display_qty = iceberg_display_qty
        self.enable_tca = enable_tca
        self.enable_fill_simulation = enable_fill_simulation
        # store any additional params
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return self.__dict__.copy()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionConfig":
        """Create from dictionary."""
        return cls(**data)


# Type alias for convenient reference
# NOTE: OrderAlgorithm is referenced by some parts of the execution layer,
# but may not be defined yet in this module. Provide a safe fallback to
# keep imports working.
try:  # pragma: no cover
    OrderAlgorithm  # type: ignore[name-defined]  # noqa: F401
except NameError:  # pragma: no cover
    OrderAlgorithm = str  # type: ignore[assignment]

ExecutionAlgorithm = OrderAlgorithm

# SlippageModel may be defined in cost_models; provide a safe fallback for imports.
try:  # pragma: no cover
    SlippageModel  # type: ignore[name-defined]  # noqa: F401
except NameError:  # pragma: no cover
    SlippageModel = str  # type: ignore[assignment]

CostModel = SlippageModel  # imported from cost_models when needed
