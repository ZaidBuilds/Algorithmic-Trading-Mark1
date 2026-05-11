"""
Unit tests for SmartOrderRouter.

Tests cover:
- Order execution with different algorithms (TWAP, VWAP, market)
- Broker selection
- Child order generation and splitting
- Fill processing and report generation
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    OrderSide,
    OrderType,
    AlgorithmType,
)
from quantumtrade.adapters.execution.smart_router import SmartOrderRouter
from quantumtrade.adapters.execution.broker_selector import BaseBroker, BrokerSelector
from quantumtrade.adapters.execution.algorithms import (
    TWAPAlgorithm,
    VWAPAlgorithm,
    POVAlgorithm,
)
from quantumtrade.adapters.execution.fill_simulator import FillSimulator
from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer


# Dummy broker for testing
class DummyBroker(BaseBroker):
    def __init__(self, name="dummy", score=1.0):
        super().__init__(name=name)
        self.score = score
        self._is_connected = True

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def is_connected(self) -> bool:
        return self._is_connected

    def submit_order(self, order: BrokerOrder) -> str:
        return f"{self.name}_order_{order.order_id}"

    def cancel_order(self, broker_order_id: str) -> bool:
        return True

    def get_order(self, broker_order_id: str):
        return {"status": "filled"}

    def get_fills(self, broker_order_id: str):
        return []

    def get_account_balance(self) -> float:
        return 1_000_000

    def get_position(self, symbol: str) -> float:
        return 0.0

    def get_score(self) -> float:
        return self.score


@pytest.fixture
def brokers():
    """Create dummy brokers for testing broker selector."""
    return {
        "broker_a": DummyBroker("broker_a", score=0.9),
        "broker_b": DummyBroker("broker_b", score=0.8),
    }


@pytest.fixture
def router(brokers):
    """Create a SmartOrderRouter instance."""
    fill_sim = FillSimulator(
        slippage_model="fixed",
        fixed_slippage_bps=1.0,
        unlimited_liquidity=True,
        fill_probability=1.0,
    )
    return SmartOrderRouter(
        brokers=brokers,
        default_algorithm="twap",
        data_client=None,
        redis_client=None,
        execution_config={"slippage_model": "fixed"},
    )


@pytest.fixture
def sample_order():
    """Create a sample BUY order."""
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        order_type=OrderType.MARKET,
        timestamp=datetime(2024, 1, 1, 9, 30),
    )


class TestSmartOrderRouter:
    """Test cases for SmartOrderRouter."""

    def test_router_initialization(self, router):
        assert router is not None
        assert router.default_algorithm == "twap"
        assert router.fill_simulator is not None

    def test_execute_market_order(self, router, sample_order, monkeypatch):
        """Test execution of immediate market order."""
        # Simulate immediate fill without algorithm
        # Need to simulate market order using simulator
        monkeypatch.setattr(router.fill_simulator, "simulate_fill", lambda order, bar, **kw: type(
            "Fill",
            (),
            {
                "quantity": order.quantity,
                "price": 100.0,
                "trade_timestamp": datetime.now(),
                "fill_id": "f1",
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "broker": order.broker or "test",
                "notional_value": order.quantity * 100.0,
                "commission": 0.0,
                "fees": 0.0,
            },
        )())
        report = router.execute_order(sample_order, algorithm="market")
        assert report is not None
        assert report.order == sample_order

    def test_twap_generates_child_orders(self, sample_order):
        from quantumtrade.adapters.execution.algorithms.twap import TWAPAlgorithm
        algo = TWAPAlgorithm(duration_minutes=60, num_slices=6)
        start = datetime(2024,1,1,9,30)
        children = algo.generate_schedule(sample_order, start_time=start)
        assert len(children) == 6
        # Check equal sizing (maybe last slice extra)
        total = sum(c.quantity for c in children)
        assert total == sample_order.quantity

    def test_vwap_generates_child_orders(self, sample_order):
        from quantumtrade.adapters.execution.algorithms.vwap import VWAPAlgorithm
        algo = VWAPAlgorithm(duration_minutes=60, target_participation_rate=0.1)
        start = datetime(2024,1,1,9,30)
        children = algo.generate_schedule(sample_order, start_time=start)
        assert len(children) > 0
        total = sum(c.quantity for c in children)
        assert total >= sample_order.quantity * 0.99  # allow rounding

    def test_broker_selection(self, router, sample_order):
        # Call router's broker selector logic (exposed via select_broker)
        broker_name = router.broker_selector.select_broker(
            symbol=sample_order.symbol,
            order_type=sample_order.order_type.value,
            quantity=sample_order.quantity,
            side=sample_order.side,
            current_price=100.0,
        )
        # Should pick highest score broker_a (score 0.9)
        assert broker_name == "broker_a"

    def test_add_fill_updates_status(self, router, sample_order):
        report = router.execute_order(sample_order, algorithm="market")
        order_id = sample_order.order_id
        # Simulate a fill
        fill = type(
            "Fill",
            (),
            {
                "fill_id": "fill1",
                "order_id": order_id,
                "symbol": "AAPL",
                "side": sample_order.side,
                "quantity": 500,
                "price": 100.0,
                "trade_timestamp": datetime.now(),
                "received_timestamp": datetime.now(),
                "broker": "test",
                "commission": 0.0,
                "fees": 0.0,
            },
        )()
        complete, exec_report = router.add_fill(order_id, fill)
        assert exec_report is not None
        # Not complete yet (partial fill)
        assert not complete
        # Add second fill to complete
        fill2 = type(
            "Fill",
            (),
            {
                "fill_id": "fill2",
                "order_id": order_id,
                "symbol": "AAPL",
                "side": sample_order.side,
                "quantity": 500,
                "price": 101.0,
                "trade_timestamp": datetime.now(),
                "received_timestamp": datetime.now(),
                "broker": "test",
                "commission": 0.0,
                "fees": 0.0,
            },
        )()
        complete, exec_report = router.add_fill(order_id, fill2)
        assert complete
        assert exec_report.total_filled_quantity == 1000

    def test_tca_generated_in_report(self, router, sample_order):
        """Ensure TCA report is generated."""
        report = router.execute_order(sample_order, algorithm="market")
        # Manually add fill to trigger TCA
        fill = type(
            "Fill",
            (),
            {
                "fill_id": "fill1",
                "order_id": sample_order.order_id,
                "symbol": "AAPL",
                "side": sample_order.side,
                "quantity": sample_order.quantity,
                "price": 100.0,
                "trade_timestamp": datetime.now(),
                "received_timestamp": datetime.now(),
                "broker": "test",
                "commission": 0.0,
                "fees": 0.0,
            },
        )()
        router.fill_simulator.unlimited_liquidity = True
        complete, exec_report = router.add_fill(sample_order.order_id, fill)
        summaries = router.get_tca_summary(sample_order.order_id)
        assert summaries is not None
        assert "total_cost_bps" in summaries

    def test_reset_clears_state(self, router, sample_order):
        router.execute_order(sample_order, algorithm="twap")
        router.reset()
        assert len(router._active_orders) == 0
        assert len(router._fills) == 0


class TestAlgorithmScheduling:
    """Test schedule generation for each algorithm."""

    def test_twap_schedule_timing(self, sample_order):
        algo = TWAPAlgorithm(duration_minutes=30, num_slices=3)
        start = datetime(2024,1,1,10,0)
        children = algo.generate_schedule(sample_order, start_time=start)
        # Check intervals roughly equal
        times = [c.scheduled_time for c in children]
        assert (times[1] - times[0]).total_seconds() == 10*60  # 10 minutes

    def test_pov_adaptability(self, sample_order):
        algo = POVAlgorithm(participation_rate=0.2, min_slice_size=10, max_slice_size=1000)
        start = datetime(2024,1,1,10,0)
        children = algo.generate_schedule(sample_order, start_time=start, end_time=start+timedelta(minutes=30))
        assert len(children) == 6  # check per 5 min

    def test_iceberg_display_size(self, sample_order):
        algo = IcebergAlgorithm(display_qty=200)
        children = algo.generate_schedule(sample_order, start_time=datetime.now())
        for child in children:
            assert child.quantity == 200
        # last slice handles remainder
        total = sum(c.quantity for c in children)
        assert total == sample_order.quantity
