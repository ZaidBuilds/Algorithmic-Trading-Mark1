"""
conftest.py for tests/integration/ — Integration-specific fixtures.

Provides fixtures for multi-component integration tests that may involve
database, Redis, broker connections, and full pipeline execution.
These fixtures are optimized for realistic integration scenarios.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil
import os
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Database Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    """Create a test SQLite database path for the integration session."""
    tmp = tmp_path_factory.mktemp("integration_db")
    db_path = tmp / "test_integration.db"
    yield str(db_path)
    # Cleanup
    if db_path.exists():
        db_path.unlink(missing_ok=True)


@pytest.fixture
def test_db_engine(test_db_path):
    """Create a SQLAlchemy engine connected to the test database."""
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{test_db_path}")
    yield engine
    engine.dispose()


@pytest.fixture
def test_db_session(test_db_engine):
    """Provide a database session for integration tests."""
    from sqlalchemy.orm import Session
    connection = test_db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Redis Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="session")
def mock_redis_server():
    """Provide a mock Redis server for integration tests.

    Uses an in-memory mock simulating Redis Streams and pub/sub behavior.
    """
    redis_client = MagicMock()

    # Simulate Redis Streams behavior
    _streams = {}

    def _xadd(stream_name, data, maxlen=None):
        if stream_name not in _streams:
            _streams[stream_name] = []
        entry_id = f"{len(_streams[stream_name])}-0"
        _streams[stream_name].append({"id": entry_id, "data": data})
        return entry_id

    def _xread(stream_name, last_id="0", count=10):
        if stream_name not in _streams:
            return []
        entries = _streams[stream_name]
        return [(stream_name, entries[-count:])]

    redis_client.xadd.side_effect = _xadd
    redis_client.xread.side_effect = _xread
    redis_client.xgroup_create = MagicMock()
    redis_client.xreadgroup = MagicMock(return_value=[])
    redis_client.xack = MagicMock(return_value=True)
    redis_client.ping.return_value = True
    redis_client.info.return_value = {
        "used_memory": 50_000_000,
        "maxmemory": 500_000_000,
        "connected_clients": 5,
        "streams": len(_streams),
    }

    yield redis_client


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Broker Integration Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MockBrokerConnection:
    """Simulated broker connection for integration tests.

    Provides a full broker interface with realistic behavior for
    order submission, fills, and account queries.
    """

    def __init__(self, name="mock_broker", initial_cash=1_000_000.0):
        self.name = name
        self._is_connected = False
        self._cash = initial_cash
        self._positions = {}
        self._orders = {}
        self._fills = []
        self._fill_counter = 0
        self._order_counter = 0

    def connect(self):
        self._is_connected = True
        return True

    def disconnect(self):
        self._is_connected = False

    def is_connected(self):
        return self._is_connected

    def submit_order(self, order):
        self._order_counter += 1
        order_id = f"order_{self._order_counter}"
        self._orders[order_id] = {
            "order_id": order_id,
            "symbol": getattr(order, "symbol", order.get("symbol")),
            "side": getattr(order, "side", order.get("side")),
            "quantity": getattr(order, "quantity", order.get("quantity")),
            "order_type": getattr(order, "order_type", order.get("order_type")),
            "price": getattr(order, "price", order.get("price")),
            "status": "submitted",
            "timestamp": datetime.utcnow(),
        }
        return order_id

    def cancel_order(self, order_id):
        if order_id in self._orders:
            self._orders[order_id]["status"] = "cancelled"
            return True
        return False

    def get_order(self, order_id):
        return self._orders.get(order_id)

    def get_fills(self, order_id):
        return [f for f in self._fills if f["order_id"] == order_id]

    def get_all_fills(self):
        return self._fills

    def get_account_balance(self):
        return self._cash

    def get_position(self, symbol):
        return self._positions.get(symbol, {"quantity": 0, "avg_price": 0.0})

    def simulate_fill(self, order_id, fill_price=None, fill_qty=None):
        """Simulate a fill for a submitted order (for testing execution flow)."""
        if order_id not in self._orders:
            return None

        order = self._orders[order_id]
        if order["status"] not in ("submitted", "partial"):
            return None

        qty = fill_qty or order["quantity"]
        price = fill_price or order.get("price", 100.0)

        self._fill_counter += 1
        fill = {
            "fill_id": f"fill_{self._fill_counter}",
            "order_id": order_id,
            "symbol": order["symbol"],
            "side": order["side"],
            "quantity": qty,
            "price": price,
            "commission": max(1.0, qty * 0.005),
            "timestamp": datetime.utcnow(),
        }
        self._fills.append(fill)

        # Update cash and positions
        if order["side"] == "BUY":
            self._cash -= price * qty
        else:
            self._cash += price * qty

        # Update position
        sym = order["symbol"]
        if sym not in self._positions:
            self._positions[sym] = {"quantity": 0, "avg_price": 0.0}
        pos = self._positions[sym]

        if order["side"] == "BUY":
            total_cost = pos["avg_price"] * pos["quantity"] + price * qty
            pos["quantity"] += qty
            pos["avg_price"] = total_cost / pos["quantity"] if pos["quantity"] > 0 else 0
        else:
            pos["quantity"] -= qty

        # Update order status
        remaining = order["quantity"] - sum(f["quantity"] for f in self._fills if f["order_id"] == order_id)
        order["status"] = "filled" if remaining <= 0 else "partial"

        return fill


@pytest.fixture(scope="session")
def mock_broker_connection():
    """Provide a mock broker connection for integration tests."""
    broker = MockBrokerConnection()
    broker.connect()
    yield broker
    broker.disconnect()


@pytest.fixture
def mock_broker_pool():
    """Provide a pool of mock brokers for multi-broker tests."""
    pool = {
        "alpaca": MockBrokerConnection(name="alpaca", initial_cash=500_000.0),
        "binance": MockBrokerConnection(name="binance", initial_cash=250_000.0),
    }
    for b in pool.values():
        b.connect()
    yield pool
    for b in pool.values():
        b.disconnect()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Market Data Integration Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="session")
def market_data_cache():
    """Provide a shared market data cache for integration tests."""
    cache = {
        "AAPL": _generate_historical_prices("AAPL", 252, 150.0),
        "MSFT": _generate_historical_prices("MSFT", 252, 300.0),
        "GOOGL": _generate_historical_prices("GOOGL", 252, 2500.0),
        "BTC": _generate_historical_prices("BTC", 252, 42000.0),
    }
    return cache


def _generate_historical_prices(symbol, n_days, start_price):
    """Generate synthetic historical price data."""
    np_random = __import__("numpy.random")
    np_random.seed(hash(symbol) % (2**32))
    prices = start_price + np_random.randn(n_days).cumsum()
    prices = [max(p, start_price * 0.5) for p in prices]  # floor at 50% of start
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return pd.DataFrame({
        "date": dates,
        "open": prices,
        "high": [p * (1 + abs(np_random.randn() * 0.01)) for p in prices],
        "low": [p * (1 - abs(np_random.randn() * 0.01)) for p in prices],
        "close": prices,
        "volume": [int(np_random.uniform(1_000_000, 10_000_000)) for _ in prices],
    }).set_index("date")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline / Workflow Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="session")
def temp_mlflow_dir(tmp_path_factory):
    """Create a temporary directory for MLflow artifacts in integration tests."""
    tmp = tmp_path_factory.mktemp("mlflow_integration")
    yield str(tmp)
    shutil.rmtree(str(tmp), ignore_errors=True)


@pytest.fixture(scope="session")
def temp_data_dir(tmp_path_factory):
    """Create a temporary directory for data files in integration tests."""
    tmp = tmp_path_factory.mktemp("data")
    yield str(tmp)
    shutil.rmtree(str(tmp), ignore_errors=True)


@pytest.fixture
def sample_training_dataset():
    """Generate a realistic synthetic training dataset for ML pipeline tests."""
    np_random = __import__("numpy.random")
    np_random.seed(12345)
    n = 500

    dates = pd.date_range(end=datetime.utcnow(), periods=n, freq="h")
    features = pd.DataFrame({
        "open": np_random.uniform(100, 200, n),
        "high": np_random.uniform(200, 300, n),
        "low": np_random.uniform(50, 100, n),
        "close": np_random.uniform(100, 200, n),
        "volume": np_random.uniform(1000, 100000, n),
        "rsi": np_random.uniform(20, 80, n),
        "macd": np_random.randn(n),
        "bb_width": np_random.uniform(5, 30, n),
        "atr": np_random.uniform(1, 10, n),
    }, index=dates)

    # Generate target based on price movement
    returns = features["close"].pct_change().shift(-1)
    targets = (returns > 0.001).astype(int) * 2 - 1  # -1, 0, 1 style
    targets[returns.isna()] = 0
    targets[targets == 0] = np_random.choice([-1, 0, 1], size=(targets == 0).sum())
    features["target"] = targets.values

    return features


@pytest.fixture
def sample_validation_dataset():
    """Generate a validation dataset for model validator tests."""
    np_random = __import__("numpy.random")
    np_random.seed(54321)
    n = 200

    dates = pd.date_range(end=datetime.utcnow(), periods=n, freq="h")
    features = pd.DataFrame({
        "open": np_random.uniform(100, 200, n),
        "high": np_random.uniform(200, 300, n),
        "low": np_random.uniform(50, 100, n),
        "close": np_random.uniform(100, 200, n),
        "volume": np_random.uniform(1000, 100000, n),
        "rsi": np_random.uniform(20, 80, n),
        "macd": np_random.randn(n),
    }, index=dates)

    predictions = np_random.choice([1, 0, -1], size=n, p=[0.35, 0.35, 0.30])
    actuals = np_random.choice([1, 0, -1], size=n, p=[0.30, 0.40, 0.30])

    return features, predictions, actuals


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Execution Flow Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def execution_config():
    """Sample execution configuration for integration tests."""
    return {
        "slippage_model": "fixed",
        "fixed_slippage_bps": 5.0,
        "max_slippage_bps": 100.0,
        "participation_rate": 0.1,
        "default_algorithm": "twap",
        "max_order_size_pct": 0.10,
        "rebalance_interval_seconds": 60,
    }


@pytest.fixture
def market_bars():
    """Simulated market data bars for the execution window."""
    base_time = datetime(2024, 1, 2, 9, 30)
    np_random = __import__("numpy.random")
    np_random.seed(99)

    bars = []
    price = 100.0
    for i in range(60):  # 1 hour of 1-min bars
        price += np_random.randn() * 0.2
        bars.append({
            "close": round(price, 2),
            "volume": int(np_random.uniform(100_000, 2_000_000)),
            "timestamp": base_time + timedelta(minutes=i),
            "high": round(price + abs(np_random.randn() * 0.5), 2),
            "low": round(price - abs(np_random.randn() * 0.5), 2),
        })
    return bars


@pytest.fixture
def sample_risk_state():
    """Sample risk manager state for integration tests."""
    return {
        "total_equity": 1_000_000.0,
        "used_margin": 200_000.0,
        "daily_pnl": 5_000.0,
        "peak_equity": 1_050_000.0,
        "current_drawdown_pct": 0.02,
        "max_drawdown_pct": 0.08,
        "open_positions": 3,
        "daily_trades": 15,
        "var_95": 35_000.0,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Model Serving Integration Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def model_artifact_path(tmp_path_factory):
    """Create a dummy model artifact directory for serving tests."""
    artifact_dir = tmp_path_factory.mktemp("model_artifacts")
    # Create minimal MLmodel file
    (artifact_dir / "MLmodel").write_text(
        "artifact_path: model\n"
        "flavors:\n"
        "  python_function:\n"
        "    loader_module: mlflow.pyfunc\n"
    )
    # Create a minimal model file
    (artifact_dir / "model.pkl").write_bytes(b"dummy_model_data")
    yield str(artifact_dir)
    shutil.rmtree(str(artifact_dir), ignore_errors=True)


@pytest.fixture
def inference_request():
    """Sample inference request payload for serving tests."""
    return {
        "model_version": "1",
        "features": {
            "open": 150.0,
            "high": 151.5,
            "low": 149.5,
            "close": 151.0,
            "volume": 1_000_000,
            "rsi": 55.0,
            "macd": 0.5,
        },
        "strategy": "ema_crossover",
        "confidence_threshold": 0.70,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Notification / Messaging Integration Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def message_bus_integration():
    """Mock message bus for integration tests with full publish/subscribe behavior."""
    bus = MagicMock()

    _subscriptions = {}
    _published = []

    def _publish(topic, message):
        _published.append({"topic": topic, "message": message, "timestamp": datetime.utcnow()})
        # Deliver to subscribers
        if topic in _subscriptions:
            for callback in _subscriptions[topic]:
                callback(message)
        return str(len(_published))

    def _subscribe(topic, callback):
        if topic not in _subscriptions:
            _subscriptions[topic] = []
        _subscriptions[topic].append(callback)

    bus.publish.side_effect = _publish
    bus.subscribe.side_effect = _subscribe
    bus.health_check.return_value = True
    bus.published_messages = _published
    return bus


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared Fixture Imports (from root conftest)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Re-export commonly needed root fixtures for convenience
from conftest import (  # noqa: F401, E402
    mock_broker,
    mock_broker_factory,
    mock_message_bus,
    mock_db_session,
    mock_db_engine,
    mock_redis_client,
    mock_fill_simulator,
    mock_broker_selector,
    mock_predictor,
    mock_registry,
    serving_test_client,
    base_event_data,
    market_data_event_data,
    signal_event_data,
    order_event_data,
    trade_event_data,
    sample_ohlcv_bars,
    sample_ohlcv_dataframe,
    sample_trades,
    sample_portfolio_state,
    sample_account_info,
    sample_strategy_config,
    sample_market_data,
    sample_indicators,
    sample_backtest_trades,
    sample_equity_curve,
    risk_limits,
    dummy_broker,
    router_brokers,
    mock_broker_connection,
    tca_analyzer,
    tca_buy_order,
    tca_sell_order,
)