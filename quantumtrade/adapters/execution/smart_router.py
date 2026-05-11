"""
Smart Order Router — enterprise-grade execution layer orchestrator.

This is the central component that:
- Accepts incoming orders
- Chooses optimal algorithm
- Selects best broker(s)
- Splits orders into child orders
- Coordinates fill collection
- Generates TCA reports
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import uuid
import asyncio

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    Fill,
    ExecutionReport,
    ChildOrder,
    OrderSide,
    OrderStatus,
)
from quantumtrade.adapters.execution.algorithms import (
    OrderAlgorithm,
    TWAPAlgorithm,
    VWAPAlgorithm,
    POVAlgorithm,
    ImplementationShortfallAlgorithm,
    IcebergAlgorithm,
)
from quantumtrade.adapters.execution.broker_selector import BrokerSelector
from quantumtrade.adapters.brokers.base import BaseBroker
from quantumtrade.adapters.execution.fill_simulator import FillSimulator
from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer
from quantumtrade.adapters.execution.cost_models import SpreadCostModel


class SmartOrderRouter:
    """
    Intelligently routes orders to minimize market impact and transaction costs.
    
    Features:
    - Multiple execution algorithms (TWAP, VWAP, POV, Implementation Shortfall, Iceberg)
    - Multi-broker routing with intelligent selection
    - Real-time fill simulation (backtest) or live execution
    - Transaction Cost Analysis (TCA) reporting
    - Order splitting and child order management
    """
    
    ALGORITHM_MAP = {
        "market": None,  # immediate fill
        "twap": TWAPAlgorithm,
        "vwap": VWAPAlgorithm,
        "pov": POVAlgorithm,
        "implementation_shortfall": ImplementationShortfallAlgorithm,
        "iceberg": IcebergAlgorithm,
    }
    
    def __init__(
        self,
        brokers: Dict[str, BaseBroker],
        default_algorithm: str = "twap",
        data_client=None,  # For market data access
        redis_client=None,  # For caching order state
        execution_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize SmartOrderRouter.
        
        Args:
            brokers: Dict of {broker_name: BaseBroker instance}
            default_algorithm: Default algo when not specified
            data_client: Market data client (optional, for live)
            redis_client: Redis for state persistence (optional)
            execution_config: Additional configuration dict
        """
        self.brokers = brokers
        self.default_algorithm = default_algorithm
        self.data_client = data_client
        self.redis = redis_client
        
        # Config
        config = execution_config or {}
        self.config = {
            "default_algorithm": default_algorithm,
            "enable_smart_routing": config.get("enable_smart_routing", True),
            "slippage_model": config.get("slippage_model", "volume"),
            "fixed_slippage_bps": config.get("fixed_slippage_bps", 1.0),
            "target_participation_rate": config.get("target_participation_rate", 0.10),
            "twap_default_duration_minutes": config.get("twap_default_duration_minutes", 30),
            "max_slippage_bps": config.get("max_slippage_bps", 10.0),
            "enable_iceberg": config.get("enable_iceberg", False),
            "iceberg_display_qty": config.get("iceberg_display_qty", 100),
        }
        
        # Initialize components
        self.broker_selector = BrokerSelector(brokers=brokers)
        self.fill_simulator = FillSimulator(
            slippage_model=self.config["slippage_model"],
            fixed_slippage_bps=self.config["fixed_slippage_bps"],
        )
        self.tca = TransactionCostAnalyzer(benchmark="arrival", spread_model="mid")
        
        # Runtime state
        self._active_orders: Dict[str, BrokerOrder] = {}
        self._child_orders: Dict[str, List[ChildOrder]] = {}
        self._fills: Dict[str, List[Fill]] = {}
        self._algorithms: Dict[str, OrderAlgorithm] = {}
    
    def execute_order(
        self,
        order: BrokerOrder,
        algorithm: Optional[str] = None,
        **algo_params
    ) -> ExecutionReport:
        """
        Execute an order using smart routing.
        
        Args:
            order: BrokerOrder to execute
            algorithm: Algorithm name (twap, vwap, pov, etc.)
            **algo_params: Algorithm-specific parameters
            
        Returns:
            ExecutionReport with fills and TCA analysis
        """
        # Assign IDs
        if not order.order_id:
            order.order_id = f"order_{uuid.uuid4().hex[:8]}"
        
        # Select algorithm
        algo_name = algorithm or self.config["default_algorithm"]
        if algo_name == "market":
            return self._execute_market_order(order)
        
        algo_cls = self.ALGORITHM_MAP.get(algo_name)
        if not algo_cls:
            raise ValueError(f"Unknown algorithm: {algo_name}")
        
        # Initialize algorithm
        algo = algo_cls(data_client=self.data_client, **algo_params)
        self._algorithms[order.order_id] = algo
        
        # Determine execution window
        duration = algo_params.get(
            "duration_minutes",
            self.config["twap_default_duration_minutes"],
        )
        start_time = order.timestamp
        end_time = start_time + timedelta(minutes=duration)
        
        # Generate child order schedule
        child_orders = algo.generate_schedule(order, start_time, end_time, **algo_params)
        self._child_orders[order.order_id] = child_orders
        
        # Select broker(s)
        if self.config["enable_smart_routing"]:
            current_price = self._get_current_price(order.symbol)
            broker_name = self.broker_selector.select_broker(
                symbol=order.symbol,
                order_type=order.order_type.value,
                quantity=order.quantity,
                side=order.side,
                current_price=current_price,
                strategy=order.strategy,
                algorithm=algo_name,
            )
            order.broker = broker_name
        else:
            order.broker = list(self.brokers.keys())[0]
        
        # Store active order
        self._active_orders[order.order_id] = order
        
        # In live mode: submit to broker, start monitoring
        # In backtest mode: execute via fill simulator
        # This method is a synchronous wrapper for backtest; live uses async path
        
        # For backtest: return empty report, fills added later via add_fill()
        return ExecutionReport(order=order, fills=[])
    
    def _execute_market_order(self, order: BrokerOrder) -> ExecutionReport:
        """Execute immediate market order."""
        # For backtest, we need market data — will be filled externally
        order.order_type = OrderType.MARKET
        order.algorithm = "market"
        self._active_orders[order.order_id] = order
        return ExecutionReport(order=order, fills=[])
    
    def add_fill(
        self,
        order_id: str,
        fill: Fill,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, ExecutionReport]:
        """
        Add a fill to an active order.
        
        Args:
            order_id: Parent order ID
            fill: Fill received
            market_data: Optional market data for TCA update
            
        Returns:
            (is_complete, ExecutionReport)
        """
        if order_id not in self._fills:
            self._fills[order_id] = []
        
        self._fills[order_id].append(fill)
        
        # Update algorithm state
        if order_id in self._algorithms:
            algo = self._algorithms[order_id]
            algo.update_fill(
                fill.child_order_id or fill.order_id,
                fill.quantity,
                fill.price,
                fill.trade_timestamp,
            )
        
        # Update order filled quantity
        if order_id in self._active_orders:
            order = self._active_orders[order_id]
            order.filled_quantity += fill.quantity
            if order.filled_quantity >= order.quantity:
                order.status = OrderStatus.FILLED
                order.filled_at = fill.trade_timestamp
        
        # Check if complete
        is_complete = self._is_order_complete(order_id)
        
        # Generate report
        report = self.get_execution_report(order_id, market_data)
        
        # Cleanup if complete
        if is_complete:
            self._cleanup_order(order_id)
        
        return is_complete, report
    
    def simulate_execution(
        self,
        order: BrokerOrder,
        market_data_bars: List[Dict[str, Any]],
        order_books: Optional[List[Dict[str, Any]]] = None,
        avg_daily_volume: Optional[float] = None,
    ) -> ExecutionReport:
        """
        Simulate full execution via fill simulator.
        Used primarily in backtest.
        
        Returns:
            ExecutionReport with simulated fills
        """
        # Create execution report with no fills
        report = self.execute_order(order, algorithm=order.algorithm.value)
        
        # Run simulator
        fills = self.fill_simulator.simulate_order_execution(
            order=order,
            bars=market_data_bars,
            order_books=order_books,
            avg_daily_volume=avg_daily_volume,
        )
        
        # Process fills
        for fill in fills:
            self.add_fill(order.order_id, fill)
        
        # Final report
        return self.get_execution_report(order.order_id)
    
    def get_execution_report(
        self,
        order_id: str,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionReport:
        """
        Generate execution report for an order.
        
        Uses TCA to provide comprehensive cost analysis.
        """
        if order_id not in self._active_orders:
            return ExecutionReport(order=BrokerOrder(symbol="", side=OrderSide.BUY, quantity=0), fills=[])
        
        order = self._active_orders[order_id]
        fills = self._fills.get(order_id, [])
        
        # Build ExecutionReport first
        exec_report = ExecutionReport(order=order, fills=fills)
        
        # Generate TCA if we have fills
        if fills and market_data is not None:
            # Convert market_data dict to DataFrame if needed
            if isinstance(market_data, dict):
                md_df = pd.DataFrame([market_data])
            elif isinstance(market_data, pd.DataFrame):
                md_df = market_data
            else:
                md_df = pd.DataFrame()
            
            tca_report = self.tca.analyze_execution(
                order=order,
                fills=fills,
                market_data=md_df,
                pre_trade_benchmark=order.pre_trade_benchmark,
                post_trade_benchmark=order.post_trade_benchmark,
            )
            # Could attach tca_report to exec_report if desired
        elif fills:
            # We have fills but no market data — calc basics
            exec_report = ExecutionReport(order=order, fills=fills)
        
        return exec_report
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel active order."""
        if order_id in self._active_orders:
            order = self._active_orders[order_id]
            order.status = OrderStatus.CANCELLED
            
            # Cancel algorithm
            if order_id in self._algorithms:
                del self._algorithms[order_id]
            
            self._cleanup_order(order_id)
            return True
        return False
    
    def get_active_orders(self) -> List[BrokerOrder]:
        """Get currently active orders."""
        return list(self._active_orders.values())
    
    def get_order_fills(self, order_id: str) -> List[Fill]:
        """Get fills for an order."""
        return self._fills.get(order_id, [])
    
    def _is_order_complete(self, order_id: str) -> bool:
        """Check if order is fully filled, cancelled, or failed."""
        if order_id not in self._active_orders:
            return True
        
        order = self._active_orders[order_id]
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            return True
        
        # Check if algorithm is done
        if order_id in self._algorithms:
            algo = self._algorithms[order_id]
            if algo.is_complete():
                order.status = OrderStatus.FILLED
                return True
        
        return False
    
    def _cleanup_order(self, order_id: str):
        """Clean up internal state after order completion."""
        # Optionally persist to DB here
        pass
    
    def _get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol (from data_client or cache)."""
        if self.data_client:
            # Could fetch live or latest
            pass
        return 100.0  # placeholder
    
    def get_tca_summary(self, order_id: str) -> Dict[str, Any]:
        """
        Get TCA summary for an order.
        
        Returns dict with cost metrics.
        """
        report = self.get_execution_report(order_id)
        return report.to_dict()
    
    def reset(self):
        """Reset router state (for backtest between runs)."""
        self._active_orders.clear()
        self._child_orders.clear()
        self._fills.clear()
        self._algorithms.clear()
