# QuantumTrade — Phase 1: Event-Driven Architecture

## Quick Start (Complete)

### 1. Install Dependencies

```bash
# From project root
python -m venv .venv
.venv\Scripts\activate  # Windows or source .venv/bin/activate

# Install all dependencies (existing + new)
pip install -r requirements.txt

# New packages specifically for event system
pip install redis pyyaml
```

Verify installation:
```bash
python -c "import redis, yaml; print('OK')"
```

### 2. Start Infrastructure (Docker)

```bash
# Start Redis and PostgreSQL
docker-compose up -d

# Wait ~30 seconds for health checks to pass
docker-compose ps

# Verify Redis is running
redis-cli ping
# Expected: PONG

# Verify PostgreSQL is running
# (use pgAdmin or psql)
```

**Note:** If you don't have Docker, install Redis and PostgreSQL manually:
- Redis: https://redis.io/download
- PostgreSQL: https://www.postgresql.org/download/

### 3. Configuration

The system reads config from multiple sources (priority order):
1. **Environment variables** (highest) — e.g., `QT_BROKER_NAME=alpaca`
2. **YAML file** — `config/quantumtrade.yaml`
3. **.env file** — `.env` in project root
4. **Defaults** — built into code

#### Minimal .env

```bash
# Broker
BROKER_NAME=paper
PAPER_TRADING=true

# Optional: API keys for live trading
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here

# Notifications (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

#### Optional YAML Config

```bash
cp config/quantumtrade.yaml.example config/quantumtrade.yaml
```

Edit `config/quantumtrade.yaml` for bulk settings (overrides .env defaults).

### 4. Run the Bot

No code changes required! The engine automatically detects and uses the event system.

```bash
python run.py                    # Paper trading (default)
python run.py --broker alpaca    # Alpaca live (if keys configured)
python run.py --broker binance   # Binance live (if keys configured)
python run.py --strategy "EMA Crossover"
python run.py --no-telegram      # Disable Telegram
```

**Expected output (excerpt):**
```
==================================================
  ⚡ QuantumTrade v2.0
  AI-Powered Algorithmic Trading System
==================================================
  Broker:     paper
  Strategy:   EMA Crossover
  Symbols:    AAPL, GOOG
  Mode:       PAPER
  Interval:   300s
==================================================

[INFO] Event-driven mode auto-enabled (Redis available)
[INFO] MarketDataHandler initialized
[INFO] SignalHandler initialized
[INFO] OrderHandler initialized
[INFO] Consumer started: group=trading_engine, streams=['events:orders']
...
```

### 5. Verify Event System

Open a new terminal:

```bash
# Connect to Redis CLI
redis-cli

# Stream lengths
XLEN events:market_data   # Market data events count
XLEN events:signals       # Signal events count
XLEN events:orders        # Order events count
XLEN events:trades        # Trade events count

# Consumer groups
XINFO GROUPS events:signals
XINFO GROUPS events:orders

# Check for failed events
XLEN events:dead_letter
# If > 0, inspect:
XRANGE events:dead_letter - + COUNT 10

# Monitor all streams (in separate terminals)
XREAD COUNT 1 STREAMS events:signals $
XREAD COUNT 1 STREAMS events:trades $
```

Python console:
```python
>>> from quantumtrade.events import get_message_bus
>>> bus = get_message_bus()
>>> print(bus.get_metrics())
{
  'events_published': 152,
  'events_consumed': 148,
  'errors': 0,
  'consumer_lag': {'events:signals': 4},
  'running': True,
  'connection': 'connected'
}
```

---

## Troubleshooting

### Redis Connection Refused

**Symptom:** `Redis health check failed` or `Error 10061 connecting to localhost:6379`

**Fix:**
```bash
# Ensure Docker containers are running
docker-compose ps

# If stopped, start them
docker-compose up -d

# Check Redis logs
docker-compose logs -f redis
```

### Import Errors: `No module named 'quantumtrade'`

**Cause:** Tests/scripts run from wrong directory.

**Fix:** Run from project root:
```bash
cd D:\zaidsystem\02_Coding\Projects\algotrading\tradingbotv1
python tests/test_phase1_quick.py
```

### YAML Config: "File not found" Warning

**Cause:** `config/quantumtrade.yaml` doesn't exist.

**Fix:** Optional — ignore or create:
```bash
cp config/quantumtrade.yaml.example config/quantumtrade.yaml
```

### Event System Not Detected

**Symptom:** Engine runs in direct mode, not event-driven.

**Check:**
```python
>>> from live.trading_engine import LiveTradingEngine
>>> engine = LiveTradingEngine(broker_name='paper', symbols=['AAPL'])
>>> engine._event_mode
True  # Should be True if Redis reachable
```

**If False:**
1. Verify redis is running: `redis-cli ping`
2. Check Python can import `quantumtrade.events`
3. Ensure `redis` package installed: `pip show redis`

---

## Development Commands

### Run Tests

```bash
# Fast event tests
pytest tests/test_events.py -v

