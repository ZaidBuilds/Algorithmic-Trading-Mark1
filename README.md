<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License"/>
  <img src="https://img.shields.io/badge/Status-Production-brightgreen?style=for-the-badge" alt="Status"/>
  <img src="https://img.shields.io/badge/Live_Trading-Alpaca_%7C_Binance-FF6B35?style=for-the-badge" alt="Live Trading"/>
</p>

<h1 align="center">⚡ QuantumTrade</h1>
<h3 align="center">AI-Powered Production Algorithmic Trading System</h3>

<p align="center">
  <i>A production-grade trading engine combining 10 strategies, real broker integration,<br>machine learning, and AI reasoning into autonomous trading decisions.</i>
</p>

---

## 🏗️ Architecture

QuantumTrade uses an **event-driven microservices-style architecture** with Redis Streams at its core. This enables loose coupling, horizontal scaling, and reliable message delivery.

### Phase 1: Event-Driven Foundation (Current)

```
┌─────────────────────────────────────────────────────────────────┐
│                         COMPONENTS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐          ┌─────────────┐                       │
│  │   Market    │  Event  │   Signal    │  Event  │  Order       │
│  │   Data      │────────▶│   Handler   │────────▶│  Handler     │
│  │   Handler   │         │   (Risk)    │         │  (Broker)    │
│  └─────────────┘         └─────────────┘         └──────────────┘
│        │                        │                        │
│        ▼                        ▼                        ▼
│  MarketDataEvent          SignalEvent            OrderEvent
│        │                        │                        │
│        └────────────────────────┼────────────────────────┘
│                                 ▼
│                          TradeEvent (Completed)
│
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    ┌────────────────────┐
                    │  Redis Streams     │
                    │  (Durable Queue)   │
                    └────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    ┌──────────┐        ┌──────────┐      ┌──────────┐
    │Consumer  │        │Consumer  │      │Consumer  │
    │Group:    │        │Group:    │      │Group:    │
    │trading_  │        │risk_     │      │data_     │
    │engine    │        │engine    │      │feed      │
    └──────────┘        └──────────┘      └──────────┘

## 📁 Project Structure (Event-Driven)

```
quantumtrade/
│
├── events/                          # Event system core
│   ├── __init__.py                  #    Public API
│   ├── schemas.py                   #    Event dataclasses (6 types)
│   ├── bus.py                       #    Redis Streams message bus
│   └── handlers/                    #    Event processors
│       ├── __init__.py
│       ├── market_data.py           #    MarketData→Signal
│       ├── signals.py               #    Signal→Order (risk check)
│       └── orders.py                #    Order→Trade (broker)
│
├── messaging/                       # Legacy compatibility
│   └── __init__.py                  #    Re-exports events module
│
├── config/                          # Configuration system
│   ├── settings.py                  #    Pydantic settings (extended)
│   ├── config_schema.py             #    Pydantic v2 validation models
│   └── quantumtrade.yaml            #    YAML config (optional)
│
├── live/
│   └── trading_engine.py            # Event-driven engine (updated)
│
├── brokers/                         # Broker integrations (unchanged)
├── strategy/                        # Trading strategies (unchanged)
├── risk/                            # Risk management (unchanged)
├── database/                        # SQLite persistence (unchanged)
├── notifications/                   # Alert system (unchanged)
├── scheduler/                       # Timing & market hours (unchanged)
│
├── docker-compose.yml               # Local dev stack (Redis + Postgres)
├── .env.example                     # Environment template
└── requirements.txt                 # Dependencies
```

---

## 🔄 Event-Driven Architecture (Phase 1)

QuantumTrade now uses a **Redis Streams-based event bus** for all inter-component communication.

### Core Event Types

| Event | Direction | Producer | Consumer | Purpose |
|:------|:----------|:---------|:---------|:--------|
| `MarketDataEvent` | Input | DataFeed | Strategy, MarketDataHandler | OHLCV price updates |
| `SignalEvent` | Internal | Strategy, MarketDataHandler | Risk, SignalHandler | BUY/SELL/HOLD signals |
| `OrderEvent` | Output | SignalHandler, Risk | OrderHandler, Broker | Order placement request |
| `TradeEvent` | Output | OrderHandler | Portfolio, DB, Risk | Fill confirmation |
| `RiskEvent` | Internal | RiskEngine | Strategy, RiskManager | Portfolio risk metrics |
| `SystemEvent` | Monitor | Any | Logger, Monitor | Health/alerts |

### Message Flow Example

```
[Market Data] → MarketDataEvent ─┐
                                   ▼
                          [MarketDataHandler]
                                   │
                                   ▼
                              SignalEvent ─┐
                                               ▼
                                          [SignalHandler]
                                         (Risk check)
                                               │
                                               ▼
                                          OrderEvent ─┐
                                                       ▼
                                                  [OrderHandler]
                                                 (Broker call)
                                                       │
                                                       ▼
                                                  TradeEvent
                                                   │
                                                   ▼
                                              [DB Logger]
