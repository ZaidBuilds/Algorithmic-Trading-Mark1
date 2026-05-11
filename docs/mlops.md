# MLOps System Documentation

## Overview

QuantumTrade MLOps provides production-grade model lifecycle management including:

- **Model Registry** - Versioning with MLflow
- **Automated Retraining** - Scheduled & trigger-based pipeline
- **Drift Detection** - Data & concept drift monitoring
- **Feature Store** - Unified feature management
- **Model Serving** - FastAPI REST endpoints
- **Canary Deployment** - Gradual rollout with safety checks
- **Alerting** - Telegram/Discord/webhook notifications

## Architecture

```
┌─────────────────┐
│  Training Data  │
│   (PostgreSQL)  │
└────────┬────────┘
         │
    ┌────▼────┐
    │ Feature │
    │ Store   │
    └────┬────┘
         │
    ┌────▼────┐      ┌──────────────────┐
    │ Feature │─────▶│  Model Registry  │◀────┐
    │ Compute │      │   (MLflow)       │     │
    └────┬────┘      └─────────┬────────┘     │
         │                     │              │
         ▼                     ▼              │
    ┌────▼────┐      ┌──────────────────┐     │
    │ Training│─────▶│  Model Version   │─────┘
    │ Pipeline│      │   Promotion      │
    └────┬────┘      └─────────┬────────┘
         │                     │
         ▼                     ▼
    ┌────▼────┐      ┌──────────────────┐
    │ Drift   │◀─────┤   Canary         │
    │ Monitor │      │   Deployment     │
    └─────────┘      └─────────┬────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Model Serving     │
                    │   (FastAPI)         │
                    └─────────────────────┘
```

## Configuration

Add to `config/quantumtrade.yaml`:

```yaml
mlops:
  mlflow:
    tracking_uri: "http://localhost:5000"
    artifact_location: "./mlflow_artifacts"
    experiment_name: "quantumtrade_models"
  
  retraining:
    enabled: true
    schedule: "0 2 * * *"  # Daily 2am UTC
    min_samples: 1000
    performance_threshold: 0.55
    improvement_threshold: 0.02
    canary:
      capital_pct: 0.01
      duration_hours: 24
    phase2_capital_pct: 0.05
    phase2_duration_days: 3
    phase3_capital_pct: 0.25
    phase3_duration_days: 7
  
  drift:
    enabled: true
    check_interval_minutes: 60
    psi_threshold: 0.2
    ks_alpha: 0.05
    accuracy_drop_threshold: 0.05
  
  feature_store:
    backend: "redis"
    ttl_seconds: 3600
  
  serving:
    host: "0.0.0.0"
    port: 8001
    workers: 2
    model_cache_size: 10
    prediction_cache_ttl: 60
```

Or use environment variables:

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
export RETRAINING_ENABLED=true
export RETRAINING_SCHEDULE="0 2 * * *"
export DRIFT_PSI_THRESHOLD=0.2
export SERVING_PORT=8001
```

## Model Registry

The registry uses MLflow for model versioning and metadata tracking.

```python
from quantumtrade.mlops import ModelRegistry

registry = ModelRegistry(
    tracking_uri="http://localhost:5000",
    experiment_name="quantumtrade_models",
)

# Register model
version = registry.register_model(
    model=trained_model,
    name="momentum_predictor",
    metrics={"accuracy": 0.85, "precision": 0.83},
    params={"n_estimators": 100, "max_depth": 15},
    training_data=df,  # Used for data hash
)

# Promote to production
registry.promote_model("momentum_predictor", version, "Production")

# Get latest production model
model = registry.get_latest_model("momentum_predictor", stage="Production")

# Rollback
registry.rollback_model("momentum_predictor", to_version="5")
```

### Staged Model Lifecycle

```
None ──▶ Staging ──▶ Production ──▶ Archived
         (QA)         (Live)          (Deprecated)
