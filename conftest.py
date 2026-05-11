"""
Root conftest.py — Shared fixtures for the QuantumTrade test suite.

Provides reusable fixtures for broker mocks, event factories, test data,
and other shared test infrastructure across unit and integration tests.
"""

import pytest
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from uuid import uuid4
import numpy as np
import pandas as pd

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture(scope="session")
def event_loop():
    """Create a new event loop for async tests."""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()
    except Exception:
        yield None


# ─── Broker Mocks ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_broker():
    """Create a generic mocked broker."""
    broker = Mock()
    broker.name = "mock_broker"
    broker.is_connected = True
    broker.paper = True
    broker.submit_order.return_value = "test_order_id"
    broker.cancel_order.return_value = True
    broker.get_order.return_value = {
        "order_id": "test_order_id",
        "status": "filled",
        "filled_quantity": 100,
        "fill_price": 150.0,
    }
    broker.get_fills.return_value = []
    broker.get_account_balance.return_value = 1_000_000.0
    broker.get_position.return_value = 0.0
    return broker


@pytest.fixture
def mock_broker_factory():
    """Factory fixture to create mock brokers with custom attributes."""

    def _create(
        name="mock_broker",
        connected=True,
        paper=True,
        balance=1_000_000.0,
        submit_order_return="test_order_id",
    ):
        broker = Mock()
        broker.name = name
        broker.is_connected = connected
        broker.paper = paper
        broker.submit_order.return_value = submit_order_return
        broker.cancel_order.return_value = True
        broker.get_order.return_value = {
            "order_id": submit_order_return,
            "status": "filled",
            "filled_quantity": 100,
            "fill_price": 150.0,
        }
        broker.get_fills.return_value = []
        broker.get_account_balance.return_value = balance
        broker.get_position.return_value = 0.0
        return broker

    return _create


# ─── Event Factories ─────────────────────────────────────────────────────────

@pytest.fixture
def base_event_data():
    """Minimal data dict for a BaseEvent."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "test_source",
        "version": "1.0",
    }


@pytest.fixture
def market_data_event_data():
    """Sample market data event payload."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "market_data_feed",
        "version": "1.0",
        "symbol": "AAPL",
        "timeframe": "1m",
        "ohlcv": {
            "open": 150.0,
            "high": 151.5,
            "low": 149.5,
            "close": 151.0,
            "volume": 1_000_000,
        },
    }


@pytest.fixture
def signal_event_data():
    """Sample signal event payload."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "strategy",
        "version": "1.0",
        "symbol": "AAPL",
        "signal_type": "buy",
        "confidence": 0.85,
        "strategy": "ema_crossover",
        "price": 151.0,
    }


@pytest.fixture
def order_event_data():
    """Sample order event payload."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "portfolio_manager",
        "version": "1.0",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 100,
        "order_type": "market",
        "price": 151.0,
    }


@pytest.fixture
def trade_event_data():
    """Sample trade event payload."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "execution_engine",
        "version": "1.0",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 100,
        "price": 150.5,
        "commission": 1.0,
        "broker": "alpaca",
    }


@pytest.fixture
def risk_event_data():
    """Sample risk event payload."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "risk_manager",
        "version": "1.0",
        "event_type": "position_limit_warning",
        "symbol": "AAPL",
        "current_exposure": 500_000.0,
        "limit": 1_000_000.0,
        "utilization_pct": 50.0,
    }


@pytest.fixture
def system_event_data():
    """Sample system event payload."""
    return {
        "event_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "source": "system",
        "version": "1.0",
        "event_type": "heartbeat",
        "status": "healthy",
        "uptime_seconds": 3600,
    }


# ─── Market Data ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ohlcv_bars():
    """Generate a list of OHLCV bars for testing."""
    base_time = datetime(2024, 1, 2, 9, 30)
    bars = []
    price = 150.0
    for i in range(60):
        open_price = price + np.random.randn() * 0.1
        close_price = open_price + np.random.randn() * 0.5
        high_price = max(open_price, close_price) + abs(np.random.randn() * 0.2)
        low_price = min(open_price, close_price) - abs(np.random.randn() * 0.2)
        volume = int(np.random.uniform(100_000, 1_000_000))
        bars.append({
            "timestamp": base_time + timedelta(minutes=i),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": volume,
        })
        price = close_price
    return bars


@pytest.fixture
def sample_ohlcv_dataframe(sample_ohlcv_bars):
    """Convert sample bars into a pandas DataFrame."""
    df = pd.DataFrame(sample_ohlcv_bars)
    df.set_index("timestamp", inplace=True)
    return df


@pytest.fixture
def sample_trades():
    """Generate sample trade fills for TCA and backtesting."""
    base_time = datetime(2024, 1, 2, 9, 30)
    return [
        {
            "trade_id": str(uuid4()),
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "price": 150.0 + i * 0.05,
            "timestamp": base_time + timedelta(minutes=i),
            "commission": 1.0,
            "broker": "alpaca",
        }
        for i in range(10)
    ]


