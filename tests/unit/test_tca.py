"""
Unit tests for Transaction Cost Analysis.

Tests cover cost breakdowns, benchmarks, and TCA report generation.
"""

import pytest
import pandas as pd
from datetime import datetime

from quantumtrade.adapters.execution.models import (
    BrokerOrder,
    Fill,
    OrderSide,
    OrderType,
    AlgorithmType,
)
from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer


@pytest.fixture
def tca():
    return TransactionCostAnalyzer(benchmark="arrival", spread_model="mid")


@pytest.fixture
def buy_order():
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        order_type=OrderType.MARKET,
        algorithm=AlgorithmType.TWAP,
        timestamp=datetime(2024, 1, 1, 9, 30),
        arrival_price=150.0,
    )


@pytest.fixture
def sell_order():
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=1000,
        order_type=OrderType.MARKET,
        algorithm=AlgorithmType.TWAP,
        timestamp=datetime(2024, 1, 1, 10, 0),
        arrival_price=150.0,
    )


@pytest.fixture
def sample_fill():
    return Fill(
        fill_id="f1",
        order_id="o1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        price=151.0,  # 1.0 higher than arrival (100bps on 150? Actually (151-150)/150=0.00667=66.7bps)
        trade_timestamp=datetime.now(),
        received_timestamp=datetime.now(),
        broker="test",
    )


class TestTCACalculations:
    """Test cost calculation methods individually."""

    def test_slippage_calculation_buy(self, tca, buy_order):
        arrival = 150.0
        avg_price = 151.0
        slippage_dollars, slippage_bps = tca.calculate_slippage(
            side=OrderSide.BUY,
            arrival_price=arrival,
            avg_fill_price=avg_price,
            quantity=1000,
        )
        # Slippage = price increase * qty
        expected_dollars = (151.0 - 150.0) * 1000
        expected_bps = ((151.0 - 150.0) / 150.0) * 10000
        assert slippage_dollars == pytest.approx(expected_dollars)
        assert slippage_bps == pytest.approx(expected_bps)

    def test_slippage_calculation_sell(self, tca, sell_order):
        arrival = 150.0
        avg_price = 149.0  # sell lower → adverse
        slippage_dollars, slippage_bps = tca.calculate_slippage(
            side=OrderSide.SELL,
            arrival_price=arrival,
            avg_fill_price=avg_price,
            quantity=1000,
        )
        # For sell, lower price is bad → slippage positive
        expected_dollars = -(avg_price - arrival) * 1000  # = (arrival-avg)*qty
        expected_dollars = (150 - 149) * 1000
        expected_bps = ((150 - 149) / 150) * 10000
        assert slippage_dollars == pytest.approx(expected_dollars)
        assert slippage_bps == pytest.approx(expected_bps)

    def test_market_impact_calculation(self, tca):
        # Permanent impact: (post - arrival) * qty
        impact_dollars, impact_bps = tca._calculate_market_impact(
            side=OrderSide.BUY,
            arrival_price=150.0,
            post_trade_price=151.0,
            quantity=1000,
            avg_daily_volume=1_000_000,
        )
        expected_dollars = (151.0 - 150.0) * 1000
        expected_bps = ((151.0 - 150.0) / 150.0) * 10000
        assert impact_dollars == pytest.approx(expected_dollars)
        assert impact_bps == pytest.approx(expected_bps)


class TestTransactionCostReport:
    """Test full report generation."""

    def test_analyze_execution_buy(self, tca, buy_order):
        # Create fill
        fill = Fill(
            fill_id="f1",
            order_id=buy_order.order_id or "o1",
            symbol=buy_order.symbol,
            side=buy_order.side,
            quantity=1000,
            price=151.0,
            trade_timestamp=datetime.now(),
            received_timestamp=datetime.now(),
            broker="test_broker",
        )
        # Market data (single bar)
        market_data = pd.DataFrame([{"Close": 150.0, "Volume": 1_000_000}])
        report = tca.analyze_execution(
            order=buy_order,
            fills=[fill],
            market_data=market_data,
            pre_trade_benchmark=150.0,
            post_trade_benchmark=150.0,
        )
        # Check fields exist and are meaningful
        assert report.filled_quantity == 1000
        assert report.implicit_slippage_bps > 0  # bought higher than arrival
        assert report.total_cost_bps > 0

    def test_analyze_execution_sell(self, tca, sell_order):
        fill = Fill(
            fill_id="f2",
            order_id=sell_order.order_id or "o2",
            symbol=sell_order.symbol,
            side=sell_order.side,
            quantity=1000,
            price=149.0,
            trade_timestamp=datetime.now(),
            received_timestamp=datetime.now(),
            broker="test_broker",
        )
        market_data = pd.DataFrame([{"Close": 150.0, "Volume": 1_000_000}])
        report = tca.analyze_execution(
            order=sell_order,
            fills=[fill],
            market_data=market_data,
            pre_trade_benchmark=150.0,
            post_trade_benchmark=150.0,
        )
        assert report.implicit_slippage_bps > 0  # sold lower than arrival

    def test_empty_fills(self, tca, buy_order):
        report = tca.analyze_execution(buy_order, [], pd.DataFrame())
        assert report.filled_quantity == 0
        assert report.total_cost_bps == 0.0


class TestBenchmarkHandling:
    """Test different benchmark selection."""

    def test_benchmark_arrival(self, buy_order):
        tca = TransactionCostAnalyzer(benchmark="arrival")
        assert tca.benchmark_type == "arrival"

    def test_benchmark_mid(self):
        tca = TransactionCostAnalyzer(benchmark="pre_mid")
        assert tca.benchmark_type == "pre_mid"


class TestImplementationShortfall:
    """Test implementation shortfall calculation."""

    def test_shortfall_buy(self):
        from quantumtrade.adapters.execution.cost_models import calculate_implementation_shortfall
        res = calculate_implementation_shortfall(
            arrival_price=150.0,
            average_fill_price=151.0,
            side=OrderSide.BUY,
            quantity=1000,
        )
        assert res["shortfall_dollars"] == pytest.approx(-1000.0)
        assert res["shortfall_bps"] == pytest.approx(-66.6667)  # negative adverse for buy

    def test_shortfall_sell(self):
        from quantumtrade.adapters.execution.cost_models import calculate_implementation_shortfall
        res = calculate_implementation_shortfall(
            arrival_price=150.0,
            average_fill_price=149.0,
            side=OrderSide.SELL,
            quantity=1000,
        )
        # Sell lower → adverse, positive shortfall
        assert res["shortfall_dollars"] == pytest.approx(1000.0)
        assert res["shortfall_bps"] == pytest.approx(66.6667)


class TestTCAComparison:
    """Compare multiple executions (used by backtest)."""

    def test_compare_algorithms(self, tca):
        orders = []
        fills_dict = {}
        market_data = {}

        # Two dummy orders
        for i in range(2):
            order = BrokerOrder(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=1000,
                order_type=OrderType.MARKET,
                algorithm=AlgorithmType.TWAP,
                timestamp=datetime.now(),
                arrival_price=150.0,
            )
            orders.append(order)
            fill = Fill(
                fill_id=f"f{i}",
                order_id=order.order_id,
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=1000,
                price=151.0,
                trade_timestamp=datetime.now(),
                received_timestamp=datetime.now(),
                broker="test",
            )
            fills_dict[order.order_id] = [fill]
            market_data["AAPL"] = pd.DataFrame([{"Close": 150.0, "Volume": 1_000_000}])

        df = tca.compare_algorithms(orders, fills_dict, market_data)
        assert len(df) == 2
        assert "total_cost_bps" in df.columns
