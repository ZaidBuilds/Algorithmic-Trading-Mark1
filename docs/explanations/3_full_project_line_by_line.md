# 🔬 Full Project Core: Line-By-Line Explanation

This document explains the **4 most important files** in the QuantumTrade system line-by-line. If you understand these files, you understand the entire architecture of the 92-file project, because these 4 files control and call all the others.

---

## 1. `run.py` (The Entry Point)
*This is the script you run to wake up the bot. It loads settings, configures the database, and starts the engine.*

```python
import logging
import asyncio
from config.settings import settings
from database.db import Database
from brokers import get_broker
from live.trading_engine import LiveTradingEngine
from telegram_controller import TelegramController
```
- **What it does:** Imports built-in Python tools (`logging`, `asyncio`) and our custom modules. 
- **Why it is needed:** You cannot use code from another file without importing it first.
- **Category:** Imports / File Structure.

```python
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
```
- **What it does:** Configures the logging system to print messages to the terminal with a timestamp, severity level (INFO, ERROR), and the message itself.
- **Why it is needed:** Without logging, if the bot crashes, we have no idea why. `print()` is amateur; `logging` allows us to filter errors or save them to a file.
- **Category:** Monitoring / Debugging.

```python
def main():
```
- **What it does:** Defines the main entry point function.
- **Why it is needed:** Wrapping execution code in a `main()` function is a Python best practice to prevent code from running accidentally if the file is imported elsewhere.

```python
    logger.info("🚀 Starting QuantumTrade Engine...")
```
- **What it does:** Prints a startup message to the terminal.

```python
    db = Database(db_path=settings.DB_PATH)
    db.connect()
```
- **What it does:** Creates an instance of our SQLite `Database` class using the path defined in `.env` (via `settings.DB_PATH`). Then, it opens the connection to the disk file.
- **Why it is needed:** The database must be ready before the trading engine starts so we can load previous positions and save new trades.
- **Category:** Persistence Layer.

```python
    broker = get_broker(settings.BROKER_NAME)
```
- **What it does:** Uses a "Factory Pattern". It looks at our `.env` file (e.g., `BROKER_NAME="alpaca"`). It then magically returns the correct broker class (e.g., `AlpacaBroker`) pre-configured with our API keys.
- **Why it is needed:** Instead of writing complex `if` statements throughout the code to check which broker we use, we just use a unified `broker` object. 

```python
    engine = LiveTradingEngine(
        broker=broker,
        db=db,
        strategy_name=settings.STRATEGY_NAME,
        symbols=settings.SYMBOLS
    )
```
- **What it does:** Instantiates the massive `LiveTradingEngine` (The Heart). We inject the `broker` and `db` we just created, along with the strategy to use and the stocks to trade (from `.env`).
- **Why it is needed:** This is "Dependency Injection". The engine relies on external tools to function. By handing them to the engine, the engine doesn't have to create them itself.
- **Category:** Core Instantiation.

```python
    if settings.TELEGRAM_TOKEN:
        bot = TelegramController(
            token=settings.TELEGRAM_TOKEN,
            allowed_chat_ids=settings.TELEGRAM_CHAT_IDS,
            engine=engine,
            broker=broker,
            db=db
        )
        bot.start()
```
- **What it does:** Checks if you provided a Telegram API token. If yes, it creates the remote control bot, handing it the `engine`, `broker`, and `db` so the bot can ask them for data (e.g., when you type `/status`). It then starts the bot in a background thread.
- **Category:** Presentation Layer (UI).

```python
    engine.start()
```
- **What it does:** Commands the trading engine to begin its infinite loop, waking up every 5 minutes (or as scheduled) to trade. This line blocks the program from exiting.

```python
if __name__ == "__main__":
    main()
```
- **What it does:** Checks if this exact file (`run.py`) was executed directly from the terminal (e.g., `python run.py`). If true, it calls `main()`.
- **Why it is needed:** Prevents `main()` from running if another script incorrectly imports `run.py`.

---

## 2. `decision_engine.py` (The Brains)
*This file takes historical prices and decides mathematically if we should buy or sell.*

```python
class DecisionEngine:
    def __init__(self, strategy_name: str):
        self.strategy = get_strategy(strategy_name)
        self.ml_predictor = MLPredictor()
        self.ollama_advisor = OllamaAdvisor()
```
- **What it does:** When the engine is created, it loads the 3 pillars of trading: 
  1. Traditional Math Strategy (e.g., EMA Crossover)
  2. Machine Learning (`ml_predictor`)
  3. AI Chat LLM (`ollama_advisor`)
- **Category:** Object Constructor.

```python
    def analyze(self, symbol: str, data: pd.DataFrame) -> Signal:
```
- **What it does:** Defines a method that takes a stock symbol and its historical prices (`DataFrame`). It promises to return a `Signal` object (Buy, Sell, or Hold).

```python
        # 1. Technical Analysis (35% weight)
        tech_data = self.strategy.calculate_indicators(data)
        tech_signal = self.strategy.generate_signal(tech_data)
```
- **What it does:** Hands the raw price data to the mathematical strategy. Usually, this adds new columns for Moving Averages. It then asks the strategy for a pure math-based signal.
- **Why it is needed:** Technical analysis captures the immediate trend.

```python
        # 2. Machine Learning (40% weight)
        ml_confidence = self.ml_predictor.predict(data)
```
- **What it does:** Passes the exact same prices to a Random Forest ML model to predict the probability that the next candle will be positive.

