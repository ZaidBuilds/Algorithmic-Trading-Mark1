# QuantumTrade Structure Migration Mapping

This document maps the old file structure to the new enterprise-grade structure.

## Mapping Rules
- OLD → NEW
- Files that don't exist in the old structure are marked as NEW
- Directory restructuring follows Clean Architecture / Hexagonal principles

## Core Trading Logic

### Engine & Orchestration
- run.py → core/engine.py
- app.py → core/engine.py (partial, CLI parts go to interfaces/cli.py)
- dashboard_app.py → interfaces/http/server.py (partial) + interfaces/gui/main_window.py (partial)

### Decision Making
- live/trading_engine.py → core/engine.py
- live/decision_engine.py → core/decision.py
- live/scheduler.py → core/scheduler.py

## Domain Models

### Trading Models
- data/models.py → domain/trading/models.py
- data/base_client.py → adapters/data/base.py (partial)
- data/validator.py → domain/trading/value_objects.py (partial)

### Trading Events
- events.py → domain/trading/events.py
- tests/test_events.py → tests/unit/test_events.py (new location)

### Value Objects
- NEW: domain/trading/value_objects.py (Money, Quantity, Price types)

## Strategies

### Base Strategy
- strategy/base.py → domain/strategy/base.py
- strategy/__init__.py → domain/strategy/__init__.py

### Technical Strategies
- strategy/ema_crossover.py → domain/strategy/technical/ema_crossover.py
- strategy/sma_strategy.py → domain/strategy/technical/sma_crossover.py
- strategy/rsi_strategy.py → domain/strategy/technical/rsi_reversion.py
- strategy/macd_strategy.py → domain/strategy/technical/macd.py
- strategy/bollinger_strategy.py → domain/strategy/technical/bollinger.py
- strategy/breakout_strategy.py → domain/strategy/technical/breakout.py
- strategy/vwap_strategy.py → domain/strategy/technical/vwap.py
- strategy/scalping_strategy.py → domain/strategy/technical/scalping.py
- strategy/momentum_strategy.py → domain/strategy/technical/momentum.py
- strategy/mean_reversion.py → domain/strategy/technical/mean_reversion.py

### Composite Strategies
- NEW: domain/strategy/composite/ensemble.py (multi-strategy orchestrator)

## Risk Management

### Risk Models
- risk/models.py → domain/risk/models.py
- risk/limits.py → domain/risk/limits.py
- risk/position_sizer.py → domain/risk/position_sizer.py
- risk/exit_manager.py → domain/risk/exit_manager.py
- risk/portfolio_risk.py → domain/risk/portfolio_risk.py

### Risk Tests
- tests/test_risk.py → tests/unit/test_risk.py

## Adapters (External Systems)

### Brokers
- brokers/base.py → adapters/brokers/base.py
- brokers/alpaca_broker.py → adapters/brokers/alpaca.py
- NEW: adapters/brokers/binance.py
- NEW: adapters/brokers/paper.py

### Data Providers
- data/loader.py → adapters/data/base.py (partial)
- data/data_client.py → adapters/data/base.py (partial)
- data/stocks_client.py → adapters/data/yahoo.py (partial) + adapters/data/alpaca_data.py (partial)
- data/crypto_client.py → adapters/data/binance_data.py (partial)
- NEW: adapters/data/yahoo.py
- NEW: adapters/data/alpaca_data.py
- NEW: adapters/data/binance_data.py

### WebSocket Streaming
- data/price_stream.py → adapters/data/websocket/market_data.py
- NEW: adapters/data/websocket/order_book.py

### Caching
- utils/logger.py → infrastructure/logging/setup.py (partial)
- NEW: infrastructure/cache/redis_client.py

### Notifications
- telegram_controller.py → interfaces/telegram/bot.py
- NEW: interfaces/telegram/handlers.py
- NEW: interfaces/telegram/keyboards.py
- NEW: adapters/notifications/telegram.py
- NEW: adapters/notifications/discord.py
- NEW: adapters/notifications/email.py
- NEW: adapters/notifications/sms.py

### ML Adapters
- NEW: adapters/ml/predictor.py
- NEW: adapters/ml/features.py
- NEW: adapters/ml/registry.py
- NEW: adapters/ml/trainers.py

## Infrastructure