```

## Automated Retraining Pipeline

### Trigger Conditions

Retraining is triggered when ANY of these conditions are met:

1. **Scheduled** - Cron schedule (default: daily at 2am UTC)
2. **Performance degradation** - Accuracy drops below threshold
3. **Drift detected** - Data/concept drift triggers alert
4. **Data volume** - New samples exceed `min_samples` (default: 1000)

### Pipeline Steps

1. Fetch recent data (last N days)
2. Validate data quality (NaN check, column check)
3. Engineer features
4. Train new model
5. Evaluate on holdout set
6. Compare vs current production
7. Run backtest (if configured)
8. Validate against promotion criteria
9. Register new version
10. Canary deployment (if enabled)
11. Auto-promote on success

### Canary Deployment

Gradual rollout to minimize risk:

| Phase   | Capital | Duration   | Action                 |
|---------|---------|------------|------------------------|
| Phase 1 | 1%      | 24 hours   | Small exposure test   |
| Phase 2 | 5%      | 3 days     | Increased allocation   |
| Phase 3 | 25%     | 1 week     | Near-production        |
| Phase 4 | 100%    | Indefinite | Full production        |

**Rollback automatic** if Sharpe ratio drops below threshold during canary.

## Drift Detection

### Data Drift

Tracks feature distribution shifts using:

- **Population Stability Index (PSI)**: `PSI > 0.2` = significant shift
- **Kolmogorov-Smirnov test**: `p-value < 0.05` = distribution change

### Concept Drift

Monitors model performance degradation:

- Accuracy drop > 5%
- Prediction confidence drop > 10%
- Win rate drop > 10%

### Check Frequency

- **Online features**: Hourly
- **Batch features**: Daily

### Alerts

Triggers:

- ModelDriftAlert event on message bus
- Telegram/Discord notifications
- Grafana panel updates

## Feature Store

### Architecture

```
┌──────────────────┐
│  Feature Defs    │  (Registry of feature definitions)
└────────┬─────────┘
         │
    ┌────▼────┐     ┌────────────┐
    │ Offline │────▶│ PostgreSQL │  (Training)
    │ Compute │     └────────────┘
    └────┬────┘
         │
    ┌────▼────┐     ┌────────────┐
    │ Online  │────▶│   Redis    │  (Serving)
    │ Cache   │     └────────────┘
    └─────────┘
```

### Usage

```python
from quantumtrade.mlops import FeatureStore, FeatureDefinition

# Initialize store
store = FeatureStore(
    backend=RedisFeatureBackend(redis_client),
    ttl_seconds=3600,
)

# Register features
store.register_feature(FeatureDefinition(
    name="rsi_14",
    description="14-period RSI",
    computation_logic="_compute_rsi(prices, period=14)",
    tags=["technical", "momentum"],
))

# Compute for training
features_df = store.batch_compute_offline(ohlcv_df)

# Cache for serving
store.cache_features("AAPL", timestamp, {"rsi_14": 65.5})

# Retrieve
features = store.get_cached_features("AAPL", timestamp)
```

## Model Serving

### FastAPI Endpoints

```
POST   /predict/{model_name}          → Single prediction
POST   /predict/batch/{model_name}    → Batch predictions
GET    /models                        → List all models
GET    /models/{name}/versions        → List versions
POST   /models/{name}/promote/{version} → Promote version
POST   /models/{name}/rollback/{version} → Rollback
GET    /metrics                       → Server metrics
DELETE /cache                         → Clear prediction cache
GET    /health                        → Health check
```

### Example Usage

```bash
# Single prediction
curl -X POST "http://localhost:8001/predict/momentum_predictor" \
  -H "Content-Type: application/json" \
  -d '{"features": {"rsi": 65.0, "sma": 100.0}}'

# Batch prediction
curl -X POST "http://localhost:8001/predict/batch/momentum_predictor" \
  -H "Content-Type: application/json" \
  -d '{"features_list": [{"rsi": 65}, {"rsi": 70}]}'

# List models
curl "http://localhost:8001/models"

# Promote model
curl -X POST "http://localhost:8001/models/momentum_predictor/promote/3" \
  -H "Content-Type: application/json" \
  -d '{"version": "3", "stage": "Production"}'
```

```python
import httpx

async def predict(symbol: str, features: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://localhost:8001/predict/{symbol}",
            json={"features": features}
        )
        return resp.json()
