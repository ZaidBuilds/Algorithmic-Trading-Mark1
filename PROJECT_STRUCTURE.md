# QuantumTrade - Enterprise Project Structure

## Directory Organization

```
quantumtrade/                          # Main Python package
├── app/                               # Application entry point
│   ├── __init__.py
│   └── run.py                         # Main launcher (forwarded from root)
│
├── interfaces/                        # User-facing layers
│   ├── cli/                           # Command-line interface
│   │   └── interactive.py
│   ├── gui/                           # Graphical interface (PyQt5)
│   │   └── dashboard.py
│   ├── telegram/                      # Telegram bot interface
│   │   └── controller.py
│   └── http/                          # HTTP API (FastAPI)
│       └── api_server.py
│
├── core/                              # Business logic & domain
│   ├── decision_engine.py             # AI-driven decision making
│   ├── multi_strategy.py              # Multi-strategy orchestration
│   ├── trading_engine.py              # Live trading engine
│   ├── trading_strategies/            # Strategy implementations
│   │   ├── ema_crossover.py
│   │   ├── vwap_strategy.py
│   │   ├── macd_strategy.py
│   │   ├── rsi_strategy.py
│   │   ├── bollinger_strategy.py
│   │   ├── momentum_strategy.py
│   │   ├── mean_reversion.py
│   │   ├── scalping_strategy.py
│   │   ├── breakout_strategy.py
│   │   └── sma_strategy.py
│   ├── risk_management/               # Risk controls
│   │   ├── risk_manager.py
│   │   ├── position_sizer.py
│   │   ├── stop_loss.py
│   │   └── limits.py
│   └── portfolio_management/          # Portfolio tracking
│       ├── tracker.py
│       └── performance.py
│
├── ml_ai/                             # Machine Learning & AI
│   ├── feature_engineer.py            # Feature engineering
│   ├── ml_predictor.py                # ML model predictions
│   ├── ollama_advisor.py              # AI advisor (Ollama)
│   ├── sentiment.py                   # Sentiment analysis
│   └── models/                        # Trained models
│
├── adapters/                          # External integrations
│   ├── brokers/                       # Broker integrations
│   │   ├── base.py                    # Base broker class
│   │   ├── alpaca_broker.py
│   │   ├── binance_broker.py
│   │   ├── paper_broker.py            # Paper trading
│   │   ├── crypto_broker.py
│   │   ├── forex_broker.py
│   │   └── stocks_broker.py
│   ├── data/                          # Data sources
│   │   ├── base_client.py             # Base data client
│   │   ├── data_client.py
│   │   ├── crypto_client.py
│   │   ├── stocks_client.py
│   │   ├── price_stream.py            # Real-time price streaming
│   │   ├── loader.py                  # Data loading
│   │   ├── models.py                  # Data models
│   │   ├── validator.py               # Data validation
│   │   └── backtest_results/          # Backtest data outputs
│   ├── execution/                     # Order execution
│   │   ├── broker_client.py
│   │   ├── order.py
│   │   ├── fill.py
│   │   ├── factory.py
│   │   └── paper_trader.py
│   └── notifications/                 # Notification channels
│       ├── alerter.py                 # Alert manager
│       ├── telegram_bot.py
│       ├── discord_webhook.py
│       └── email_notifier.py
│
├── infrastructure/                    # System infrastructure
│   ├── config/                        # Configuration management
│   │   ├── settings.py                # Global settings
│   │   ├── assets.py                  # Asset configuration
│   │   └── quantumtrade.yaml          # YAML config
│   ├── database/                      # Data persistence
│   │   ├── db.py                      # Database connection
│   │   └── trade_repository.py        # Trade storage
│   ├── monitoring/                    # Observability
│   │   ├── logger.py                  # Logging setup
│   │   ├── telemetry.py               # Telemetry initialization
│   │   ├── metrics.py                 # Prometheus metrics
│   │   ├── metrics_endpoint.py        # Metrics HTTP endpoint
│   │   ├── health.py                  # Health checks
│   │   ├── health_endpoint.py         # Health HTTP endpoint
│   │   ├── structured_logging.py      # Structured log format
│   │   ├── dashboard_server.py        # Monitoring dashboard
│   │   ├── prometheus.yml             # Prometheus config
│   │   ├── alertmanager.yml           # Alert config
│   │   └── grafana/                   # Grafana dashboards
│   ├── tracing/                       # Distributed tracing
│   │   ├── tracing.py                 # OpenTelemetry setup
│   │   ├── context.py                 # Trace context
│   │   └── instrumentation.py         # Instrumentation
│   └── events/                        # Event system
│       └── events.py                  # Message bus & events
│
├── backtesting/                       # Backtesting framework
│   ├── engine.py                      # Backtest engine
│   ├── reporter.py                    # Results reporting
│   └── optimizer.py                   # Parameter optimization
│
├── domain/                            # Domain models & entities
│   ├── trading/                       # Trading domain
│   │   ├── position.py
│   │   ├── order.py
│   │   └── trade.py
│   └── market/                        # Market domain
│       └── symbol.py
│
├── deployment/                        # Deployment configurations
│   ├── docker/
│   ├── kubernetes/
│   └── cloud/
│
├── tests/                             # Comprehensive test suite
│   ├── unit/                          # Unit tests
│   ├── integration/                   # Integration tests
│   └── conftest.py                    # Test fixtures
│
├── docs/                              # Documentation
│   ├── api/
│   ├── architecture/
│   └── setup/
│
├── scripts/                           # Utility scripts
├── mlops/                             # MLOps pipelines
├── __init__.py
└── main.py                            # Alternative entry point

```

