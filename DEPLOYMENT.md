# QuantumTrade Deployment Guide

This document provides comprehensive deployment instructions for QuantumTrade trading bot using Docker and Kubernetes.

## Table of Contents

- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Helm Chart Installation](#helm-chart-installation)
- [Environment Variables](#environment-variables)
- [Health Check Endpoints](#health-check-endpoints)
- [Monitoring Endpoints](#monitoring-endpoints)

---

## Docker Deployment

### Prerequisites

- Docker Engine 24.0+
- Docker Compose 2.20+
- Environment variables configured (see [Environment Variables](#environment-variables))

### Quick Start

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env

# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f tradingbot

# Stop all services
docker-compose down
```

### Services Included

| Service | Port | Description |
|---------|------|-------------|
| tradingbot | 8080, 9090 | Main trading bot API (health on 8080, metrics on 9090) |
| model-serving | 8001 | ML model inference service |
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis cache and message broker |
| prometheus | 9090 | Metrics collection |
| grafana | 3000 | Metrics dashboard (admin/admin) |
| jaeger | 16686 | Distributed tracing UI |
| mlflow | 5000 | Model registry |
| alertmanager | 9093 | Alert management |

### Docker Compose Profiles

```bash
# Start core services only (tradingbot, postgres, redis)
docker-compose --profile core up -d

# Start with monitoring stack
docker-compose --profile monitoring up -d

# Start full stack
docker-compose up -d
```

### Production Considerations

```bash
# Use external volumes for persistence
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Enable resource limits
docker-compose -f docker-compose.yml -f docker-compose.resources.yml up -d
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes 1.24+
- kubectl configured
- Namespace created (optional)

### Quick Start

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Deploy all resources
kubectl apply -k k8s/

# Or deploy individually
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/services.yaml
kubectl apply -f k8s/tradingbot-deployment.yaml
```

### Verify Deployment

```bash
# Check pod status
kubectl get pods -n tradingbot

# Check services
kubectl get svc -n tradingbot

# View logs
kubectl logs -f deployment/tradingbot -n tradingbot
```

### Kustomize Overlay Structure

```
k8s/
├── base/                 # Base manifests
├── overlays/
│   ├── development/      # Dev-specific configs
│   ├── staging/          # Staging-specific configs
│   └── production/       # Production-specific configs
```

### Production Deployment

```bash
# Apply production overlay
kubectl apply -k k8s/overlays/production

# Scale deployment
kubectl scale deployment tradingbot --replicas=5 -n tradingbot
```

---

## Helm Chart Installation

### Prerequisites

- Helm 3.13+
- Kubernetes cluster access

### Install from Local Chart

```bash
# Clone or add the chart
helm install quantumtrade ./helm/tradingbot \
  --namespace tradingbot \
  --create-namespace \
  --set image.tag=latest
```

### Chart Repository (Future)

```bash
# Add repository
helm repo add quantumtrade https://quantumtrade.github.io/charts
helm repo update

# Install
helm install quantumtrade quantumtrade/tradingbot \
  --namespace tradingbot \
  --create-namespace
```

### Helm Customization Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Container image repository | `quantumtrade/tradingbot` |
| `image.tag` | Image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `replicaCount` | Number of replicas | `2` |
| `resources.limits.cpu` | CPU limit | `1000m` |
| `resources.limits.memory` | Memory limit | `1Gi` |
| `resources.requests.cpu` | CPU request | `500m` |
| `resources.requests.memory` | Memory request | `512Mi` |
| `config.LOG_LEVEL` | Logging level | `INFO` |
| `config.ENVIRONMENT` | Environment name | `production` |
| `postgres.enabled` | Deploy PostgreSQL | `true` |
| `redis.enabled` | Deploy Redis | `true` |
| `prometheus.enabled` | Deploy Prometheus | `true` |
| `grafana.enabled` | Deploy Grafana | `true` |
| `jaeger.enabled` | Deploy Jaeger | `true` |
| `mlflow.enabled` | Deploy MLflow | `true` |
| `service.http.port` | HTTP service port | `8080` |
| `service.api.port` | API service port | `8000` |
| `persistence.data.enabled` | Enable data persistence | `true` |
| `persistence.data.size` | PVC size | `10Gi` |
| `nodeSelector` | Node selection labels | `{}` |
| `tolerations` | Pod tolerations | `[]` |
| `affinity` | Pod affinity rules | `{}` |

### Example Custom Values

```yaml
# values-prod.yaml
image:
  tag: v1.0.0

replicaCount: 3

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 1000m
    memory: 1Gi

config:
  LOG_LEVEL: WARNING
  ENVIRONMENT: production

persistence:
  data:
    enabled: true
    size: 50Gi

nodeSelector:
  node-type: trading

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

```bash
helm install quantumtrade ./helm/tradingbot -f values-prod.yaml
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for notifications | `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `TELEGRAM_CHAT_ID` | Telegram chat ID for notifications | `123456789` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `secure-password` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | - |
| `API_JWT_SECRET` | JWT secret for API auth | - |
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `MLFLOW_HOST` | MLflow hostname | `mlflow` |
| `MLFLOW_PORT` | MLflow port | `5000` |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `ENVIRONMENT` | Environment name (development/staging/production) | `production` |

### Secrets Management

**Docker Compose:**

```bash
# Using .env file
echo "TELEGRAM_BOT_TOKEN=your-token" >> .env
echo "TELEGRAM_CHAT_ID=your-chat-id" >> .env
```

**Kubernetes (kubectl):**

```bash
kubectl create secret generic tradingbot-secrets \
  --namespace tradingbot \
  --from-literal=TELEGRAM_BOT_TOKEN=your-token \
  --from-literal=TELEGRAM_CHAT_ID=your-chat-id \
  --from-literal=API_JWT_SECRET=your-jwt-secret
```

---

## Health Check Endpoints

### HTTP Health Endpoints

| Endpoint | Port | Description |
|----------|------|-------------|
| `/health/live` | 8080 | Liveness probe - Returns 200 if container is alive |
| `/health/ready` | 8080 | Readiness probe - Returns 200 if ready to serve traffic |
| `/health` | 8080 | Full health status with component checks |

### Health Check Responses

**Liveness Check:**
```bash
curl http://localhost:8080/health/live
{"status": "alive", "timestamp": "2024-01-15T10:30:00Z"}
```

**Readiness Check:**
```bash
curl http://localhost:8080/health/ready
{"status": "healthy", "timestamp": "2024-01-15T10:30:00Z"}
```

**Full Health Status:**
```bash
curl http://localhost:8080/health
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "checks": {
    "database": {"status": "healthy"},
    "redis": {"status": "healthy"},
    "mlflow": {"status": "healthy"}
  }
}
```

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 5

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
```

---

## Monitoring Endpoints

### Metrics Endpoints

| Service | Endpoint | Port | Description |
|---------|----------|------|-------------|
| TradingBot | `/metrics` | 9090 | Prometheus metrics |
| Model Serving | `/health` | 8001 | Health check |
| Model Serving | `/metrics` | 8001 | Model serving metrics |
| Prometheus | `/metrics` | 9090 | Prometheus metrics endpoint |
| Grafana | `/` | 3000 | Dashboard UI |
| Jaeger | `/health` | 16686 | Tracing UI |
| MLflow | `/health` | 5000 | Model registry health |

**Note:** The health server runs on port 8080 and the metrics server runs on port 9090. These are separate endpoints served by different HTTP servers.

### Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `trading_pnl_total` | Total profit/loss | - |
| `trading_positions_count` | Current open positions | - |
| `trading_orders_total` | Total orders executed | - |
| `model_prediction_latency_seconds` | Model inference latency | > 1s |
| `redis_connected` | Redis connection status | != 1 |
| `postgres_connected` | PostgreSQL connection status | != 1 |

### Prometheus Configuration

The `monitoring/prometheus.yml` includes the following scrape targets:

```yaml
scrape_configs:
  - job_name: 'tradingbot'
    static_configs:
      - targets: ['tradingbot:9090']
    scrape_interval: 15s
```

### Grafana Dashboards

Pre-configured dashboards are available in `monitoring/grafana/dashboards/`.
Import via Grafana UI or use provisioning for automatic setup.

---

## Troubleshooting

### Common Issues

**Container fails to start:**
```bash
# Check logs
docker-compose logs tradingbot

# Verify environment variables
docker-compose exec tradingbot env | grep TELEGRAM
```

**Database connection refused:**
```bash
# Check PostgreSQL status
kubectl get pods -n tradingbot -l app=postgres
kubectl logs deployment/postgres -n tradingbot
```

**Health check failing:**
```bash
# Run health check manually
docker-compose exec tradingbot curl localhost:8080/health/live
```

### Support

- GitHub Issues: https://github.com/quantumtrade/tradingbot/issues
- Documentation: https://docs.quantumtrade.ai