# Phase 1 verification
python tests/test_phase1_quick.py

# All tests (existing + new)
pytest tests/ -v
```

### Manual Message Publishing

```python
from quantumtrade.events import MarketDataEvent, get_message_bus

bus = get_message_bus()

# Publish a market data event
event = MarketDataEvent(
    symbol="AAPL",
    timeframe="1m",
    ohlcv={
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000000,
    }
)
msg_id = bus.publish(event)
print(f"Published: {msg_id}")
```

### Docker Management

```bash
# Start
docker-compose up -d

# Stop (keep volumes)
docker-compose down

# Stop + remove volumes (WIPE DATA)
docker-compose down -v

# Logs
docker-compose logs -f redis
docker-compose logs -f postgres

# Shell into Redis
docker-compose exec redis redis-cli

# Shell into Postgres
docker-compose exec postgres psql -U quantum -d quantumtrade
```

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                       Trading Engine                           │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Scheduler tick every N seconds                           │ │
│  └───────────────┬──────────────────────────────────────────┘ │
│                  ▼                                             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  For each symbol: fetch OHLCV → calculate indicators      │ │
│  └───────────────┬──────────────────────────────────────────┘ │
│                  ▼                                             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Generate signal (BUY/SELL/HOLD) + confidence             │ │
│  └───────────────┬──────────────────────────────────────────┘ │
│         ┌────────┴─────────┐                                   │
│         │                  │                                   │
│         ▼  DIRECT MODE    ▼  EVENT MODE                        │
│  ┌──────────────┐   ┌──────────────────┐                       │
│  │ Call broker  │   │ Publish          │                       │
│  │ directly     │   │ SignalEvent      │                       │
│  └──────────────┘   └────────┬─────────┘                       │
│                              ▼                                 │
│                      ┌─────────────────┐                        │
│                      │ SignalHandler   │                        │
│                      │ (risk check)    │                        │
│                      └────────┬────────┘                        │
│                               ▼                                │
│                      ┌─────────────────┐                        │
│                      │ OrderHandler    │◄─────┐                 │
│                      │ (broker call)   │      │                 │
│                      └────────┬────────┘      │ (broker fills)  │
│                               ▼               │                 │
│                      ┌─────────────────┐      │                 │
│                      │ Publish Trade   │──────┘                 │
│                      │ Event           │                        │
│                      └─────────────────┘                        │
│                               │                                 │
│                               ▼                                 │
│                      [DB Logger + Notification + Portfolio]    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
                     ┌────────────────────┐
                     │   Redis Streams    │
                     │ (Durable Queue)    │
                     └────────────────────┘
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QT_MESSAGE_BUS_URL` | `redis://localhost:6379/0` | Redis URL |
| `QT_EVENT_STREAM_MAX_LEN` | `10000` | Max stream length |
| `QT_CONSUMER_GROUP` | `quantumtrade` | Consumer group prefix |
| `QT_BROKER_NAME` | `paper` | `paper`, `alpaca`, `binance` |
| `QT_PAPER_TRADING` | `true` | Paper mode flag |
| `QT_SYMBOLS` | `["AAPL","GOOG"]` | Symbols (space-separated) |
| `QT_TRADING_INTERVAL_SECONDS` | `300` | Tick frequency |
| `QT_MAX_POSITION_SIZE_PCT` | `0.10` | Max 10% per position |

Full list: See `quantumtrade/config/config_schema.py`

### Redis Stream Names

| Stream | Events | Consumer Groups |
|--------|--------|----------------|
| `events:market_data` | MarketDataEvent | data_feed |
| `events:signals` | SignalEvent | trading_engine, risk_engine, monitor |
| `events:orders` | OrderEvent | trading_engine |
| `events:trades` | TradeEvent | risk_engine, portfolio |
| `events:risk` | RiskEvent | trading_engine, monitor |
| `events:system` | SystemEvent | monitor, logger |
| `events:dead_letter` | Failed events | (manual inspection) |

---

## Success Checklist

- [ ] Docker containers running (`docker-compose ps`)
- [ ] Redis responds (`redis-cli ping` → PONG)
- [ ] PostgreSQL accessible on port 5432
- [ ] `python run.py` starts without errors
- [ ] Engine shows "Event-driven mode auto-enabled"
- [ ] `XLEN events:orders` > 0 after first tick
- [ ] `XINFO GROUPS events:orders` shows consumer group
- [ ] All 15 `test_events.py` tests pass
- [ ] `test_phase1_quick.py` => 5/5 groups passed
- [ ] Existing `tests/test_*.py` still pass (no regressions)

---

**Phase 1 Complete.** The event-driven foundation is production-ready and fully backward compatible.
