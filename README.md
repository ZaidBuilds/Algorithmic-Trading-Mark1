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

```
┌──────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                         │
│   CLI (app.py)  ·  GUI (dashboard_app)  ·  Telegram Bot 🤖   │
├──────────────────────────────────────────────────────────────┤
│                    PORTFOLIO TRACKER                          │
│   Position Tracking · Equity Curve · Sharpe · Max Drawdown   │
├──────────────────────────────────────────────────────────────┤
│                    NOTIFICATION LAYER                         │
│   Telegram Bot  ·  Discord Webhook  ·  Email (SMTP)          │
├──────────────────────────────────────────────────────────────┤
│                    DECISION ENGINE                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐  │
│  │ Technical  │  │  ML Model  │  │  AI + Sentiment        │  │
│  │ (35% wt.)  │  │  (40% wt.) │  │  (25% wt.)            │  │
│  └─────┬──────┘  └─────┬──────┘  └───────┬────────────────┘  │
│        └───────────────┼──────────────────┘                   │
│                        ▼                                      │
│     Multi-Strategy Runner → Ensemble / Per-Symbol             │
│              Unified Signal → BUY / SELL / HOLD               │
├──────────────────────────────────────────────────────────────┤
│                    EXECUTION LAYER                            │
│   Broker Factory → Alpaca (Stocks) │ Binance (Crypto) │ Paper │
│   Order Manager  · Risk Manager  · Position Tracker           │
├──────────────────────────────────────────────────────────────┤
│                    SCHEDULER                                  │
│   Market Hours Detection · Cron Ticks · Session Events        │
├──────────────────────────────────────────────────────────────┤
│                    DATA LAYER                                 │
│   WebSocket Streaming (Binance/Alpaca) · yfinance · CCXT      │
├──────────────────────────────────────────────────────────────┤
│                    PERSISTENCE                                │
│   SQLite (trades, signals, snapshots) · Settings KV Store     │
└──────────────────────────────────────────────────────────────┘
```

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

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/<your-username>/quantumtrade.git
cd quantumtrade

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your broker API keys, notification tokens, etc.
```

### 3. Launch

```bash
# ── One Command To Rule Them All ─────────────
python run.py                        # Uses settings from .env

# ── Override broker/strategy ─────────────────
python run.py --broker paper         # Paper trading
python run.py --broker alpaca        # Alpaca live
python run.py --strategy VWAP        # Use VWAP strategy
python run.py --no-telegram          # Without Telegram bot

# ── Desktop Dashboard ────────────────────────
python dashboard_app.py

# ── CLI Backtest ─────────────────────────────
python app.py backtest --symbol AAPL --strategy "EMA Crossover"
```

---

## 📁 Project Structure

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