```

### Key Features

- **Durable Storage**: All events persisted in Redis Streams (survive restarts)
- **Consumer Groups**: Multiple independent consumers can subscribe to same stream
- **At-Least-Once Delivery**: Acknowledgment pattern + replay on failure
- **Idempotent Handlers**: Safe to process duplicate events (event_id tracking)
- **Dead-Letter Queue**: Failed events automatically routed for inspection
- **Auto-Reconnection**: Transparent reconnection on Redis failure
- **Metrics**: Built-in counters for events published/consumed, lag, errors

### Consumer Groups

```
group:trading_engine      - Main engine (signals → orders)
group:risk_engine         - Risk monitoring (position tracking)
group:data_feed           - Data persistence
group:monitor             - Dashboard / metrics
```

### Running with Event System

```bash
# 1. Start Redis + PostgreSQL via Docker Compose
docker-compose up -d

# 2. Configure optional YAML
cp config/quantumtrade.yaml.example config/quantumtrade.yaml
# Edit as needed (or use .env)

# 3. Run the bot (uses new event system transparently)
python run.py

# 4. Monitor events via CLI
redis-cli XLEN events:signals        # Stream length
redis-cli XINFO GROUPS events:trades # Consumer group info
```

### Backward Compatibility

All existing code continues to work unchanged. The event system is used **internally** by the updated `LiveTradingEngine`, but the public API (`run.py`, CLI, Telegram) remains identical. Brokers, strategies, and database models are untouched.

---

## ✨ Key Features

### 🏦 Real Broker Integration
| Broker | Markets | Modes | API |
|:-------|:--------|:------|:----|
| **Alpaca** | US Stocks, ETFs, Crypto | Paper + Live | `alpaca-py` |
| **Binance** | Crypto (Spot) | Testnet + Live | `python-binance` |
| **Paper** | All | Simulated | Local |

### 📈 10 Trading Strategies
| Category | Strategies |
|:---------|:-----------|
| **Trend-Following** | EMA Crossover · SMA · MACD · Momentum |
| **Mean-Reversion** | RSI · Bollinger Bands · Mean Reversion (Z-Score) |
| **Price-Action** | Breakout · VWAP |
| **High-Frequency** | Scalping |

### 🤖 AI / ML Layer
- **25+ engineered features** — RSI, MACD, momentum, volatility, volume ratios
- **Random Forest & Gradient Boosting** — 80%+ directional accuracy
- **Ollama LLM Advisor** — contextual market reasoning via local AI

### 🛡️ Risk Management
- Max position sizing (% of portfolio)
- Stop-loss & take-profit automation
- Daily loss limits with auto-halt
- Maximum concurrent positions guard
- Cash reserve protection

### 🔔 Notifications
- **Telegram** — instant trade alerts to your phone
- **Discord** — webhook alerts to your server
- **Email** — formatted HTML alerts via SMTP

### 🏥 Health Checks
Health endpoints for monitoring and container orchestration:

| Endpoint | Description | Returns |
|----------|-------------|---------|
| `GET /health/live` | Liveness probe | 200 if process is alive |
| `GET /health/ready` | Readiness probe | 200 if DB, Redis, broker connected |
| `GET /health` | Full health check | 200/207/503 with component breakdown |

```bash
# Check bot health
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
curl http://localhost:8080/health
```

Docker healthcheck uses `/health/live` endpoint for container restarts.

### 🤖 Telegram Bot Controller (18 commands!)
| Command | Action |
|:--------|:-------|
| `/status` | Engine status, equity, positions |
| `/buy AAPL 10` | Execute buy from your phone |
| `/sell AAPL 10` | Execute sell from your phone |
| `/portfolio` | Full portfolio with allocation |
| `/performance` | Sharpe, drawdown, Calmar ratio |
| `/sentiment AAPL` | News sentiment analysis |
| `/compare` | Strategy comparison |
| `/startbot` / `/stopbot` | Start/stop engine remotely |

### 📦 SQLite Database
- All trades persisted automatically
- P&L tracking by symbol, strategy, and day
- Portfolio snapshots over time
- Settings key-value store

### 📡 Real-Time Data Streaming
- Binance WebSocket (crypto)
- Alpaca WebSocket (stocks)
- yfinance polling fallback

### 📰 Sentiment Analysis
- RSS feed analysis (Yahoo Finance, Google News)
- Financial-specific lexicon (60+ terms)
- Bullish/bearish signal generation

### ⏱️ Workflow Automation
- Market hours detection (US stocks, crypto 24/7, forex)
- Interval-based strategy execution
- Pre-market / after-hours session events
- Graceful shutdown handling

---

## 🚀 Quick Start (Phase 1)

### 1. Clone & Install

```bash
git clone https://github.com/<your-username>/quantumtrade.git
cd quantumtrade

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### 2. Start Infrastructure (Docker Compose)