### Database
- database/db.py → infrastructure/database/models.py (partial) + infrastructure/database/repository.py (partial)
- data/quantumtrade.db → infrastructure/database/ (managed via migrations)
- NEW: infrastructure/database/session.py
- NEW: infrastructure/database/repository.py
- NEW: infrastructure/database/migrations/ (Alembic)

### Configuration
- config/settings.py → infrastructure/config/settings.py
- config/quantumtrade.yaml.example → infrastructure/config/defaults/development.yaml
- config/assets.py → infrastructure/config/schema.py (partial)
- NEW: infrastructure/config/yaml.py
- NEW: infrastructure/config/defaults/staging.yaml
- NEW: infrastructure/config/defaults/production.yaml

### Logging
- utils/logger.py → infrastructure/logging/setup.py
- NEW: infrastructure/logging/formatters.py
- NEW: infrastructure/logging/correlation.py

### Metrics
- monitoring/metrics.py → infrastructure/metrics/collector.py
- monitoring/health.py → infrastructure/health/checks.py (partial)
- tests/test_metrics.py → tests/unit/test_metrics.py

### Tracing
- tracing/ → infrastructure/tracing/ (move entire directory)
- tracing/instrumentation.py → infrastructure/tracing/setup.py
- tracing/context.py → infrastructure/tracing/propagators.py
- NEW: infrastructure/tracing/exporters.py

### Health Checks
- monitoring/health.py → infrastructure/health/checks.py
- NEW: infrastructure/health/endpoint.py

### Security
- NEW: infrastructure/security/auth.py
- NEW: infrastructure/security/secrets.py
- NEW: infrastructure/security/audit.py

### Messaging
- NEW: infrastructure/messaging/bus.py (Redis Streams wrapper)
- NEW: infrastructure/messaging/publishers.py
- NEW: infrastructure/messaging/subscribers.py

## Interfaces (Presentation Layer)

### CLI
- app.py → interfaces/cli.py
- run.py → interfaces/cli.py (partial)

### HTTP API (FastAPI)
- dashboard_app.py → interfaces/http/server.py (partial)
- templates/dashboard.html → interfaces/http/server.py (partial, for embedded templates)
- NEW: interfaces/http/routes/trading.py
- NEW: interfaces/http/routes/portfolio.py
- NEW: interfaces/http/routes/strategies.py
- NEW: interfaces/http/routes/health.py
- NEW: interfaces/http/middleware/ (auth, CORS, rate limiting)
- NEW: interfaces/http/schemas/ (Pydantic models)

### WebSocket
- NEW: interfaces/websocket/server.py

### Telegram Bot
- telegram_controller.py → interfaces/telegram/bot.py
- NEW: interfaces/telegram/handlers.py
- NEW: interfaces/telegram/keyboards.py

### GUI (PyQt5)
- dashboard_app.py → interfaces/gui/main_window.py (partial)
- NEW: interfaces/gui/dashboard.py
- NEW: interfaces/gui/widgets/ (custom widgets)

## Backtesting (Separate Concern)

### Backtesting Engine
- src/backtesting/engine.py → backtesting/engine.py
- src/backtesting/metrics.py → backtesting/metrics.py
- src/backtesting/reporter.py → backtesting/reporter.py
- src/backtesting/visualization.py → backtesting/visualization.py

### Backtesting Simulation
- NEW: backtesting/simulation/slippage.py
- NEW: backtesting/simulation/latency.py
- NEW: backtesting/simulation/impact.py

### Walk-Forward Optimization
- NEW: backtesting/walk_forward.py

## MLOps (Separate Concern)

### Model Registry & Serving
- NEW: mlops/registry.py (MLflow integration)
- NEW: mlops/pipeline.py (Prefect/Airflow)
- NEW: mlops/drift_detector.py
- NEW: mlops/validator.py
- NEW: mlops/serving/server.py

## Deployment Configuration

### Docker
- Dockerfile → deployment/docker/Dockerfile (base)
- NEW: deployment/docker/Dockerfile.dev
- NEW: deployment/docker/Dockerfile.prod

