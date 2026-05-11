"""
conftest.py for tests/unit/ — Unit-specific fixtures.

Provides lightweight, in-process fixtures optimized for fast unit tests.
Each fixture is self-contained and does not require external services (Redis,
database, broker connections, etc.).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _default_test_settings():
    """Override the root conftest autouse fixture to avoid patching config.settings.redis_client.

    The root conftest's `_default_test_settings` patches `config.settings.redis_client`
    which fails because `config.settings` does not have that attribute at import time.
    This empty override prevents that fixture from running for unit tests.
    """
    yield


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Drift Detection Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def drift_detector():
    """Create a DriftDetector with test-friendly thresholds."""
    from quantumtrade.mlops.drift_detector import DriftDetector
    return DriftDetector(
        psi_threshold=0.2,
        ks_alpha=0.05,
        js_threshold=0.1,
        window_size=100,
    )


@pytest.fixture
def baseline_data():
    """Generate stable baseline distribution (seeded for reproducibility)."""
    np.random.seed(42)
    return np.random.normal(0, 1, 1000)


@pytest.fixture
def shifted_data():
    """Generate distribution with mean shift to trigger drift."""
    np.random.seed(43)
    return np.random.normal(1, 1, 1000)


@pytest.fixture
def identical_data():
    """Generate identical distribution (no drift expected)."""
    np.random.seed(42)
    return np.random.normal(0, 1, 1000)


@pytest.fixture
def baseline_features(baseline_data):
    """Baseline features dict mapping column name to array."""
    return {"feature1": baseline_data}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Feature Store / ML Pipeline Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def sample_feature_matrix():
    """Create a sample feature matrix DataFrame for ML tests."""
    np.random.seed(42)
    n = 500
    return pd.DataFrame({
        "timestamp": pd.date_range(end=datetime.utcnow(), periods=n, freq="h"),
        "open": np.random.uniform(100, 200, n),
        "high": np.random.uniform(200, 300, n),
        "low": np.random.uniform(50, 100, n),
        "close": np.random.uniform(100, 200, n),
        "volume": np.random.uniform(1000, 100000, n),
        "rsi": np.random.uniform(20, 80, n),
        "macd": np.random.randn(n),
        "target": np.random.choice([1, 0, -1], size=n, p=[0.3, 0.3, 0.4]),
    }).set_index("timestamp")


@pytest.fixture
def mock_feature_store():
    """Mock feature store that returns canned data."""
    store = MagicMock()
    store.get_latest_features.return_value = pd.DataFrame({
        "open": [150.0],
        "high": [151.5],
        "low": [149.5],
        "close": [151.0],
        "volume": [1_000_000],
        "rsi": [55.0],
        "macd": [0.5],
    })
    store.get_features_range.return_value = (
        datetime(2024, 1, 1),
        datetime(2024, 1, 31),
    )
    store.is_stale.return_value = False
    return store


@pytest.fixture
def mock_online_feature_store():
    """Mock online feature store interface."""
    from quantumtrade.mlops.features.online import OnlineFeatureStore
    store = MagicMock(spec=OnlineFeatureStore)
    store.get_features.return_value = pd.DataFrame({
        "open": [150.0],
        "high": [151.0],
        "low": [149.0],
        "close": [150.5],
        "volume": [1000000],
    })
    store.get_many_features.return_value = pd.DataFrame()
    return store


@pytest.fixture
def mock_feature_registry():
    """Mock feature registry."""
    registry = MagicMock()
    registry.get_feature.return_value = {
        "name": "rsi_14",
        "sql": "SELECT rsi FROM indicators WHERE window=14",
        "version": 1,
    }
    registry.list_features.return_value = []
    return registry


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MLflow / Model Registry Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_mlflow_client():
    """Create a mocked MLflow MlflowClient with full method coverage.

    Reuses the more complete version from root conftest if available,
    but provides a standalone default for unit test isolation.
    """
    client = MagicMock()

    # Experiment
    mock_exp = MagicMock()
    mock_exp.experiment_id = "0"
    mock_exp.name = "test_experiment"
    mock_exp.artifact_location = "/tmp/mlflow/artifacts"
    client.get_experiment_by_name.return_value = mock_exp
    client.get_experiment.return_value = mock_exp
    client.create_experiment.return_value = "0"

    # Run
    mock_run = MagicMock()
    mock_run.info.run_id = "test_run_id"
    mock_run.info.experiment_id = "0"
    mock_run.data.params = {}
    mock_run.data.metrics = {}
    mock_run.data.tags = {}
    client.create_run.return_value = mock_run
    client.get_run.return_value = mock_run
    client.search_runs.return_value = [mock_run]

    # Model version
    mock_version = MagicMock()
    mock_version.version = "1"
    mock_version.current_stage = "Staging"
    client.search_model_versions.return_value = [mock_version]
    client.get_model_version.return_value = mock_version
    client.transition_model_version_stage.return_value = mock_version
    client.create_model_version.return_value = mock_version

    # Registered model
    mock_model = MagicMock()
    mock_model.name = "test_model"
    client.search_registered_models.return_value = [mock_model]
    client.get_registered_model.return_value = mock_model
    client.create_registered_model.return_value = mock_model

    # Logging
    client.log_param = MagicMock()
    client.log_metric = MagicMock()
    client.log_text = MagicMock()
    client.log_artifact = MagicMock()
    client.log_artifacts = MagicMock()
    client.set_tracking_uri = MagicMock()
    client.set_registry_uri = MagicMock()

    return client


@pytest.fixture
def mock_mlflow_context():
    """Patch mlflow module-level functions for unit tests."""
    import mlflow
    with patch("mlflow.set_tracking_uri"), \
         patch("mlflow.start_run"), \
         patch("mlflow.log_param"), \
         patch("mlflow.log_metric"), \
         patch("mlflow.log_artifact"), \
         patch("mlflow.log_text"), \
         patch("mlflow.set_tag"):
        yield


@pytest.fixture
def mock_model():
    """Create a mock trained sklearn model."""
    from unittest.mock import Mock
    model = Mock()
    model.predict.return_value = [1]
    model.predict_proba.return_value = [[0.15, 0.70, 0.15]]
    model.score.return_value = 0.85
    model.get_params.return_value = {"n_estimators": 100}
    return model


@pytest.fixture
def sample_model_version():
    """Sample ModelVersion dataclass/dict for registry tests."""
    return {
        "version": "1",
        "model_name": "price_predictor",
        "run_id": "abc123",
        "stage": "Staging",
        "accuracy": 0.85,
        "created_at": datetime.utcnow(),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Model Serving (FastAPI) Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_predictor():
    """Create a mocked Predictor with canned responses."""
    from quantumtrade.mlops.serving.predictor import PredictionResponse
    predictor = MagicMock()
    predictor.predict.return_value = PredictionResponse(
        prediction=1,
        confidence=0.85,
        model_version="1",
        timestamp=datetime.utcnow(),
        latency_ms=5.2,
    )
    predictor.get_metrics.return_value = {
        "predictions_total": 100,
        "cache_hits": 50,
        "cache_hit_rate": 0.5,
    }
    predictor.cache_hits = 50
    predictor.cache_misses = 50
    predictor.clear_cache = MagicMock()
    predictor.health_check.return_value = True
    return predictor


@pytest.fixture
def mock_registry():
    """Create a mocked ModelRegistry."""
    registry = MagicMock()
    registry.list_models.return_value = []
    registry.list_versions.return_value = []
    registry.list_versions_in_stage.return_value = []
    registry.get_latest_model.return_value = None
    registry.get_model.return_value = None
    registry.register_model.return_value = "v1"
    registry.transition_stage.return_value = True
    registry.get_metrics.return_value = {"accuracy": 0.85}
    return registry


@pytest.fixture
def serving_test_client(mock_registry, mock_predictor):
    """Create a FastAPI TestClient with mocked dependencies for serving tests.

    Patches module-level variables in the server module so the test client
    operates with deterministic, in-memory mocks.
    """
    from unittest.mock import patch
    from fastapi.testclient import TestClient

    with patch("quantumtrade.mlops.serving.server.registry", mock_registry), \
         patch("quantumtrade.mlops.serving.server.predictor", mock_predictor), \
         patch("quantumtrade.mlops.serving.server.startup_event", lambda: None):
        from quantumtrade.mlops.serving.server import app as fastapi_app
        client = TestClient(fastapi_app)
        yield client


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Execution / Order Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def sample_broker_order():
    """Create a sample BrokerOrder for execution tests."""
    from quantumtrade.adapters.execution.models import BrokerOrder, OrderSide
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        order_type="MARKET",
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_limit_order():
    """Create a sample limit order."""
    from quantumtrade.adapters.execution.models import BrokerOrder, OrderSide
    return BrokerOrder(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=500,
        order_type="LIMIT",
        timestamp=datetime.now(),
        price=155.0,
    )


@pytest.fixture
def sample_ohlcv_bar():
    """Create a single OHLCV bar dict for fill simulation tests."""
    return {
        "close": 150.0,
        "volume": 1_000_000,
        "timestamp": datetime(2024, 1, 2, 9, 30),
        "high": 151.0,
        "low": 149.0,
    }


@pytest.fixture
def sample_fill_response():
    """Mock fill response from broker."""
    return MagicMock(
        fill_id="fill_123",
        order_id="order_456",
        symbol="AAPL",
        quantity=100,
        price=150.5,
        commission=1.0,
        timestamp=datetime.utcnow(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TCA (Transaction Cost Analysis) Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def tca_analyzer():
    """Create a TransactionCostAnalyzer instance."""
    from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer
    return TransactionCostAnalyzer(benchmark="arrival", spread_model="mid")


@pytest.fixture
def tca_buy_order():
    """Buy order for TCA tests."""
    from quantumtrade.adapters.execution.models import (
        BrokerOrder, OrderSide, OrderType, AlgorithmType,
    )
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
def tca_sell_order():
    """Sell order for TCA tests."""
    from quantumtrade.adapters.execution.models import (
        BrokerOrder, OrderSide, OrderType, AlgorithmType,
    )
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
def tca_sample_fill():
    """Sample fill for TCA tests."""
    from quantumtrade.adapters.execution.models import Fill, OrderSide
    return Fill(
        fill_id="f1",
        order_id="o1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=1000,
        price=151.0,  # 1.0 higher than arrival (66.7bps on 150)
        commission=1.0,
        timestamp=datetime(2024, 1, 1, 9, 35),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Backtesting Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def sample_backtest_trades():
    """Sample completed trades for backtesting metrics."""
    from quantumtrade.backtesting.metrics import Trade
    return [
        Trade(
            entry_time=datetime(2024, 1, 2, 9, 30),
            exit_time=datetime(2024, 1, 2, 10, 0),
            entry_price=150.0,
            exit_price=152.0,
            quantity=100,
            side="BUY",
            pnl=200.0,
            pnl_pct=1.33,
            commission=2.0,
        ),
        Trade(
            entry_time=datetime(2024, 1, 2, 10, 0),
            exit_time=datetime(2024, 1, 2, 10, 30),
            entry_price=152.0,
            exit_price=151.0,
            quantity=100,
            side="SELL",
            pnl=-100.0,
            pnl_pct=-0.66,
            commission=2.0,
        ),
    ]


@pytest.fixture
def sample_equity_curve():
    """Sample equity curve DataFrame for backtesting."""
    dates = pd.date_range(start="2024-01-02", periods=100, freq="min")
    equity = 100_000 + np.cumsum(np.random.randn(100) * 100)
    return pd.DataFrame({
        "timestamp": dates,
        "equity": equity,
        "returns": np.random.randn(100) * 0.001,
    }).set_index("timestamp")


@pytest.fixture
def sample_benchmark_returns():
    """Sample benchmark returns for performance comparison."""
    return pd.Series(
        np.random.randn(252) * 0.001,
        index=pd.date_range(start="2024-01-01", periods=252, freq="B"),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Risk Management Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def sample_position():
    """Create a sample position dict for risk tests."""
    return MagicMock(
        symbol="AAPL",
        quantity=500,
        avg_price=150.0,
        current_price=155.0,
        market_value=77_500.0,
        unrealized_pnl=2_500.0,
    )


@pytest.fixture
def sample_positions():
    """Create a list of sample positions."""
    return [
        MagicMock(symbol="AAPL", quantity=500, avg_price=150.0, market_value=77_500.0),
        MagicMock(symbol="MSFT", quantity=200, avg_price=300.0, market_value=60_000.0),
        MagicMock(symbol="GOOGL", quantity=100, avg_price=2500.0, market_value=250_000.0),
    ]


@pytest.fixture
def risk_limits():
    """Sample risk limits configuration."""
    return {
        "max_position_pct": 0.25,
        "max_portfolio_pct": 0.80,
        "stop_loss_pct": 0.02,
        "max_drawdown_pct": 0.10,
        "var_limit": 50_000.0,
        "max_correlation": 0.85,
        "sector_limit_pct": 0.40,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Smart Order Router Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def dummy_broker():
    """Create a minimal dummy broker for router tests.

    Uses MagicMock to auto-handle any attribute access or method calls,
    with sensible defaults for common broker operations.
    """
    broker = MagicMock()
    broker.name = "dummy"
    broker.score = 1.0
    broker._is_connected = True
    broker.is_connected.return_value = True
    broker.submit_order.return_value = "dummy_order_1"
    broker.cancel_order.return_value = True
    broker.get_order.return_value = {"status": "filled"}
    broker.get_fills.return_value = []
    broker.get_account_balance.return_value = 1_000_000.0
    broker.get_position.return_value = 0.0
    return broker


@pytest.fixture
def router_brokers(dummy_broker):
    """Dict of brokers for router initialization."""
    return {"dummy": dummy_broker}


@pytest.fixture
def mock_broker_selector(router_brokers):
    """Mock BrokerSelector that returns pre-configured brokers."""
    from quantumtrade.adapters.execution.broker_selector import BrokerSelector
    selector = MagicMock(spec=BrokerSelector)
    selector.brokers = router_brokers
    selector.select_broker.return_value = dummy_broker
    selector.get_broker.return_value = dummy_broker
    selector.get_all_brokers.return_value = router_brokers
    return selector


@pytest.fixture
def sample_market_bars():
    """Simulated market data bars for execution window."""
    base_time = datetime(2024, 1, 2, 9, 30)
    bars = []
    price = 100.0
    for i in range(10):
        price += 0.1  # slight upward drift
        bars.append({
            "close": round(price, 2),
            "volume": 500_000,
            "timestamp": base_time + timedelta(minutes=i),
            "high": round(price + 0.5, 2),
            "low": round(price - 0.5, 2),
        })
    return bars


@pytest.fixture
def mock_fill_simulator():
    """Mock FillSimulator with deterministic behavior."""
    simulator = MagicMock()
    simulator.simulate_fill.return_value = MagicMock(
        fill_price=150.0,
        quantity_filled=100,
        commission=1.0,
        slippage_bps=1.5,
        fill_time=0.001,
        success=True,
        timestamp=datetime.utcnow(),
    )
    simulator.simulate_allocation.return_value = [
        MagicMock(
            fill_price=150.0,
            quantity_filled=50,
            commission=0.5,
            timestamp=datetime.utcnow(),
        )
    ]
    return simulator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Strategy Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def sample_strategy_config():
    """Sample strategy configuration dict."""
    return {
        "name": "ema_crossover",
        "type": "technical",
        "parameters": {
            "fast_period": 9,
            "slow_period": 21,
            "signal_period": 9,
        },
        "risk": {
            "max_position_pct": 0.25,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04,
        },
        "enabled": True,
    }


@pytest.fixture
def sample_market_data():
    """Sample market data dict for strategy signal generation."""
    return {
        "symbol": "AAPL",
        "timeframe": "1h",
        "timestamp": datetime(2024, 1, 2, 10, 0),
        "open": 150.0,
        "high": 151.5,
        "low": 149.5,
        "close": 151.0,
        "volume": 1_000_000,
    }


@pytest.fixture
def sample_indicators():
    """Sample technical indicators for strategy tests."""
    return {
        "sma_20": 149.5,
        "ema_9": 150.8,
        "ema_21": 149.2,
        "rsi_14": 58.5,
        "macd": 0.5,
        "macd_signal": 0.3,
        "bb_upper": 155.0,
        "bb_lower": 145.0,
        "atr_14": 2.5,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Validator Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_validation_result():
    """Create a sample validation result."""
    from quantumtrade.mlops.validator import ValidationResult, ValidationStatus
    result = ValidationResult(status=ValidationStatus.PASSED)
    result.add_check("min_accuracy", True, 0.85)
    result.add_check("min_samples", True, 500)
    return result


@pytest.fixture
def promotion_criteria():
    """Sample promotion criteria for model validation."""
    from quantumtrade.mlops.validator import PromotionCriteria
    return PromotionCriteria(
        min_accuracy=0.75,
        min_precision=0.70,
        min_recall=0.70,
        min_sharpe=1.0,
        max_drift_score=0.3,
        min_backtest_trades=10,
        required_backtest_period_days=30,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Messaging / Notification Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_notification_client():
    """Mock notification/alerting client."""
    client = MagicMock()
    client.send_alert.return_value = {"status": "sent", "message_id": "msg_123"}
    client.send_email.return_value = {"status": "sent"}
    client.send_telegram.return_value = {"ok": True, "message_id": 123}
    client.send_slack.return_value = {"ok": True, "channel": "#alerts"}
    client.retry_count = 3
    return client


@pytest.fixture
def mock_event_handler():
    """Mock event handler for signal processing tests."""
    handler = MagicMock()
    handler.handle.return_value = True
    handler.process.side_effect = lambda event: event
    handler.validate.return_value = True
    return handler


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health Check Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_health_checker_components():
    """Create all mocked components for HealthChecker tests."""
    mock_db = MagicMock()
    mock_db.conn.execute.return_value.fetchone.return_value = (1,)

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.info.return_value = {
        "used_memory": 10_000_000,
        "maxmemory": 1_000_000_000,
    }

    mock_broker = MagicMock()
    mock_broker.is_connected = True
    mock_broker.get_account.return_value = MagicMock(
        cash=500_000.0,
        portfolio_value=1_000_000.0,
        buying_power=1_000_000.0,
    )

    mock_bus = MagicMock()
    mock_bus.health_check.return_value = True
    mock_bus.publish.return_value = "health-check-123"

    return {
        "db": mock_db,
        "redis": mock_redis,
        "broker": mock_broker,
        "bus": mock_bus,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Telemetry / Logging Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_tracer():
    """Mock OpenTelemetry tracer for tracing tests."""
    tracer = MagicMock()
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    tracer.start_as_current_span.return_value = mock_span
    tracer.start_span.return_value = mock_span
    return tracer


@pytest.fixture
def mock_metrics_registry():
    """Mock Prometheus metrics registry."""
    registry = MagicMock()
    registry.register = MagicMock()
    registry.unregister = MagicMock()
    registry.collect = MagicMock(return_value=[])
    return registry


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cleanup / Session-scoped Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="session")
def _session_cleanup():
    """Session-scoped cleanup to run after all unit tests complete."""
    yield
    # Clean up temporary files, DB connections, etc.
    import shutil
    import tempfile
    tmp_dir = tempfile.gettempdir()
    for item in Path(tmp_dir).glob("mlflow_test_*"):
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)