```bash
# Start Redis + PostgreSQL
docker-compose up -d

# Verify
docker-compose ps
docker-compose logs -f redis    # Watch Redis logs
docker-compose logs -f postgres # Watch Postgres logs

# Stop
docker-compose down
```

**Note:** Redis runs on `localhost:6379`, Postgres on `localhost:5432`.

### 3. Configure

```bash
# Copy and edit environment
cp .env.example .env
# Edit .env with your broker keys, tokens, etc.

# Optional: YAML config (overrides .env)
cp config/quantumtrade.yaml.example config/quantumtrade.yaml
# Edit config/quantumtrade.yaml
```

**Configuration Priority:** Environment variables > YAML file > .env file > defaults.

### 4. Launch

```bash
# ── Standard launch ─────────────────────
python run.py                        # Paper trading (default)
python run.py --broker paper         # Explicit paper
python run.py --broker alpaca        # Alpaca live
python run.py --broker binance       # Binance live

# ── Strategy override ───────────────────
python run.py --strategy "EMA Crossover"
python run.py --strategy "RSI"

# ── Symbol override ─────────────────────
python run.py --symbols AAPL GOOGL MSFT

# ── Disable features ────────────────────
python run.py --no-telegram          # No Telegram bot

# ── Desktop Dashboard ───────────────────
python dashboard_app.py

# ── CLI Backtest ────────────────────────
python app.py backtest --symbol AAPL --strategy "EMA Crossover"
```

### 5. Verify Event System

```bash
# Check Redis streams
redis-cli XLEN events:market_data   # Market data events count
redis-cli XLEN events:signals       # Signal events count
redis-cli XLEN events:orders        # Order events count
redis-cli XLEN events:trades        # Trade events count

# Check consumer groups
redis-cli XINFO GROUPS events:signals

# Check DLQ for failed events
redis-cli XLEN events:dead_letter
redis-cli XRANGE events:dead_letter - + COUNT 10

# Monitor metrics (Python console)
>>> from quantumtrade.events import get_message_bus
>>> bus = get_message_bus()
>>> print(bus.get_metrics())
```

---

## ⚙️ Configuration

