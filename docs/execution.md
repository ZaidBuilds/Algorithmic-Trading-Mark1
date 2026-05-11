# Execution Layer Documentation

Enterprise-grade order execution system for QuantumTrade.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Execution Algorithms](#execution-algorithms)
   - [TWAP](#twap)
   - [VWAP](#vwap)
   - [POV](#pov)
   - [Implementation Shortfall](#implementation-shortfall)
   - [Iceberg](#iceberg)
4. [Transaction Cost Analysis (TCA)](#transaction-cost-analysis-tca)
5. [Fill Simulator](#fill-simulator)
6. [Smart Order Router](#smart-order-router)
7. [Broker Selection](#broker-selection)
8. [Configuration](#configuration)
9. [Usage Examples](#usage-examples)
10. [Monitoring & Metrics](#monitoring--metrics)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The execution layer (`quantumtrade.adapters.execution`) provides sophisticated order routing, algorithmic execution, and comprehensive transaction cost analysis. It minimizes market impact and slippage while providing post-trade analytics.

**Key Features:**

- **Multiple execution algorithms** optimized for different market conditions
- **Smart broker routing** with automatic failover and consensus routing
- **Realistic fill simulation** for backtesting with configurable slippage and impact models
- **Deep TCA** breaking down explicit and implicit costs
- **Metrics integration** with Prometheus for live monitoring

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SmartOrderRouter                          │
│  Orchestrates orders, selects algorithms & brokers         │
└─────────────┬───────────────────────────┬───────────────────┘
              │                           │
    ┌─────────▼──────┐          ┌────────▼─────────┐
    │  Execution     │          │  BrokerSelector  │
    │  Algorithms    │          │  (routing logic) │
    └────────┬───────┘          └────────┬─────────┘
             │                           │
    ┌────────▼───────┐          ┌────────▼─────────┐
    │ FillSimulator  │          │ BaseBroker(s)    │
    │ (backtest)     │          │  (Alpaca, Binance)│
    └────────┬───────┘          └───────────────────┘
             │
    ┌────────▼─────────┐
    │  TCA Analyzer    │
    │  (cost breakdown)│
    └──────────────────┘
```

---

## Execution Algorithms

### TWAP

**Time-Weighted Average Price** — splits order into equal-sized slices distributed evenly over time.

- **Best for:** Illiquid instruments, minimizing market footprint, predictable schedules.
- **Parameters:**
  - `duration_minutes` — total execution window (default 30)
  - `num_slices` — number of child orders; if unspecified, auto-calculated from duration

**How it works:** Order is divided into N equal parts. Each slice is sent at regular intervals regardless of volume. This yields a time-averaged price near the true TWAP.

**Example:**

```python
from quantumtrade.adapters.execution.smart_router import SmartOrderRouter

router = SmartOrderRouter(brokers={...})
order = BrokerOrder(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=1000,
    algorithm=AlgorithmType.TWAP,
    algo_params={"duration_minutes": 30}
)
report = router.execute_order(order)
```

**When to use:** You care only about averaging time risk, not volume participation.

---

### VWAP

**Volume-Weighted Average Price** — allocates slices based on historical intraday volume profile.

- **Best for:** Liquid equities, achieving benchmark participation
- **Parameters:**
  - `target_participation_rate` — % of market volume to target (default 10%)
  - `duration_minutes` — execution window
  - `volume_profile` — custom list of volume percentages per bucket (overrides default)

**How it works:** The day's typical volume pattern (e.g., more volume at open/close) is used to schedule larger slices during high-volume periods, improving benchmark performance.

**When to use:** Large orders where matching volume is important.

---

### POV

**Percentage of Volume** — adaptive participation rate, scaling order size to real-time volume.

- **Best for:** Hiding order size, participating opportunistically
- **Parameters:**
  - `participation_rate` — target % of current volume (default 10%)
  - `min_slice_size`, `max_slice_size` — bounds on child order size
  - `lookahead_minutes` — short-term volume forecast horizon

**How it works:** As volume arrives, the algorithm places orders of size `participation_rate * observed_volume`. If volume spikes, order scales up; if dry, waits. This provides excellent slicing but requires continuous monitoring.

**When to use:** Very large orders in very liquid markets, or when minimizing signal leakage is critical.

---

### Implementation Shortfall

**Almgren–Chriss optimal execution** — mathematically optimizes the trade-off between market impact and timing risk.

- **Best for:** Precise risk-controlled liquidation, optimal cost
- **Parameters:**
  - `risk_aversion` (λ) — higher values prioritize urgency (front-loaded) over market impact; range 0.0001–0.01
  - `urgency` — desired completion horizon multiplier
  - `volatility` — expected price volatility
  - `num_periods` — number of slices

**How it works:** Solves the optimal control problem: minimize `Impact Cost + λ * Variance Risk`. Results in a curved front-loaded schedule for sells (sell early) and buys (buy early) depending on risk aversion.

**Formula intuition:** `q_k = X * sinh(α(T−k)) / sinh(αT)` for sell path.

**When to use:** When you have a clear risk budget and want mathematically optimal execution.

---

### Iceberg

**Hidden order slicing** — displays only a small visible quantity while replenishing hidden size.

- **Best for:** Hiding true order size on HFT-friendly exchanges
- **Parameters:**
  - `display_qty` — visible quantity per order (default: auto ~2% of total)
  - `refresh_speed` — minimum seconds between visible order refreshes
  - `max_slippage_bps` — pause if slippage exceeds threshold

**How it works:** Only a fraction of the total order is shown in the order book at any time. After that slice fills, a new child order with the same displayed size is submitted, maintaining a hidden reserve.

**When to use:** Large, passive orders on exchanges that support iceberg orders (e.g., Binance, Coinbase).

---

## Transaction Cost Analysis (TCA)

TCA dissects the **total cost** of a trade into explicit and implicit components.

### Cost Breakdown

| Component | Description |
|---|---|
| **Explicit Costs** | Broker commissions, exchange fees, taxes |
| **Slippage** | Difference between arrival price and fill price |
| **Spread Cost** | Cost of crossing bid–ask spread |
| **Market Impact** | Permanent price change caused by the trade |
| **Implementation Shortfall** | Combined slippage + impact relative to arrival |

All costs are reported in **basis points (bps)** where 1 bps = 0.01%.

### Using the TCA Analyzer

```python
from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer

tca = TransactionCostAnalyzer(benchmark="arrival")  # or "vwap", "twap"

report = tca.analyze_execution(
    order=my_order,
    fills=list_of_fills,
    market_data=price_dataframe,  # OHLCV around execution window
    pre_trade_benchmark=150.0,    # optional, else inferred from data
    post_trade_benchmark=151.0,   # optional
)
print(f"Total cost: {report.total_cost_bps:.1f} bps")
print(f"Implementation shortfall: {report.implementation_shortfall_bps:.1f} bps")
```

**Report fields:**

```python
TransactionCostReport(
    order_id: str
    symbol: str
    side: OrderSide
    filled_quantity: float
    weighted_avg_price: float
    total_notional: float
    explicit_commission: float
    explicit_fees: float
    implicit_slippage: float      # $
    implicit_slippage_bps: float
    implicit_spread: float
    implicit_spread_bps: float
    implicit_impact: float
    implicit_impact_bps: float
    total_cost_bps: float
    implementation_shortfall_bps: float
    execution_duration_seconds: float
)
```

### Benchmark Selection

| Benchmark | Use When... |
|---|---|
| `arrival` | Compare to price when order entered system |
| `vwap` | Compare to day's volume-weighted average |
| `twap` | Compare to time-weighted average |
| custom | Provide `pre_trade_benchmark` and `post_trade_benchmark` manually |

---

## Fill Simulator

Simulates how an order would fill in historical data for **backtesting**.

### Models

| Model | Behavior |
|---|---|
| `fixed` | Adds/subtracts fixed bps to price |
| `volume` | Slippage proportional to order size / ADV |
| `sqrt` | Square-root impact (common market impact) |
| `linear` | Linear with quantity |

### Configuration

```python
from quantumtrade.adapters.execution.fill_simulator import FillSimulator

sim = FillSimulator(
    slippage_model="volume",          # "fixed", "volume", "sqrt", "linear"
    fixed_slippage_bps=1.0,           # only used if model=="fixed"
    enable_spread_cost=True,          # add spread cost component
    enable_market_impact=True,        # apply impact model
    fill_probability=0.95,            # chance of fill per bar (for liquidity simulation)
    unlimited_liquidity=False,        # backtest often sets True
    min_fill_quantity=1.0,            # ignore tiny fills
)
```

### Usage in Backtest

```python
fill = sim.simulate_fill(order, bar, avg_daily_volume=1_000_000)
if fill:
    execution_price = fill.price
    # fill includes slippage, spread, impact baked in
```

---

## Smart Order Router

`SmartOrderRouter` is the main façade for the execution layer.

### Initialization

```python
from quantumtrade.adapters.execution.smart_router import SmartOrderRouter
from quantumtrade.adapters.execution.broker_selector import BaseBroker

# Provide broker instances
brokers = {
    "alpaca": AlpacaBroker(api_key="...", secret="..."),
    "binance": BinanceBroker(api_key="...", secret="..."),
}

router = SmartOrderRouter(
    brokers=brokers,
    default_algorithm="twap",
    data_client=my_market_data_client,  # optional
    redis_client=redis,                  # optional
    execution_config={
        "slippage_model": "volume",
        "fixed_slippage_bps": 1.0,
        "max_slippage_bps": 10.0,
    },
)
```

### API

| Method | Purpose |
|---|---|
| `execute_order(order, algorithm, **algo_params)` | Submit order for execution (async in live mode) |
| `add_fill(order_id, fill)` | Used internally / by broker adapters to register fills |
| `get_execution_report(order_id)` | Fetch detailed `ExecutionReport` for completed order |
| `get_tca_summary(order_id)` | Get dict of TCA metrics |
| `cancel_order(order_id)` | Cancel in-flight order |
| `get_active_orders()` | List currently active parent orders |
| `reset()` | Clear internal state (useful between backtest runs) |

### Order Lifecycle

1. **Submit** — `execute_order()` assigns IDs, selects broker, generates child order schedule.
2. **Monitor** — In live mode, broker adapter pushes fills via `add_fill()`.
3. **Complete** — When all child orders filled, report is generated automatically.

---

## Broker Selection

`BrokerSelector` scores brokers on fees, latency, fill-rate, and depth.

### Customizing Broker Scoring

Extend `BaseBroker` and override `get_score()` to add custom logic.

```python
class MyBroker(BaseBroker):
    def get_score(self) -> float:
        base = super().get_score()
        # Add custom factor: e.g., prefer brokers with specific symbols
        return base * (1.2 if "BTC" in self.supported_symbols else 1.0)
```

### Consensus Routing

Split order across multiple brokers:

```python
allocation = broker_selector.split_across_brokers(
    order,
    current_price=100.0,
    min_slice=100,
)
# {'broker_a': 600, 'broker_b': 400}
```

---

## Configuration

### ExecutionConfig

```python
from quantumtrade.adapters.execution.base import ExecutionConfig

config = ExecutionConfig(
    default_algorithm="twap",
    enable_smart_routing=True,
    slippage_model="volume",
    fixed_slippage_bps=1.0,
    target_participation_rate=0.10,
    twap_default_duration_minutes=30,
    max_slippage_bps=10.0,     # reject orders >10bps estimated slippage
    enable_iceberg=False,
)
```

### Environment Variables

| Variable | Description |
|---|---|
| `EXECUTION_DEFAULT_ALGO` | Default algorithm (twap/vwap/pov/etc.) |
| `EXECUTION_SLIPPAGE_MODEL` | Which slippage model to use |
| `EXECUTION_MAX_SLIPPAGE_BPS` | Maximum acceptable slippage (reject if higher) |
| `BROKER_PRIMARY` | Primary broker name |
| `BROKER_FALLBACK` | Comma-separated fallback chain |

---

## Usage Examples

### Basic Market Order (Immediate Fill)

```python
order = BrokerOrder(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=100,
    order_type=OrderType.MARKET,
)
report = router.execute_order(order)  # algorithm = market (default fallback)
```

### TWAP Over 30 Minutes

```python
order = BrokerOrder(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=10000,
    algorithm=AlgorithmType.TWAP,
    algo_params={"duration_minutes": 30}
)
report = router.execute_order(order)
print(f"Avg price: {report.weighted_avg_price:.2f}")
```

### VWAP With Custom Profile

```python
order = BrokerOrder(
    symbol="AAPL",
    side=OrderSide.SELL,
    quantity=5000,
    algorithm=AlgorithmType.VWAP,
    algo_params={
        "duration_minutes": 60,
        "target_participation_rate": 0.15,  # 15% of volume
    },
)
```

### Iceberg on Binance

```python
order = BrokerOrder(
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    quantity=10,  # BTC
    algorithm=AlgorithmType.ICEBERG,
    algo_params={
        "display_qty": 0.5,   # show only 0.5 BTC each time
        "refresh_speed": 1,   # seconds
    },
)
```

---

## Monitoring & Metrics

The execution layer emits Prometheus metrics under the `quantumtrade_` prefix.

| Metric | Type | Labels | Description |
|---|---|---|---|
| `quantumtrade_algorithm_orders_total` | Counter | algorithm, side | Orders routed to each algo |
| `quantumtrade_execution_cost_basis_points` | Gauge | symbol, side, algorithm, broker | Total cost in bps |
| `quantumtrade_slippage_basis_points` | Gauge | symbol, side, algorithm | Slippage bps |
| `quantumtrade_spread_cost_basis_points` | Gauge | symbol, side | Spread cost bps |
| `quantumtrade_impact_cost_basis_points` | Gauge | symbol, side, algorithm | Impact bps |
| `quantumtrade_implementation_shortfall_bps` | Gauge | symbol, side, algorithm | Shortfall bps |
| `quantumtrade_child_orders_total` | Counter | algorithm, parent_order_id | Child orders created |
| `quantumtrade_fill_latency_seconds` | Histogram | broker, algorithm | Time from submit to fill |

Access metrics at `http://localhost:8000/metrics` after starting the metrics server.

---

## Troubleshooting

### High Slippage

**Symptom:** TCA reports show > 10 bps slippage consistently.

**Likely causes:**
- `slippage_model` set to `"volume"` with high ADV? Verify ADV input.
- Order size too large relative to market liquidity.
- Using market orders in illiquid conditions.

**Fixes:**
- Switch algorithm to `TWAP` (spreads over time).
- Reduce `target_participation_rate` in VWAP/POV.
- Increase `num_slices` to reduce per-slice impact.

### No Fills in Backtest

**Symptom:** `fill_simulator.simulate_fill()` returns None.

**Cause:** `fill_probability` < 1 or volume limits.

**Fix:** Set `unlimited_liquidity=True` and `fill_probability=1.0` for backtest.

### Broker Not Selected

**Symptom:** `router.execute_order()` fails with "no suitable broker".

**Cause:** All brokers disconnected or min/max order value not met.

**Fix:** Verify broker connection; adjust `min_order_value`, `max_order_value` on broker instances.

### TCA Report Missing Fields

**Symptom:** `total_cost_bps` = 0 even though trade executed.

**Cause:** Market data missing required columns (`Close`, `Volume`).

**Fix:** Ensure `market_data` DataFrame has `Close` column and preferably `Volume`; provide `pre_trade_benchmark` manually if needed.

---

## Performance Considerations

- **Backtest speed:** FillSimulator is pure Python; consider using `numba` if profiling shows bottleneck.
- **Metrics overhead:** Prometheus counters/gauges are cheap; avoid high-cardinality label values (e.g., use symbol, not full ticker string if many).
- **Memory:** TCA reports stored in memory; batch-export to CSV/DB regularly for long backtests.

---

## Future Enhancements

- Support for **limit orders** and **stop orders** in algorithms
- **Real-time adaptivity**: dynamically adjust on volatility spikes
- **Cross-exchange aggregation** for crypto multi-venue routing
- **Machine learning** based slippage prediction (learn from historical fills)