# ─── Portfolio & Account ─────────────────────────────────────────────────────

@pytest.fixture
def sample_portfolio_state():
    """Sample portfolio state dict."""
    return {
        "total_equity": 1_000_000.0,
        "cash": 500_000.0,
        "positions": {
            "AAPL": {
                "quantity": 500,
                "avg_price": 150.0,
                "market_value": 75_000.0,
                "unrealized_pnl": 2_500.0,
            },
            "MSFT": {
                "quantity": 200,
                "avg_price": 300.0,
                "market_value": 60_000.0,
                "unrealized_pnl": -1_000.0,
            },
        },
        "day_pnl": 1_500.0,
        "total_pnl": 5_000.0,
    }


@pytest.fixture
def sample_account_info():
    """Sample account info object."""
    return {
        "account_id": str(uuid4()),
        "cash": 500_000.0,
        "portfolio_value": 1_000_000.0,
        "buying_power": 1_000_000.0,
        "equity": 1_000_000.0,
        "last_equity": 995_000.0,
        "multiplier": 1.0,
    }


# ─── Settings / Config ───────────────────────────────────────────────────────

@pytest.fixture
def mock_settings():
    """Mock application settings."""
    settings = Mock()
    settings.DEBUG = True
    settings.ENVIRONMENT = "test"
    settings.DATABASE_URL = "sqlite:///test.db"
    settings.REDIS_URL = "redis://localhost:6379/1"
    settings.ALPACA_API_KEY = "test_key"
    settings.ALPACA_API_SECRET = "test_secret"
    settings.ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
    settings.BINANCE_API_KEY = "test_key"
    settings.BINANCE_API_SECRET = "test_secret"
    settings.RISK_MAX_POSITION_PCT = 0.25
    settings.RISK_STOP_LOSS_PCT = 0.02
    settings.RISK_MAX_DRAWDOWN_PCT = 0.10
    settings.TRADING_MODE = "paper"
    settings.LOG_LEVEL = "DEBUG"
    settings.ML_MODEL_REGISTRY_URI = "/tmp/mlflow_test"
    settings.OTEL_EXPORTER_JAEGER_ENDPOINT = "http://localhost:14268/api/traces"
    settings.TELEGRAM_BOT_TOKEN = "test_token"
    settings.TELEGRAM_CHAT_ID = "test_chat_id"
    return settings


# ─── Message Bus ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_message_bus():
    """Mock message/event bus."""
    bus = MagicMock()
    bus.publish.return_value = str(uuid4())
    bus.subscribe.return_value = None
    bus.health_check.return_value = True
    bus.get_queue_size.return_value = 0
    return bus


# ─── Database ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.filter.return_value.first.return_value = None
    session.query.return_value.filter.return_value.count.return_value = 0
    session.add = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def mock_db_engine():
    """Mock SQLAlchemy engine."""
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(
        return_value=MagicMock(execute=Mock())
    )
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    return engine


# ─── Redis ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = MagicMock()
    client.ping.return_value = True
    client.get.return_value = None
    client.set.return_value = True
    client.delete.return_value = 1
    client.incr.return_value = 1
    client.lpush.return_value = 1
    client.rpop.return_value = None
    client.pubsub.return_value = MagicMock()
    client.info.return_value = {
        "used_memory": 10_000_000,
        "maxmemory": 1_000_000_000,
        "connected_clients": 10,
    }
    return client


# ─── Execution Engine ────────────────────────────────────────────────────────

@pytest.fixture
def mock_fill_simulator():
    """Mock fill simulator."""
    simulator = MagicMock()
    simulator.simulate_fill.return_value = Mock(
        fill_price=150.0,
        quantity_filled=100,
        commission=1.0,
        slippage_bps=1.5,
        fill_time=0.001,
        success=True,
    )
    return simulator


@pytest.fixture
def mock_broker_selector():
    """Mock broker selector."""
    selector = MagicMock()
    selector.select_broker.return_value = Mock(
        name="best_broker",
        score=0.95,
        is_connected=True,
    )
    selector.get_all_brokers.return_value = {}
    return selector


