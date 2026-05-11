# 🏗 QuantumTrade: Full System Architecture

This outlines the high-level system design of the trading bot, breaking down how the layers communicate, where the logic lives, and how it can scale to a SaaS platform.

---

## 🏛 The 4 Core Layers

### 1. Presentation & Interaction (Client Layer)
This is the interface the user (or the bot's scheduler) interacts with.
- **Telegram Bot Controller:** Intercepts slash commands (e.g., `/buy AAPL 10`, `/portfolio`).
- **Dashboard API (Flask/React):** A web-based interface or PyQt5 desktop app showing live charts and P&L.
- **CLI App:** The traditional terminal interface to backtest, run tests, or view logs.
- *Responsibility:* Receiving inputs, formatting outputs perfectly for humans (HTML templates, Markdown text), and plotting graphs. It contains **no trading logic**.

### 2. Decision Engine (Server Logic Layer)
This is the "Brain" of the bot, running in a background thread or a heavy infinite loop.
- **Unified 3-Layer Vote:** Passes technical analysis (35%), ML models (40%), and AI LLM rules (25%) over the incoming price streams.
- **Multi-Strategy Runner:** Tests these rules across 10 strategies (EMA crossover, momentum, mean reversion).
- **Risk Management:** Halts trades if daily loss limits are hit, enforces position sizing rules, stops loss trailing.
- *Responsibility:* Crushing thousands of calculations locally. It decides *if* a trade is logical, but it doesn't execute the order.

### 3. Execution & Communication Layer
Where the magic happens. Interfacing with the real world securely.
- **Broker Factory (Alpaca/Binance):** Standardizes API calls so the bot talks to cryptos and stocks identically.
- **Notification Managers:** Uses Discord Webhooks and SMTP handling for instant alerts.
- **WebSocket Price Streamer:** Connects to exchange servers to intercept trades in milliseconds.
- *Responsibility:* Order execution, live data fetching across the network. Handshake authentication using private API keys.

### 4. Persistence (Database Layer)
The memory.
- **SQLite Database:** Files stored entirely locally on disk. 
- **Repositories (TradeRepository):** ORM (Object-Relational Mapping)-like classes that query the database safely.
- *Responsibility:* Saving every trade outcome, holding the historical price models (for ML training), computing Sharpe ratios over months.

---

## 🔀 The Request Flow (A Trading "Tick")

Let's trace exactly what happens when the clock hits the 5-minute interval:

1. **Trigger (Scheduler):** The `TradingScheduler` wakes up the `LiveTradingEngine`.
2. **Fetch Data (Execution):** The Engine asks the `PriceStreamer` for the latest 60 periods of OHLCV data for AAPL.
3. **Analyze (Server Layer):** 
    - The `DecisionEngine` calculates Technical indicators.
    - It runs the ML predictor.
    - It asks Ollama (AI) for market sentiment.
4. **Signal Generated:** The Strategy votes "BUY" with 85% confidence.
5. **Validate Risk (Server Layer):** The signal reaches the `RiskManager`. It verifies we have enough cash, and we don't have too many AAPL shares already. Validated!
6. **Execute (Execution):** The `Broker(Alpaca)` fires an HTTP POST request to the API with our private keys. We buy 10 shares of AAPL at $150.00.
7. **Persist (Database):** The `TradeRepository` saves a new record to SQLite: `Trade(Symbol=AAPL, Side=BUY, Price=150.00)`.
8. **Feedback (Client Layer):** An event fires. `TelegramBot` sends a message to your phone: 🟢 *Execute BUY 10 AAPL @ $150.00*.

---

## 💾 Where Does "State" Live?

State (the current status of the program) is a massive problem in software engineering. If the power goes out, what state gets lost?
1. **Volatile State (RAM):** 
    - Real-time price ticks in the WebSocket queue.
    - Temporary technical indicators.
    - Telegram user active sessions.
    - *If power resets: We just reconnect and fetch the latest prices. No harm.*
2. **Persistent State (Disk):**
    - Account Balance.
    - Open Positions.
    - API Keys.
    - Trade History.
    - *If power resets: The `PortfolioTracker` queries SQLite or the Broker APIs on boot, perfectly restoring the state.*

---

## 🛡️ Validation & Security 

### Where does Validation happen?
- **Frontend/Input:** The Telegram Bot intercepts commands. If you type `/buy 10`, it rejects it immediately ("Missing symbol") without bothering the backend.
- **Backend/Logic:** Before an order goes to the broker, `RiskManager.check_trade()` verifies mathematically that we aren't betting 100% of our portfolio.

### Security Risks
1. **Compromised API Keys:** If the `.env` file is accidentally pushed to GitHub, anyone can empty your Alpaca or Binance accounts. **Solution:** `.gitignore` blocks `.env`.
2. **Unauthorized Telegram Access:** Anyone who finds your bot on Telegram could type `/sell`. **Solution:** The bot checks `update.effective_chat.id` against a hardcoded whitelist in `.env`.
3. **Database Injection:** Bad actors altering SQLite commands. **Solution:** We use parameterized queries (prevents SQL injection).

---

## 🚀 Scaling to 10,000 Users (SaaS Architecture)

Currently, this bot runs on your local machine for **1 user**. If we wanted to sell access to 10,000 users as a Web Service:

1. **Database Layer:** Replace SQLite with PostgreSQL (relational) or TimescaleDB (specifically designed for time-series financial data).
2. **Server Layer:** Extract the heavy logic (`DecisionEngine`) into a distributed queue architecture using **Celery & Redis**. We create "Worker Nodes." 
3. **WebSockets:** Implement **Kafka** to ingest millions of price ticks from Binance, broadcasting them instantly to users.
4. **Environment:** Docker containers deployed to AWS (Elastic Container Service) or Kubernetes. 
5. **Execution:** Instead of handling user keys directly, we would use OAUTH implementations to perform trades securely on behalf of users.