### Kubernetes
- NEW: deployment/k8s/manifests/deployment.yaml
- NEW: deployment/k8s/manifests/service.yaml
- NEW: deployment/k8s/manifests/configmap.yaml
- NEW: deployment/k8s/manifests/secrets.yaml
- NEW: deployment/k8s/helm/quantumtrade/Chart.yaml
- NEW: deployment/k8s/helm/quantumtrade/values.yaml

### Terraform
- NEW: deployment/terraform/main.tf
- NEW: deployment/terraform/variables.tf
- NEW: deployment/terraform/outputs.tf

### CI/CD
- NEW: deployment/ci/github/workflows/ci-cd.yml
- NEW: deployment/ci/gitlab/ (similar structure)

## Documentation

### Core Docs
- README.md → docs/README.md (moved)
- SETUP_PHASE1.md → docs/DEVELOPMENT.md (updated)
- ARCHITECTURE.md → docs/ARCHITECTURE.md (new/updated)
- API.md → docs/API.md
- DEPLOYMENT.md → docs/DEPLOYMENT.md
- RUNBOOK.md → docs/RUNBOOK.md

### Examples
- NEW: docs/examples/broker_integration.py
- NEW: docs/examples/custom_strategy.py

## Data Directory (Runtime)

### Raw Data
- NEW: data/raw/ (cached market data)

### Processed Data
- NEW: data/processed/ (features)

### ML Models
- NEW: data/models/ (trained models)

### Backtest Results
- NEW: data/backtest_results/

### Logs
- NEW: data/logs/ (application logs)

## Test Suite (Mirror Structure)

### Unit Tests
- tests/test_strategy.py → tests/unit/test_strategies/
- tests/test_ema_crossover_strategy.py → tests/unit/test_strategies/
- tests/test_backtest.py → tests/unit/test_backtesting/ (new)
- tests/test_data_layer.py → tests/unit/test_data/ (new)
- tests/test_health.py → tests/unit/test_infrastructure/health/ (new)
- tests/test_metrics.py → tests/unit/test_infrastructure/metrics/ (new)
- tests/test_tracing.py → tests/unit/test_infrastructure/tracing/ (new)

### Integration Tests
- tests/test_comprehensive.py → tests/integration/test_event_flow.py
- tests/test_phase1_quick.py → tests/integration/test_broker_integration.py
- tests/integration_test_events.py → tests/integration/test_event_flow.py
- NEW: tests/integration/test_end_to_end.py

### End-to-End Tests
- NEW: tests/e2e/test_live_trading.py

### Fixtures
- NEW: tests/fixtures/sample_data.py
- NEW: tests/fixtures/mocks.py

## Configuration Files

### Environment
- .env.example → .env.example (root)
- .env.production → .env.production (root, not committed)
- NEW: infrastructure/config/defaults/development.yaml
- NEW: infrastructure/config/defaults/staging.yaml
- NEW: infrastructure/config/defaults/production.yaml

### Dependencies
- requirements.txt → requirements.txt (root)
- requirements-dev.txt → requirements-dev.txt (root)
- pyproject.toml → pyproject.toml (root) or setup.py

### DevOps
- docker-compose.yml → docker-compose.yml (updated paths)
- docker-compose.prod.yml → docker-compose.prod.yml (updated paths)
- Makefile → Makefile (updated)
- .gitignore → .gitignore (updated to exclude data/)

## Scripts

### Setup & Deployment
- scripts/setup_dev.sh → scripts/setup_dev.sh
- scripts/deploy.sh → scripts/deploy.sh
- scripts/backup.sh → scripts/backup.sh

### Monitoring Scripts
- NEW: scripts/monitoring/grafana.sh
- NEW: scripts/monitoring/prometheus.sh

## Summary of Changes

1. **Clear Layering**: Core domain → Adapters → Infrastructure → Interfaces
2. **Separation of Concerns**: Trading logic isolated from technical infrastructure
3. **Test Mirror**: Tests follow same structure as source
4. **Configuration Centralized**: All config in infrastructure/config/
5. **Deployment Isolated**: All deploy configs in deployment/
6. **Data Separated**: Runtime data in data/ (not versioned)
7. **MLOps Separated**: Model lifecycle separate from trading code
8. **Backtesting Isolated**: Separate from live trading engine
9. **Standardized Naming**: Consistent file naming conventions
10. **Package Structure**: Proper Python packages with __init__.py files

This migration maintains backward compatibility during transition by keeping old files until migration is complete.