# ─── ML / MLOps ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow tracking client with comprehensive method mocks."""
    client = MagicMock()

    # Experiment mocks
    mock_exp = Mock()
    mock_exp.experiment_id = "0"
    mock_exp.name = "test_experiment"
    mock_exp.artifact_location = "/tmp/mlflow/artifacts"
    client.get_experiment_by_name.return_value = mock_exp
    client.get_experiment.return_value = mock_exp
    client.list_experiments.return_value = [mock_exp]
    client.create_experiment.return_value = "0"

    # Run mocks
    mock_run = Mock()
    mock_run.info.run_id = "test_run_id"
    mock_run.info.experiment_id = "0"
    mock_run.info.start_time = int(datetime.utcnow().timestamp() * 1000)
    mock_run.data.params = {}
    mock_run.data.metrics = {}
    mock_run.data.tags = {}
    client.create_run.return_value = mock_run
    client.get_run.return_value = mock_run
    client.search_runs.return_value = [mock_run]

    # Model version mocks
    mock_version = Mock()
    mock_version.version = "1"
    mock_version.current_stage = "Staging"
    mock_version.source = "artifacts/model"
    client.search_model_versions.return_value = [mock_version]
    client.get_model_version.return_value = mock_version
    client.transition_model_version_stage.return_value = mock_version
    client.create_model_version.return_value = mock_version
    client.update_model_version.return_value = mock_version
    client.delete_model_version.return_value = {}

    # Registered model mocks
    mock_model = Mock()
    mock_model.name = "test_model"
    client.search_registered_models.return_value = [mock_model]
    client.get_registered_model.return_value = mock_model
    client.create_registered_model.return_value = mock_model
    client.update_registered_model.return_value = mock_model
    client.delete_registered_model.return_value = {}

    # Log/artifact mocks
    client.log_param = Mock()
    client.log_metric = Mock()
    client.log_text = Mock()
    client.log_artifact = Mock()
    client.log_artifacts = Mock()
    client.log_batch = Mock()

    # Set tracking URI
    client.set_tracking_uri = Mock()
    client.set_registry_uri = Mock()

    return client


@pytest.fixture
def sample_training_data():
    """Generate synthetic training data for ML tests."""
    np.random.seed(42)
    n_samples = 1000
    dates = pd.date_range(end=datetime.utcnow(), periods=n_samples, freq="h")

    features = pd.DataFrame({
        "timestamp": dates,
        "open": np.random.uniform(100, 200, n_samples),
        "high": np.random.uniform(100, 200, n_samples),
        "low": np.random.uniform(100, 200, n_samples),
        "close": np.random.uniform(100, 200, n_samples),
        "volume": np.random.uniform(1000, 100000, n_samples),
        "rsi": np.random.uniform(20, 80, n_samples),
        "macd": np.random.randn(n_samples),
        "bb_upper": np.random.uniform(200, 250, n_samples),
        "bb_lower": np.random.uniform(50, 100, n_samples),
    })
    features.set_index("timestamp", inplace=True)

    # Target: 1 for buy signal, 0 for sell, -1 for hold
    targets = np.random.choice([1, 0, -1], size=n_samples, p=[0.3, 0.3, 0.4])

    return features, targets


@pytest.fixture
def sample_model_input():
    """Sample input features for model inference tests."""
    return pd.DataFrame({
        "open": [150.0],
        "high": [151.5],
        "low": [149.5],
        "close": [151.0],
        "volume": [1_000_000],
        "rsi": [55.0],
        "macd": [0.5],
        "bb_upper": [160.0],
        "bb_lower": [140.0],
    })


# ─── Test Data Helpers ───────────────────────────────────────────────────────

@pytest.fixture
def temp_dir():
    """Create and return a temporary directory path (auto-cleanup not guaranteed)."""
    import tempfile
    tmp = tempfile.mkdtemp()
    yield tmp


@pytest.fixture
def sample_csv_path(tmp_path_factory):
    """Create a sample OHLCV CSV file for data loading tests."""
    tmp = tmp_path_factory.mktemp("data")
    csv_path = tmp / "test_data.csv"

    np.random.seed(123)
    n = 100
    dates = pd.date_range(start="2023-01-01", periods=n, freq="1d")
    df = pd.DataFrame({
        "Date": dates,
        "Open": np.random.uniform(100, 200, n),
        "High": np.random.uniform(200, 300, n),
        "Low": np.random.uniform(50, 100, n),
        "Close": np.random.uniform(100, 200, n),
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    })
    df.to_csv(csv_path, index=False)
    return str(csv_path)


# ─── Utilities ────────────────────────────────────────────────────────────────

@pytest.fixture
def freeze_time():
    """Factory fixture to freeze time at a specific datetime.

    Usage:
        now = freeze_time()
        with now("2024-01-15 10:00:00"):
            # time-dependent code here
    """
    from unittest.mock import patch

    def _freeze(time_str_or_dt):
        if isinstance(time_str_or_dt, str):
            target = datetime.fromisoformat(time_str_or_dt)
        else:
            target = time_str_or_dt

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return target

            @classmethod
            def utcnow(cls):
                return target

        return patch("datetime.datetime", FrozenDatetime)

    return _freeze


@pytest.fixture(autouse=True)
def _default_test_settings(mock_settings, mock_redis_client):
    """Auto-apply default mock settings and redis for all tests in scope."""
    # Patch config.settings.settings globally for tests
    with patch("config.settings.settings", mock_settings), \
         patch("config.settings.redis_client", mock_redis_client):
        yield