## Root-Level Files (Backward Compatibility Wrappers)

```
Root/
├── app.py                             # → quantumtrade.interfaces.cli.interactive
├── dashboard_app.py                   # → quantumtrade.interfaces.gui.dashboard  
├── telegram_controller.py             # → quantumtrade.interfaces.telegram.controller
├── decision_engine.py                 # → quantumtrade.core.decision_engine
├── multi_strategy.py                  # → quantumtrade.core.multi_strategy
│
├── run.py                             # Main entry point (will move to quantumtrade/app/)
├── conftest.py                        # Test configuration
│
├── pyproject.toml                     # Python project config
├── requirements.txt                   # Pip dependencies
├── Dockerfile                         # Docker image
├── docker-compose.yml                 # Docker Compose setup
│
├── README.md                          # Project documentation
├── DEPLOYMENT.md                      # Deployment guide
├── LICENSE                            # License file
│
├── examples/                          # Example scripts
├── templates/                         # HTML templates
├── k8s/                               # Kubernetes manifests
├── logs/                              # Application logs
├── tests/                             # Root test files (most moved to quantumtrade/tests/)
├── utils/                             # Utility functions
├── scheduler/                         # Task scheduler
└── .env.example                       # Environment template
```

## Key Integration Points

### 1. Entry Points
- **CLI**: `python run.py --broker paper --strategy "EMA Crossover"`
- **GUI**: `python dashboard_app.py` or `python -m quantumtrade.interfaces.gui.dashboard`
- **Telegram**: Controlled via `quantumtrade/interfaces/telegram/controller.py`
- **API**: HTTP API on port 8000

### 2. Configuration
- Primary: `quantumtrade/infrastructure/config/quantumtrade.yaml`
- Settings: `quantumtrade/infrastructure/config/settings.py`
- Assets: `quantumtrade/infrastructure/config/assets.py`

### 3. Data Flow
```
Data (adapters/data/) → Core (core/) → Strategies (core/trading_strategies/)
                     ↓
              ML/AI (ml_ai/) ← Feature Engineering
                     ↓
              Decision Engine (core/decision_engine.py)
                     ↓
         Risk Manager (core/risk_management/) → Position Sizer
                     ↓
         Broker Execution (adapters/execution/)
                     ↓
        Order Execution (adapters/brokers/)
                     ↓
       Portfolio & Database (core/portfolio_management/ + infrastructure/database/)
```

### 4. Observability Stack
- **Logging**: `infrastructure/monitoring/logger.py`
- **Metrics**: Prometheus on http://localhost:8000/metrics
- **Tracing**: OpenTelemetry with Jaeger (optional)
- **Health**: http://localhost:8000/health
- **Dashboard**: Grafana dashboards in `infrastructure/monitoring/grafana/`

## Testing

```
quantumtrade/tests/
├── unit/                    # Fast, isolated unit tests
├── integration/             # Integration tests with real components
└── conftest.py             # Shared fixtures & markers
```

Run tests:
```bash
pytest                       # All tests
pytest -m unit             # Only unit tests
pytest -m integration      # Only integration tests
pytest --cov               # With coverage
```

## Import Paths

### New (Organized)
```python
from quantumtrade.interfaces.cli.interactive import main
from quantumtrade.interfaces.gui.dashboard import QuantumTradeDashboard
from quantumtrade.interfaces.telegram.controller import TelegramController
from quantumtrade.core.decision_engine import UnifiedDecisionEngine
from quantumtrade.core.trading_strategies.ema_crossover import EMA_Crossover
from quantumtrade.core.risk_management.risk_manager import RiskManager
from quantumtrade.adapters.brokers.alpaca_broker import AlpacaBroker
from quantumtrade.adapters.data.stocks_client import StocksClient
from quantumtrade.infrastructure.config.settings import settings
from quantumtrade.infrastructure.database.db import get_db
from quantumtrade.ml_ai.ml_predictor import MLPredictor
from quantumtrade.backtesting.engine import BacktestEngine
```

### Legacy (Still Supported - Root Wrappers)
```python
from app import main                              # → quantumtrade.interfaces.cli.interactive
from dashboard_app import main                   # → quantumtrade.interfaces.gui.dashboard
from telegram_controller import TelegramController  # → quantumtrade.interfaces.telegram.controller
from decision_engine import UnifiedDecisionEngine   # → quantumtrade.core.decision_engine
from multi_strategy import MultiStrategyRunner      # → quantumtrade.core.multi_strategy
```

## Benefits of This Structure

✅ **Clean Separation of Concerns** - Each folder has a single purpose  
✅ **Scalable** - Easy to add new adapters, strategies, or interfaces  
✅ **Enterprise-Grade** - Professional package hierarchy  
✅ **Testable** - Clear dependencies and test organization  
✅ **Observable** - Dedicated infrastructure/monitoring folder  
✅ **Maintainable** - Backward compatibility via root wrappers  
✅ **Documented** - Self-documenting structure  

---
Generated: 2026-05-10  
QuantumTrade Trading System v2.0
