"""
Integration test for end-to-end execution flow.

Tests the complete pipeline:
- SmartOrderRouter receives order
- Splits using TWAP algorithm
- Simulates fills via FillSimulator
- Generates TCA reports
- Aggregates to ExecutionReport
"""

import pytest
from datetime import datetime, timedelta

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    OrderSide,
    OrderType,
    AlgorithmType,
)
from quantumtrade.adapters.execution.smart_router import SmartOrderRouter
from quantumtrade.adapters.execution.broker_selector import BaseBroker
from quantumtrade.adapters.execution.fill_simulator import FillSimulator
from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer


class DummyBroker(BaseBroker):
    def __init__(self):
        super().__init__(name="dummy")
        self._is_connected = True

    def connect(self) -> bool: return True
    def disconnect(self) -> None: pass
    def is_connected(self) -> bool: return self._is_connected
    def submit_order(self, order: BrokerOrder) -> str: return "broker_order_1"
    def cancel_order(self, broker_order_id: str) -> bool: return True
    def get_order(self, broker_order_id: str): return {"status": "filled"}
    def get_fills(self, broker_order_id: str): return []
    def get_account_balance(self) -> float: return 1_000_000
    def get_position(self, symbol: str) -> float: return 0.0


@pytest.fixture
def router():
    brokers = {"dummy": DummyBroker()}
    sim = FillSimulator(
        slippage_model="fixed",
        fixed_slippage_bps=5.0,  # 5 bps
        unlimited_liquidity=True,
        fill_probability=1.0,
    )
    s = SmartOrderRouter(
        brokers=brokers,
        default_algorithm="twap",
        execution_config={"slippage_model": "fixed", "fixed_slippage_bps": 5.0},
    )
    # Override simulator for deterministic tests
    s.fill_simulator = sim
    return s


@pytest.fixture
def market_bars():
    """Simulated market data bars for the execution window (1 min intervals)."""
    base_time = datetime(2024, 1, 1, 9, 30)
    bars = []
    price = 100.0
    for i in range(10):
        price += 0.1  # slight upward drift
        bars.append({
            "close": round(price, 2),
            "volume": 500_000,
            "timestamp": base_time + timedelta(minutes=i),
        })
    return bars


def test_end_to_end_twap_execution(router, market_bars):
    """Test full TWAP execution from order to fills."""
    order = BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        order_type=OrderType.MARKET,
        timestamp=market_bars[0]["timestamp"],
        algorithm=AlgorithmType.TWAP,
        algo_params={"duration_minutes": 10, "num_slices": 5},
    )

    # Normal path: router.execute_order(...) returns empty report for backtest unless simulator integrated.
    # In our design, router.execute_order creates child orders but doesn't simulate fills yet; fills added via add_fill.
    # However integration may simulate directly. But we can use router.simulate_execution method.
    # Let's use the router's simulate_execution method if available; we haven't added that to the router class? Yes we added simulate_execution.
    if hasattr(router, 'simulate_execution'):
        report = router.simulate_execution(order, market_bars, avg_daily_volume=1_000_000)
        assert report is not None
        assert report.total_filled_quantity == 1000
        # Check TCA reports generated
        tca_reports = router.get_tca_summary(order.order_id)
        assert tca_reports  # non-empty dict
        # Verify cost > 0 (slippage+spread)
        assert report.total_cost_bps > 0
    else:
        # Fallback: manually execute children and add fills
        report = router.execute_order(order, algorithm="twap", duration_minutes=10, num_slices=5)
        # Add fills from simulation for each bar (simulate order execution)
        fills = router.fill_simulator.simulate_order_execution(
            order=order,
            bars=market_bars,
            avg_daily_volume=1_000_000,
        )
        for f in fills:
            router.add_fill(order.order_id, f)
        final_report = router.get_execution_report(order.order_id, market_data=None)
        assert final_report.total_filled_quantity == 1000


def test_execution_cost_with_impact(router):
    """Test that larger orders show higher cost."""
    order_small = BrokerOrder(
        symbol="AAPL", side=OrderSide.BUY, quantity=100,
        order_type=OrderType.MARKET,
        timestamp=datetime.now(),
    )
    order_large = BrokerOrder(
        symbol="AAPL", side=OrderSide.BUY, quantity=10000,
        order_type=OrderType.MARKET,
        timestamp=datetime.now(),
    )
    bar = {"close": 100.0, "volume": 1_000_000, "timestamp": datetime.now()}

    fill_small = router.fill_simulator.simulate_fill(order_small, bar, avg_daily_volume=1_000_000)
    fill_large = router.fill_simulator.simulate_fill(order_large, bar, avg_daily_volume=1_000_000)

    # Large order should have higher impact cost (higher price for buy)
    assert fill_large.price > fill_small.price

    # Compute TCA for both
    tca = TransactionCostAnalyzer()
    market_df = __import__('pandas').DataFrame([bar])
    report_small = tca.analyze_execution(order_small, [fill_small], market_df)
    report_large = tca.analyze_execution(order_large, [fill_large], market_df)

    assert report_large.total_cost_bps > report_small.total_cost_bps


def test_multiple_broker_routing(router):
    """Test consensus routing splits order across brokers."""
    # Add second broker with lower score
    from quantumtrade.adapters.execution.broker_selector import BaseBroker

    class LowScoreBroker(BaseBroker):
        def __init__(self):
            super().__init__("low_score")
            self._is_connected = True
        def connect(self): return True
        def disconnect(self): pass
        def is_connected(self): return True
        def submit_order(self, order): return "low1"
        def cancel_order(self, broker_order_id): return True
        def get_order(self, broker_order_id): return {"status":"filled"}
        def get_fills(self, broker_order_id): return []
        def get_account_balance(self): return 1e6
        def get_position(self, symbol): return 0.0
        def get_score(self): return 0.1  # very low

    router.brokers["low"] = LowScoreBroker()
    order = BrokerOrder(
        symbol="AAPL", side=OrderSide.BUY, quantity=1000,
        order_type=OrderType.MARKET, timestamp=datetime.now(),
    )
    current_price = 100.0
    split = router.broker_selector.split_across_brokers(order, current_price, min_slice=10)
    # Should allocate primarily to high-score broker (dummy)
    assert "dummy" in split
    total = sum(split.values())
    assert total == pytest.approx(1000, rel=0.01)


def test_tca_report_consistency(router):
    """Verify TCA report fields are populated correctly."""
    order = BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=500,
        order_type=OrderType.MARKET,
        timestamp=datetime.now(),
        arrival_price=100.0,
        broker="dummy",
    )
    bar = {"close": 100.2, "volume": 1_000_000, "timestamp": datetime.now(), "bid": 100.1, "ask": 100.3}
    fill = router.fill_simulator.simulate_fill(order, bar, avg_daily_volume=1_000_000)
    assert fill is not None
    market_df = __import__('pandas').DataFrame([bar])
    tca = TransactionCostAnalyzer()
    report = tca.analyze_execution(order, [fill], market_df, pre_trade_benchmark=100.0, bid_price=100.1, ask_price=100.3)
    # Verify non-zero where expected
    assert report.filled_quantity == 500
    assert report.total_notional > 0
    assert report.explicit_commission >= 0
    # Implicit costs may be non-zero
    # Ensure report contains necessary fields
    assert hasattr(report, 'total_cost_bps')
    assert hasattr(report, 'implementation_shortfall_bps')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