```python
        # 3. AI / LLM Reasoning (25% weight)
        ai_sentiment = self.ollama_advisor.evaluate(symbol, tech_data)
```
- **What it does:** Converts the numbers to text and asks the local AI model (Ollama) if the market conditions look like a trap. returns a sentiment score.

```python
        # Final Aggregation
        final_score = (tech_signal.confidence * 0.35) + (ml_confidence * 0.40) + (ai_sentiment * 0.25)
```
- **What it does:** A weighted average. ML gets the most voting power because it's statistically backtested. Human-like logic (AI) gets the least because LLMs can hallucinate.

```python
        if final_score >= 0.70:
            return Signal(SignalType.BUY, confidence=final_score)
        elif final_score <= 0.30:
            return Signal(SignalType.SELL, confidence=final_score)
        else:
            return Signal(SignalType.HOLD, confidence=final_score)
```
- **What it does:** Converts the mathematical score back into a human action. If the combined agreement of Math + ML + AI is above 70%, we buy. If below 30%, we short/sell. Note that the vast middle (30% to 70%) defaults to HOLD to prevent over-trading in uncertain markets.

---

## 3. `live/trading_engine.py` (The Heart)
*This runs the infinite loop, coordinates the broker, risk manager, and decision engine.*

```python
class LiveTradingEngine:
    def _run_loop(self):
        while self.is_running:
            now = datetime.now()
            if self.scheduler.should_run(now):
                self._tick()
            time.sleep(1)
```
- **What it does:** An infinite loop. As long as the bot hasn't been stopped by the user, it checks the current time. It asks the `scheduler` "Is it time to trade yet?" (e.g., has the 5-minute candle closed?). If yes, it calls `_tick()`. It then pauses for 1 second so it doesn't max out your CPU.
- **Why it is needed:** This is the pulse of the system. Without it, the bot runs once and exits.
- **Category:** Concurrency / Main Application Loop.

```python
    def _tick(self):
        logger.info(f"⏰ Execution Tick: {datetime.now()}")
        for symbol in self.symbols:
            self._process_symbol(symbol)
```
- **What it does:** Iterates through every stock you told it to trade (e.g., `["AAPL", "TSLA", "BTCUSDT"]`) and processes them one at a time.

```python
    def _process_symbol(self, symbol: str):
        account = self.broker.get_account()
        position = self.broker.get_position(symbol)
```
- **What it does:** Calls out to the internet (Alpaca/Binance) to get your exact cash balance and checks if you currently own shares of this specific stock.
- **Why it is needed:** State retrieval. We cannot make decisions without knowing our exact financial reality at this exact second.

```python
        if position:
            self.risk_manager.check_stop_loss(position, current_price)
```
- **What it does:** If we DO own the stock, the first priority is Defense. It checks if the current price has dropped below our safety net (Stop Loss). If yes, the `risk_manager` will trigger a panic sell.

```python
        signal = self.decision_engine.analyze(symbol, current_data)
```
- **What it does:** Sends the data to the Brain (File #2) and gets a BUY/SELL/HOLD signal.

```python
        if signal.is_buy() and not position:
            qty = self.risk_manager.calculate_position_size(signal.price, account.cash)
            self.broker.place_order(BrokerOrder(symbol, BUY, qty))
```
- **What it does:** If the Brain says buy, AND we don't already own it, we calculate how many shares we can afford (never risking >5% of cash) and send a market order over the internet to the exchange.

---

## 4. `telegram_controller.py` (The Face)
*This connects the backend logic to your mobile phone via Telegram's API.*

```python
class TelegramController:
    def __init__(self, token, allowed_chat_ids, engine):
        self.token = token
        self.allowed_chat_ids = allowed_chat_ids
        self.engine = engine
```
- **What it does:** The controller loads your secret Telegram token and a list of allowed User IDs (so random strangers can't control your money). It also holds a reference to the `engine` so it can boss it around.

```python
    async def _check_auth(self, update) -> bool:
        chat_id = str(update.effective_chat.id)
        if chat_id not in self.allowed_chat_ids:
            await update.message.reply_text("⛔ Unauthorized user.")
            return False
        return True
```
- **What it does:** A security firewall. Every time someone sends a message to the bot, this function extracts their hidden Telegram ID. If it's not in your `.env` file, it rejects them immediately.
- **Category:** Security / Middleware.

```python
    async def _cmd_portfolio(self, update, context):
        if not await self._check_auth(update): return
        
        self.portfolio_tracker.update()
        msg = self.portfolio_tracker.telegram_report()
        await update.message.reply_text(msg, parse_mode="Markdown")
```
- **What it does:** An asynchronous command handler. When you type `/portfolio` on your phone, Telegram hits this function. 
  1. It checks your ID (Security).
  2. It commands the `portfolio_tracker` to sync with the database and broker.
  3. It generates a formatted text string (`telegram_report()`).
  4. It sends that text right back to your phone, styled with bold text and emojis (`Markdown`).

---

### 📝 Summary of Data Flow (The Big Picture)

1. You start `run.py`. It builds the isolated pieces (`Broker`, `Database`) and clicks them like Lego bricks into the `LiveTradingEngine` and `TelegramController`. 
2. The `LiveTradingEngine` starts its beating heart (`_run_loop`), downloading data via WebSockets and checking the time.
3. Once an interval hits, it uses the `DecisionEngine` to run intense mathematical and AI calculations on the price arrays.
4. If the AI spots a breakout, it commands the `Broker` to fire an HTTP request to Wall Street, actually buying the stock.
5. Meanwhile, if you are sitting on a train, you type `/portfolio` into your phone. The `TelegramController` intercepts it, reads SQLite, and texts you back telling you exactly how much money the Engine just made you.