```
quantumtrade/
│
├── run.py                         # 🚀 Main launcher (starts everything)
├── telegram_controller.py         # 🤖 Telegram bot (18 commands)
├── multi_strategy.py              # 🎯 Multi-strategy runner
├── app.py                         # CLI entry point
├── dashboard_app.py               # Desktop GUI (PyQt5)
├── decision_engine.py             # Unified 3-layer decision engine
│
├── brokers/                       # 🏦 Broker Integrations
│   ├── __init__.py                #    Broker factory
│   ├── base.py                    #    Abstract broker interface
│   ├── alpaca_broker.py           #    Alpaca (US stocks + crypto)
│   ├── binance_broker.py          #    Binance (crypto spot)
│   └── paper_broker.py            #    Paper trading (simulated)
│
├── strategy/                      # 📈 10 Trading Strategies
│   ├── __init__.py                #    Strategy registry & factory
│   ├── base.py                    #    Abstract strategy class
│   ├── ema_crossover.py           #    EMA 12/26 crossover
│   ├── sma_strategy.py            #    SMA 50/200 crossover
│   ├── rsi_strategy.py            #    RSI mean-reversion
│   ├── macd_strategy.py           #    MACD momentum
│   ├── bollinger_strategy.py      #    Bollinger Bands
│   ├── vwap_strategy.py           #    VWAP (volume-weighted)
│   ├── breakout_strategy.py       #    Support/Resistance breakout
│   ├── mean_reversion.py          #    Z-Score mean reversion
│   ├── momentum_strategy.py       #    Multi-timeframe momentum
│   ├── scalping_strategy.py       #    Fast scalping signals
│   └── signals.py                 #    Signal definitions
│
├── portfolio/                     # 📊 Portfolio Tracker
│   ├── __init__.py                #    Module init
│   ├── tracker.py                 #    Position & P&L tracking
│   └── performance.py             #    Sharpe, drawdown, analytics
│
├── database/                      # 💾 SQLite Persistence
│   ├── __init__.py                #    Module init
│   ├── db.py                      #    Database manager
│   └── trade_repository.py        #    Trade operations
│
├── notifications/                 # 🔔 Alert System
│   ├── __init__.py                #    Notification manager
│   ├── telegram_bot.py            #    Telegram alerts
│   ├── discord_webhook.py         #    Discord alerts
│   └── email_notifier.py          #    Email alerts
│
├── scheduler/                     # ⏱️ Workflow Automation
│   ├── __init__.py
│   ├── trading_scheduler.py       #    Scheduler engine
│   └── market_hours.py            #    Market hours utility
│
├── live/                          # 🔴 Live Trading
│   ├── trading_engine.py          #    Production trading engine
│   └── runner.py                  #    Legacy runner
│
├── data/                          # 📦 Data Layer
│   ├── price_stream.py            #    WebSocket streaming
│   ├── loader.py · validator.py
│   ├── stocks_client.py · crypto_client.py
│   └── models.py
│
├── ai/                            # 🧠 AI Integration
│   ├── ollama_advisor.py          #    LLM market reasoning
│   └── sentiment.py               #    News sentiment analysis
│
├── config/                        # ⚙️ Configuration
│   ├── settings.py                #    Pydantic settings
│   └── assets.py                  #    Symbol registry
│
├── risk/                          # 🛡️ Risk Management
│   ├── risk_manager.py · position_sizer.py
│   ├── stop_loss.py · limits.py
│
├── ml/                            # 🤖 Machine Learning
│   ├── feature_engineer.py · ml_predictor.py
│
├── src/backtesting/               # 🔁 Backtesting Engine
│   ├── engine.py · metrics.py
│   ├── reporter.py · visualization.py
│
├── execution/                     # 💱 Order Execution
│   ├── broker_client.py · paper_trader.py
│   ├── order.py · fill.py
│
├── monitoring/                    # 📊 Monitoring
│   ├── dashboard_server.py · logger.py
│
├── tests/                         # ✅ Test Suite
├── templates/                     # 🎨 HTML Templates
├── utils/                         # 🔧 Utilities
│
├── .env.example                   # Configuration template
├── .gitignore                     # Git ignore rules
├── LICENSE                        # MIT License
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

---

## ⚙️ Configuration

All settings live in `.env`:

| Section | Key Settings |
|:--------|:------------|
| **Mode** | `MODE=PAPER` — BACKTEST, PAPER, or LIVE |
| **Broker** | `BROKER_NAME=alpaca` — paper, alpaca, binance |
| **Strategy** | `STRATEGY_NAME=EMA Crossover` — any of 10 strategies |
| **Risk** | Position limits, stop-loss, daily loss cap |
| **Schedule** | `TRADING_INTERVAL_SECONDS=300` — tick frequency |
| **Notifications** | Telegram token, Discord URL, email SMTP |
| **AI/ML** | Ollama host, model name, retrain interval |

---

## 📊 Performance Metrics

| Metric | What It Measures |
|:-------|:----------------|
| **Total Return** | Overall profit/loss percentage |
| **Sharpe Ratio** | Risk-adjusted return (> 1.0 is good) |
| **Max Drawdown** | Worst peak-to-trough decline |
| **Win Rate** | Percentage of profitable trades |
| **Profit Factor** | Gross profit ÷ gross loss |
| **Calmar Ratio** | Return per unit of max drawdown |

---

## 📈 Distributed Tracing (Phase 2 Week 3)

QuantumTrade implements distributed tracing using OpenTelemetry to monitor and debug the trading system. Traces are exported to Jaeger for visualization and analysis.

### Key Features
- **Automatic Instrumentation**: Traces for Redis, HTTP requests (broker API calls), SQLAlchemy database queries, and logging
- **Manual Spans**: Custom spans for key trading operations (tick processing, signal generation, risk checks, order execution)
- **Trace Context Propagation**: Trace IDs propagate through Redis messages and are injected into structured logs
- **Configurable Sampling**: ParentBased sampling with adjustable rate (default 10% for production)
- **Jaeger Integration**: Traces viewable at http://localhost:16686

### Components
1. **`monitoring/tracing.py`** - OpenTelemetry setup with Jaeger exporter
2. **`tracing/context.py`** - Span context manager, trace ID helpers, and decorators
3. **`tracing/instrumentation.py`** - Manual span creation for trading operations
4. **`monitoring/telemetry.py`** - Combined initialization of logging, metrics, and tracing
5. **Instrumentation Updates** - Automatic tracing of Redis, HTTP, and SQL operations

### Configuration
Set environment variables in `.env`:
```
OTEL_EXPORTER_JAEGER_ENDPOINT=http://localhost:14268/api/traces
OTEL_SAMPLING_RATIO=0.1          # 10% sampling rate (set to 1.0 for dev)
OTEL_SERVICE_NAME=quantumtrade
```

### Running with Jaeger
```bash
# Start Jaeger via Docker Compose
docker-compose up -d jaeger

