# 🛠️ QuantumTrade: Project Building Plan & Workflow

This document outlines exactly how we architected and built the QuantumTrade system from scratch. It acts as a blueprint for how a Senior Software Architect plans a complex, multi-layered Python trading system.

---

## 🎯 1. Project Goal
**Problem:** Retail traders lose money to emotional decisions and slow execution. Existing bots are either too simple (RSI only) or too complex (C++ institutional HFT).
**User:** A tech-savvy retail trader who wants full control over their funds, utilizing modern AI and Machine Learning without paying monthly SaaS fees.
**Main Features Required:**
- 10+ Technical Trading Strategies (EMA, Bollinger, Breakout).
- Machine Learning predictions (Scikit-Learn).
- AI Market Reasoning (Ollama LLM).
- Real-world Execution (Alpaca for stocks, Binance for crypto).
- Instant notifications & control (Telegram Bot).
- Performance analytics (Sharpe ratio, max drawdown).

---

## 🥞 2. Tech Stack Proposal

### Language
- **Python 3.10+**: The only logical choice for merging Data Science, API integrations, and AI seamlessly.

### Data & Machine Learning Layer
- **Pandas & NumPy:** For insanely fast OHLCV data manipulation and indicator calculation.
- **Scikit-Learn:** For training Random Forest models to predict price direction. Better suited than deep learning for tabular financial data.
- **yfinance / websocket-client:** For fetching historical (polling) and live (streaming) data.

### AI Layer
- **Ollama:** To run LLMs (like Llama 3) locally for privacy and zero cost. It filters out "bad" trades by reading raw market context.

### Execution & Broker Layer
- **alpaca-py & python-binance:** Official SDKs. Using official SDKs guarantees we don't have to manually handle complex WebSocket authentication or HTTP signing.

### Persistence (Database)
- **SQLite:** Chosen over PostgreSQL because this is a local desktop bot. No need to run a heavy database server on a personal laptop.

### Interface & Notifications
- **python-telegram-bot:** The easiest way to build a mobile UI without actually building a mobile app.
- **PyQt5:** For the desktop dashboard, providing a native OS feel.

---

## 🏗️ 3. Full System Architecture

1. **User Action (Telegram):** User sends `/status`.
2. **Controller (Presentation):** The `TelegramController` intercepts this. It asks the `PortfolioTracker` for current state.
3. **State Retrieval (Database):** The `PortfolioTracker` queries the SQLite database for today's P&L and recent trades.
4. **Formatting:** The controller formats this into a beautiful Markdown message.
5. **Response:** Telegram sends the message back to the user's phone.

**When Trading (Automated Flow):**
1. **Scheduler (Cron):** Ticks every 5 minutes.
2. **Data Fetcher:** Grabs the last 60 periods of AAPL prices.
3. **Decision Engine:** Runs 3 layers (Math -> ML -> AI). Generates a BUY signal with 85% confidence.
4. **Risk Manager:** Assesses portfolio cash. Calculates we can buy exactly 14 shares.
5. **Broker Integration:** Sends the HTTP POST to Alpaca.
6. **Notifier:** Sends a Telegram message: `🟢 BOUGHT 14 AAPL`.
7. **Database:** Logs the trade to SQLite for the `PerformanceAnalyzer`.

---

## 🚀 4. The Building Phases

When building a system this complex, you **never** write everything at once. You build it in decoupled layers.

### Phase 1: Core Definitions (The Brains)
- Created the abstract `BaseStrategy` class.
- Implemented the 10 math strategies (EMA, RSI, MACD).
- Why? Because without strategies, the bot is just an empty shell.

### Phase 2: Data & Broker Interfaces (The Hands)
- Created the `Broker` interface (buy, sell, get_positions).
- Drafted the `PaperBroker` (fake money) so we could safely simulate trades without connecting to Alpaca yet.
- Drafted the `DataClient` to pull from Yahoo Finance.

### Phase 3: The Engine & Risk Logic (The Heart)
- Wrote the `DecisionEngine` to aggregate the 3 analysis layers.
- Wrote the `RiskManager` to calculate maximum position sizing.
- Built the `LiveTradingEngine` loop that connects Phase 1 and Phase 2 together.

### Phase 4: Persistence & Tracking (The Memory)
- Created `database/db.py` to save signals and trades.
- Built the `PortfolioTracker` to calculate Sharpe ratios from the database.

### Phase 5: AI & Machine Learning (The Evolution)
- Added `ml_predictor.py` and `ollama_advisor.py`.
- Integrated them into the `DecisionEngine` so they cast "votes" alongside the standard math strategies.

### Phase 6: The User Interface (The Face)
- Built the `TelegramController` to wrap around the whole system, exposing the engine's methods via bot slash commands.
- Configured Real-time WebSockets to replace slow polling.

---

## 🧠 5. Senior Architect Principles Used

1. **Dependency Injection:** The `TradingEngine` doesn't care *which* broker it uses. We pass in `AlpacaBroker` or `PaperBroker` via the constructor. This makes testing 100x easier.
2. **Separation of Concerns:** The `DecisionEngine` generates signals, but it has ZERO power to execute a trade. The `Broker` executes trades, but has ZERO power to decide what to buy. The `RiskManager` sits in between as a firewall.
3. **Fail-Fast Defense:** Every critical block (like `fetch_data()`) has `if data is None: return`. If an API goes down, the bot gracefully aborts the tick instead of crashing and wiping out the portfolio.
4. **Decoupled Configuration:** API keys and sensitive settings are strictly kept in `.env`, completely isolated from the business logic.