```

### Caching

- **Model cache**: In-memory LRU (configurable size)
- **Prediction cache**: Redis-backed with TTL (default: 60s)
- **Hit rate** exposed at `/metrics`

## Monitoring & Alerts

### Metrics Tracked

- Prediction counts
- Cache hit rates
- Latency (P50, P95, P99)
- Model accuracy over time
- Drift metrics (PSI, KS statistic)
- Traffic split (A/B tests)

### Alert Channels

Configure in YAML:

```yaml
mlops:
  alerts:
    webhook_url: "https://hooks.slack.com/..."
    telegram:
      bot_token: "xxx"
      chat_id: "12345"
    discord:
      webhook_url: "https://discord.com/api/webhooks/..."
```

### Alert Severities

- **Low** - Info, no action needed
- **Medium** - Warning, monitor
- **High** - Action required soon
- **Critical** - Immediate action

### Grafana Dashboard

Import predefined dashboard JSON from `monitoring/grafana/`:

Panels include:
- Model accuracy trend (line)
- Prediction confidence histogram
- Drift metrics (PSI, KS) over time
- Model version traffic share
- Retraining events log

## Development

### Running the Serving API

```bash
# Install dependencies
pip install fastapi uvicorn mlflow

# Start API server
uvicorn quantumtrade.mlops.serving.server:app --host 0.0.0.0 --port 8001
```

### Starting MLflow

```bash
# Start MLflow tracking server
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlflow_artifacts \
  --host 0.0.0.0 \
  --port 5000
```

### Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests with coverage
pytest --cov=quantumtrade.mlops --cov-report=html
```

### Docker Compose

```yaml
version: '3.8'
services:
  mlflow:
    image: mlflow/mlflow:latest
    ports:
      - "5000:5000"
    volumes:
      - mlflow_data:/mlflow
    command: >
      mlflow server
      --backend-store-uri sqlite:///mlflow/mlflow.db
      --default-artifact-root /mlflow/artifacts
      --host 0.0.0.0
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  model-serving:
    build: ./quantumtrade/mlops/serving
    ports:
      - "8001:8001"
    depends_on:
      - mlflow
      - redis
    environment:
      - MLFLOW_TRACKING_URI=http://mlflow:5000
      - REDIS_URL=redis://redis:6379/0

volumes:
  mlflow_data:
```

## API Reference

### ModelRegistry

| Method                  | Description                         |
|-------------------------|-------------------------------------|
| `register_model()`      | Register new model version          |
| `promote_model()`       | Promote to staging/production       |
| `get_latest_model()`    | Get latest version in stage         |
| `compare_versions()`    | Compare two versions                |
| `rollback_model()`      | Rollback to previous version        |
| `list_models()`         | List all registered models          |

### RetrainingPipeline

| Method               | Description                         |
|----------------------|-------------------------------------|
| `run_pipeline()`     | Execute full retraining pipeline    |
| `trigger_manual()`   | Manually trigger retraining         |

### DriftDetector

| Method                | Description                        |
|-----------------------|------------------------------------|
| `set_baseline()`      | Set reference distribution         |
| `detect_drift()`      | Compare current vs baseline        |
| `should_retrain()`    | Check if retraining needed         |

### Predictor

| Method          | Description                  |
|-----------------|------------------------------|
| `predict()`     | Single prediction            |
| `predict_batch()` | Batch predictions          |
| `clear_cache()` | Clear prediction cache       |

## Troubleshooting

### MLflow Connection Failed

```bash
# Check MLflow is running
curl http://localhost:5000/health

# Start MLflow if not running
mlflow server --host 0.0.0.0 --port 5000
```

### Redis Connection Issues

```bash
# Test Redis
redis-cli ping

# Start Redis (Docker)
docker run -p 6379:6379 redis:7-alpine
```

### Model Not Found

Ensure model is registered and promoted to Production:

```python
registry.list_models()
registry.get_latest_model("model_name", stage="Production")
```

## Performance Optimization

- Model loading: Cache frequently used models in memory
- Prediction caching: Cache predictions for 1-5 minutes for hot symbols
- Batch predictions: Use batch endpoint for multiple symbols
- Connection pooling: Use async HTTP client for high QPS

## Future Enhancements

- A/B testing traffic splitting
- Multi-armed bandit for model selection
- Explainable AI (SHAP/LIME) integration
- Automated hyperparameter tuning (Optuna)
- Distributed training support
- Real-time feature computation streaming
- K8s operator for lifecycle management