# Access Jaeger UI
open http://localhost:16686

# View traces for trading operations
```

### Verification
1. Check that Jaeger is running: `docker-compose ps jaeger`
2. Run the trading bot: `python run.py`
3. Visit Jaeger UI to see traces for:
   - Trading tick processing
   - Data fetching (yfinance/CCXT)
   - Signal generation
   - Risk checks
   - Order execution (broker API calls)
   - Database operations
   - Redis message publishing/consuming

---

## 🧪 Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=. --cov-report=term-missing
```

---

## 📦 Tech Stack

| Category | Technologies |
|:---------|:------------|
| **Language** | Python 3.8+ |
| **Brokers** | Alpaca (alpaca-py) · Binance (python-binance) |
| **GUI** | PyQt5 |
| **Data** | pandas · NumPy · yfinance · CCXT |
| **ML** | scikit-learn (RF, GBM) |
| **AI** | Ollama (local LLM) |
| **Web** | Flask · Flask-CORS |
| **Notifications** | Telegram · Discord · Email |

---

## ⚠️ Disclaimer

> This software is for **educational and research purposes only**. Trading financial instruments carries significant risk. Past backtesting performance does NOT guarantee future results. Always paper-trade extensively before risking real capital. The authors accept NO liability for financial losses.

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

<p align="center">
  Made with ❤️ by <strong>Zaid</strong>
</p>
