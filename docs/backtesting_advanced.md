# Advanced Backtesting Engine — Phase 6

Production-grade realistic simulation with advanced optimization and robustness testing.

## Overview

The `quantumtrade.backtesting` package provides a sophisticated backtesting framework that models real-world market microstructure costs:

- **Slippage** — price movement between signal and execution
- **Latency** — execution delay causing adverse price moves
- **Spread** — bid-ask spread costs for market orders
- **Market Impact** — permanent & temporary price changes from your orders
- **Liquidity** — partial fills and volume constraints
- **Gap Risk** — overnight price jumps that bypass stops
- **Circuit Breakers** — exchange trading halts

Together, these effects turn naive backtests (fill at close) into production-ready simulations.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Simulation Components](#simulation-components)
   - [Slippage Models](#slippage-models)
   - [Latency](#latency)
   - [Spread Costs](#spread-costs)
   - [Market Impact](#market-impact)
   - [Liquidity Constraints](#liquidity-constraints)
   - [Gap Risk](#gap-risk)
3. [MarketSimulator](#marketsimulator)
4. [Transaction Cost Analysis (TCA)](#transaction-cost-analysis-tca)
5. [Walk-Forward Optimization](#walk-forward-optimization)
6. [Monte Carlo Robustness](#monte-carlo-robustness)
7. [Configuration](#configuration)
8. [Best Practices](#best-practices)
9. [Examples](#examples)
10. [Testing](#testing)

---

## Quick Start

```python
from quantumtrade.backtesting import BacktestEngine, BacktestReporter
from quantumtrade.backtesting.simulation import MarketSimulator

# Configure realistic simulation
sim_config = {
    "slippage_model": "impact",       # Almgren-Chriss impact
    "latency_ms": 150,                # 150ms average latency
    "spread_bps": 1.0,                # 1 bps spread
    "enable_impact": True,
    "impact_eta": 0.01,               # Permanent impact coefficient
    "impact_epsilon": 0.05,           # Temporary impact coefficient
    "participation_rate": 0.10,       # Max 10% of bar volume
    "enable_gap_risk": True,
    "seed": 42,
}

engine = BacktestEngine(
    initial_balance=10000,
    commission=0.001,  # 10 bps
    simulator_config=sim_config,
)

metrics = engine.run(strategy, historical_data)
reporter = BacktestReporter(metrics, tca_reports=engine.get_tca_reports())
reporter.print_summary()
```

---

## Simulation Components

### Slippage Models

Slippage is the difference between expected and actual fill price.

#### A. Fixed Slippage

Constant bps regardless of order size.

```python
from quantumtrade.backtesting.simulation import FixedSlippageModel

model = FixedSlippageModel(bps=1.0)  # 1 bps always
```

**Use when:** You want a simple, constant cost assumption.

---

#### B. Volume-Based Slippage

Linear with order participation rate:

```
slippage_bps = k × (quantity / ADV)
```

Typical `k=100–500 bps`. 1% of ADV → 1–5 bps slippage.

```python
from quantumtrade.backtesting.simulation import VolumeBasedSlippageModel

model = VolumeBasedSlippageModel(k=100.0)  # conservative
```

**Use when:** Modeling linear market impact for moderate-sized orders.

---

#### C. Square-Root Slippage

Diminishing returns: double order size → <2× slippage.

```
slippage_bps = σ × √(quantity / ADV)
```

Common in algo trading (`σ ≈ 0.01–0.05`).

```python
from quantumtrade.backtesting.simulation import SquareRootSlippageModel

model = SquareRootSlippageModel(sigma=0.02)  # moderate volatility
```

**Use when:** Modeling typical market impact with concave scaling.

---

#### D. Almgren-Chriss Impact Model

Full decomposition: permanent (linear) + temporary (sqrt) impact.

```
Permanent impact (bps) = η × (Q / ADV) × 10000
Temporary impact (bps) = ε × √(Q / ADV) × 10000
Total impact = Permanent + Temporary
```

Parameters:
- `η` (eta): Permanent impact coefficient (typical 0.001–0.01)
- `ε` (epsilon): Temporary impact coefficient (typical 0.01–0.1)

```python
from quantumtrade.backtesting.simulation import AlmgrenChrissSlippageModel

model = AlmgrenChrissSlippageModel(eta=0.01, epsilon=0.05)
```

**Use when:** Modeling full transaction cost breakdown. Most realistic for larger orders.

---

### Latency

Latency is the delay between signal generation and order execution. During this window, the price may move → slippage.

Model: price movement ~ volatility × √(Δt)

```python
from quantumtrade.backtesting.simulation import LatencyModel

latency = LatencyModel(
    mean_latency_ms=150,   # 150ms typical
    std_latency_ms=50,     # jitter ±50ms
    min_latency_ms=10,
    max_latency_ms=1000,
)

# Simulate a latency sample
latency_ms = latency.sample_latency()

# Estimate price shift during that latency
shifted_price = latency.calculate_price_shift(
    latency_ms=150,
    volatility=0.20,  # 20% annualized
    current_price=100.0,
    side=OrderSide.BUY,
)
# For 150ms at 20% vol, shift ≈ 0.1–0.3 bps
```

**Sources of latency:**
| Source | Typical (ms) |
|--------|-------------|
| Network round-trip | 50–200 |
| Broker API processing | 100–500 |
| Exchange matching | 0–100 |
| **Total** | **150–800** |

---

### Spread Costs

Buy at ask, sell at bid. Half-spread is an implicit cost.

- **Market orders**: Pay half-spread immediately
- **Limit orders**: May receive price improvement (fill inside spread)

```python
from quantumtrade.backtesting.simulation import SpreadCostModel

spread_model = SpreadCostModel(default_spread_bps=1.0)

# For buy order at ask=100.1, mid=100.0
cost_bps = spread_model.calculate_spread_cost(
    side=OrderSide.BUY,
    fill_price=100.1,
    bid_price=100.0,
    ask_price=100.1,
    quantity=1000,
)
# Returns ~1.0 bps (half-spread)
```

**Typical spreads:**
| Asset | Spread (bps) |
|-------|-------------|
| Large-cap US equity | 0.5–2 |
| Small-cap equity | 2–10 |
| Crypto ( BTC/USD ) | 1–5 |
| Crypto ( altcoin ) | 5–50 |
| Forex (major pairs) | 0.1–2 |

---

### Market Impact

When you trade, the market moves. Impact has two parts:

1. **Permanent**: Price stays moved after your trade (information leakage, inventory costs)
2. **Temporary**: Immediate jump that partially reverts (liquidity takers)

The Almgren-Chriss model provides closed-form optimal execution. We use its impact formulas.

```python
from quantumtrade.backtesting.simulation import AlmgrenChrissImpact

impact = AlmgrenChrissImpact(eta=0.01, epsilon=0.05)

# Calculate impact
result = impact.calculate_impact(
    side=OrderSide.BUY,
    order_quantity=100_000,
    avg_daily_volume=1_000_000,  # ADV = 1M
    price=100.0,
)

print(result)
# {
#   'permanent_bps': 10.0,   # η × (100k/1M) × 10000 = 0.01 × 0.1 × 10000
#   'temporary_bps': ~5.0,   # ε × √(0.1) × 10000 ≈ 0.05 × 0.316 × 10000
#   'total_bps': ~15.0,
#   'permanent_dollars': $100,  # 10 bps × $100k notional
#   'temporary_dollars': $50,
#   'total_dollars': $150,
# }
```

Impact scales non-linearly:
| Participation | Permanent Impact | Temporary Impact | **Total** |
|--------------|-----------------|-----------------|-----------|
| 1% | 1 bps | 1.6 bps | 2.6 bps |
| 5% | 5 bps | 3.5 bps | 8.5 bps |
| 10% | 10 bps | 5.0 bps | 15 bps |
| 20% | 20 bps | 7.1 bps | 27 bps |

---

### Liquidity Constraints

Real markets have finite depth. Your order may:
- Only partially fill in the current bar
- Walk the book (consume multiple price levels)
- Leave unfilled remainder

```python
from quantumtrade.backtesting.simulation import LiquidityModel

liquidity = LiquidityModel(
    participation_rate=0.10,   # consume max 10% of bar volume
    min_fill_quantity=1.0,
    allow_partial_fills=True,
)

fill_qty, is_complete = liquidity.determine_fill_quantity(
    order_quantity=100_000,
    bar_volume=500_000,  # this bar saw 500k volume
    order_book_depth=20_000,  # 20k available at best price
)
# Max fill = min(100k, 500k×10%=50k, 20k×10%=2k) → ≈2k
```

**Limit orders** fill only if price reaches the limit:

```python
from quantumtrade.backtesting.simulation import LimitOrderFillModel

limit_model = LimitOrderFillModel(
    fill_probability=0.5,           # 50% chance of fill if price touched
    price_improvement_bps=0.5,      # average improvement inside spread
)

filled, fill_price = limit_model.simulate_limit_fill(
    side=OrderSide.BUY,
    limit_price=99.5,
    high_price=101.0,
    low_price=99.4,  # low touches limit
    volume=1_000_000,
)
```

---

### Gap Risk

Overnight gaps occur when the market closes and reopens at a different price. Stop-loss orders offer **no protection** across gaps.

```python
from quantumtrade.backtesting.simulation import GapRiskModel

gap_model = GapRiskModel(
    gap_probability=0.02,      # 2% of days have a gap
    mean_gap_pct=0.5,          # avg gap size 0.5%
    gap_std_pct=1.0,           # std dev 1% (lognormal)
    max_gap_pct=15.0,          # max plausible gap
)

# Simulate overnight gap
gap_occurred, gap_pct, new_open = gap_model.simulate_gap(
    previous_close=100.0,
)

# Simulate gap stop-loss
triggered, fill_price, slippage_bps = gap_model.adjust_stop_loss_for_gaps(
    stop_price=99.0,       # stop set at 99 (-1%)
    previous_close=100.0,
    side=OrderSide.BUY,    # holding long
)
```

#### Gap probabilities by horizon

| Holding Period | Gap Probability (2% daily) |
|----------------|---------------------------|
| 1 night | 2.0% |
| 1 week | 9.6% |
| 1 month | 45% |

Weekends/holidays: multiply by closure length (2× for Fri→Mon).

---

## MarketSimulator

The `MarketSimulator` orchestrates all cost components in a single `simulate_fill()` call.

### Execution Pipeline

For each order, the simulator:

1. **Liquidity check** — can we fill any quantity this bar?
2. **Determine fill quantity** — partial or full
3. **Select base price** — bid/ask if order book available, else close
4. **Apply spread cost** → adjust base price by half-spread
5. **Sample latency** (50–1000ms random)
6. **Calculate latency-induced shift** — price moved during delay
7. **Compute slippage** — based on order size / ADV
8. **Apply market impact** — permanent + temporary
9. **Handle gaps** (if overnight)
10. **Return `MarketFill`** with full cost breakdown

```python
from quantumtrade.backtesting.simulation import MarketSimulator
from quantumtrade.adapters.execution.models import BrokerOrder, OrderSide
from datetime import datetime

sim = MarketSimulator(
    slippage_model="impact",
    latency_ms=150,
    spread_bps=1.5,
    enable_impact=True,
    impact_eta=0.01,
    impact_epsilon=0.05,
    participation_rate=0.10,
    enable_liquidity_constraints=False,
    enable_gap_risk=True,
    seed=42,
)

order = BrokerOrder(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=10_000,
    order_type=OrderType.MARKET,
    timestamp=datetime.now(),
)

bar = {
    "close": 150.0,
    "high": 151.0,
    "low": 149.0,
    "volume": 1_000_000,
    "timestamp": datetime.now(),
}

# Optional order book
order_book = {
    "bid": 149.9,
    "ask": 150.1,
    "bid_size": 5000,
    "ask_size": 8000,
}

fill = sim.simulate_fill(
    order=order,
    bar=bar,
    order_book=order_book,
    avg_daily_volume=1_000_000,  # ADV
    volatility=0.20,              # 20% annual vol
)

if fill:
    print(f"Fill price: ${fill.price:.4f}")
    print(f"Slippage: {fill.slippage_bps:.1f} bps")
    print(f"Spread: {fill.spread_cost_bps:.1f} bps")
    print(f"Impact: {fill.impact_bps:.1f} bps")
    print(f"Total implicit: {fill.total_implicit_cost_bps:.1f} bps")
    print(f"Total implicit ($): ${fill.total_implicit_cost_dollars:.2f}")
```

---

## Transaction Cost Analysis (TCA)

TCA breaks down the total cost of each trade:

- **Explicit costs**: commissions, fees (clear and visible)
- **Implicit costs**: slippage, spread, market impact (hidden)

The `BacktestEngine` automatically generates a `TransactionCostReport` for every filled order.

### Cost Breakdown Example

```
Order: Buy 10,000 AAPL @ $150.00 arrival

Fill price:         $150.23
Notional:          $1,502,300

Explicit costs:
  Commission (10bps): $1,502.30  (0.10%)

Implicit costs:
  Slippage:          $150.23  (1.00 bps = $150.23)
  Spread cost:       $75.12   (0.50 bps)
  Market impact:     $225.35  (1.50 bps)
  Total implicit:    $450.70  (3.00 bps)

Total cost:         $1,953.00 (1.30% of notional)
```

You can access all reports from the engine:

```python
reports = engine.get_tca_reports()
for r in reports:
    print(f"Symbol: {r.symbol}")
    print(f"  Implicit slippage: {r.implicit_slippage_bps:.1f} bps")
    print(f"  Implicit spread:   {r.implicit_spread_bps:.1f} bps")
    print(f"  Implicit impact:   {r.implicit_impact_bps:.1f} bps")
    print(f"  Total implicit:    {r.total_implicit_cost_bps:.1f} bps")
```

---

## Walk-Forward Optimization

Prevents **overfitting** by testing on out-of-sample windows.

### How It Works

1. Split data chronologically into training + testing windows
2. Optimize strategy parameters on training window
3. Test best parameters on subsequent test window
4. Roll forward and repeat

```
Window 1:  Train [0:252]  → Test [252:315]   (252 trading days = 1 year)
Window 2:  Train [63:315] → Test [315:378]
Window 3:  Train [126:378] → Test [378:441]
      ...
```

**Rolling** (default): fixed-size sliding windows

**Anchored**: training window grows

```python
from quantumtrade.backtesting import WalkForwardOptimizer
from quantumtrade.backtesting.engine import BacktestEngine

wfo = WalkForwardOptimizer(
    train_window_days=252,  # 1 year
    test_window_days=63,    # 3 months
    anchored=False,         # rolling windows
    objective_metric="sharpe_ratio",
    greater_is_better=True,
)

results = wfo.run(
    strategy_factory=lambda params: MyStrategy(**params),
    param_grid=[
        {"fast_ema": 10, "slow_ema": 30},
        {"fast_ema": 20, "slow_ema": 50},
        {"fast_ema": 5,  "slow_ema": 15},
    ],
    data=historical_data,
    initial_balance=10000,
    commission=0.001,
)

print(results.oos_aggregate)
# {
#   'n_folds': 5,
#   'mean_return_pct': 12.5,
#   'mean_win_rate': 58.2,
#   'mean_sharpe': 1.34,
#   'positive_folds_pct': 80.0,  # 4/5 folds profitable
# }

print(results.parameter_stability)
# {
#   'fast_ema': {'mean': 12.5, 'std': 2.5, 'cv': 0.20},  # stable
#   'slow_ema': {'mean': 38.3, 'std': 12.1, 'cv': 0.32}, # moderate variance
# }
```

### Interpretation

- **Positive OOS performance** → strategy genuinely works out-of-sample
- **Low parameter variance** → robust, stable strategy
- **Consistent win rate** across folds → reliable edge
- **Walk-Forward Efficiency Ratio (WFER)** = OOS return / IS return
  - WFER > 0.5 considered acceptable
  - WFER < 0.3 suggests overfitting

---

## Monte Carlo Robustness Testing

Given the observed trade history, what's the range of possible outcomes? Monte Carlo answers by resampling trades.

### Methods

1. **IID Bootstrap** — randomly resample individual trade returns with replacement
   - Assumes trades independent (conservative)
2. **Block Bootstrap** — resample blocks of consecutive trades
   - Preserves serial correlation (drawdown clusters)
3. **Randomization** — permute trade order
   - Keeps distribution fixed, breaks timing

```python
from quantumtrade.backtesting import MonteCarloRobustnessTester

tester = MonteCarloRobustnessTester(
    strategy_factory=lambda p: MyStrategy(**p),
    n_simulations=10000,   # 10k paths
    seed=42,
)

# Load trades from backtest
trades = metrics.trades

results = tester.run_from_trades(
    trades=trades,
    initial_balance=10000,
    bootstrap_method="iid",   # or "block", "randomize"
    block_size=10,            # for block bootstrap
)

print(tester.generate_report(results))
```

### Output Statistics

```
MONTE CARLO ROBUSTNESS TEST (10,000 simulations)

RETURN DISTRIBUTION
  Mean return:        +15.2%
  Median return:      +14.8%
  5th percentile:     -8.3%   ← worst-case scenario
  95th percentile:    +42.1%  ← best-case

RISK METRICS
  Avg max drawdown:   18.5%
  95th %ile DD:       32.1%   ← worst-case drawdown

PROBABILITIES
  P(negative return): 12.3%
  P(Sharpe < 0):      8.2%

COMPARISON TO ORIGINAL BACKTEST
  Original return:    +16.0%  (57th percentile)
  Original Sharpe:    1.42     (62nd percentile)
```

**Interpretation:**
- Median return ≈ original → backtest typical
- 5th percentile at -8% → worst-case still not terrible (accept)
- Only 12% chance of negative → high confidence
- 95th DD 32% → could experience this drawdown

If 5th percentile return is deeply negative (-40%), strategy is fragile → avoid.

---

## Configuration

All simulation parameters live in `quantumtrade.config.settings.backtest_simulation`:

```yaml
backtest_simulation:
  # Slippage
  SLIPPAGE_MODEL: "impact"        # fixed, volume, sqrt, impact
  FIXED_SLIPPAGE_BPS: 1.0
  IMPACT_ETA: 0.01
  IMPACT_EPSILON: 0.05

  # Latency
  LATENCY_MS: 150.0

  # Spread
  SPREAD_BPS: 1.0

  # Liquidity
  PARTICIPATION_RATE: 0.10        # 10% of bar volume
  ENABLE_LIQUIDITY_CONSTRAINTS: false

  # Feature flags
  ENABLE_MARKET_IMPACT: true
  ENABLE_GAP_RISK: true
  ENABLE_CIRCUIT_BREAKERS: false

  # Walk-forward
  WALK_FORWARD_ENABLED: false
  WF_TRAIN_WINDOW_DAYS: 252
  WF_TEST_WINDOW_DAYS: 63
  WF_ANCHORED: false

  # Monte Carlo
  MONTE_CARLO_ENABLED: false
  MC_SIMULATIONS: 10000
  MC_BOOTSTRAP_METHOD: "iid"
  MC_BLOCK_SIZE: 10
```

Access via settings singleton:

```python
from quantumtrade.config.settings import settings

config = settings.backtest_simulation
print(config.SLIPPAGE_MODEL)  # "impact"
```

---

## Best Practices

### Slippage

| Order size (vs ADV) | Expected slippage (bps) |
|---------------------|------------------------|
| < 1% | 0.5–2 bps |
| 1–5% | 2–8 bps |
| 5–10% | 8–20 bps |
| > 10% | 20+ bps (non-linear) |

**Rule of thumb:** Slippage ≈ 1 bps per 1% of ADV for moderate sizes.

### Latency

- Use realistic latency: 50–200ms for retail API, 1–10ms for colocated HFT
- Larger volatility → larger latency-induced slippage
- Consider stochastic (not fixed) latency

### Impact

- **Eta** (`η`): starts around 0.01 for large-cap equities
- **Epsilon** (`ε`): starts around 0.05
- Calibrate to your asset class using historical trades

### Liquidity

- Turn on `enable_liquidity_constraints` for large orders (>5% ADV)
- Participation rate 5–10% is realistic for algorithmic execution
- Below 5%: can assume fill each bar; above 10%: multi-day execution

### Gap Risk

- For overnight holds: enable `enable_gap_risk`
- Stop-losses **do not** protect across gaps — simulate explicitly
- Weekend gaps ≈ 2× daily gap probability

### Walk-Forward

- Training window: 1–2 years (≥252 trading days)
- Testing window: 1–3 months (63–252 days)
- Minimum 5 folds for statistical significance
- Anchored (expanding) windows for more stable parameters

### Monte Carlo

- Use at least 10,000 simulations for stable percentiles
- Compare original backtest to Monte Carlo percentile:
  - 40–60% → expected (backtest typical)
  - >80% → lucky backtest (overfit?)
  - <20% → unlucky backtest (might be better than it looks)
- Block bootstrap recommended for correlated returns

---

## Examples

### Example 1: Basic Backtest with Realistic Costs

```python
from quantumtrade.backtesting import BacktestEngine, BacktestReporter
from quantumtrade.strategy.momentum import MomentumStrategy
import yfinance as yf

# Download data
data = yf.download("SPY", period="2y", interval="1d")

# Configure simulation
config = {
    "slippage_model": "impact",
    "latency_ms": 150,
    "spread_bps": 0.5,
    "impact_eta": 0.005,
    "impact_epsilon": 0.03,
    "enable_gap_risk": True,
    "seed": 123,
}

engine = BacktestEngine(
    initial_balance=100000,
    commission=0.0005,  # 5 bps
    simulator_config=config,
)

strategy = MomentumStrategy(fast_period=10, slow_period=30)
metrics = engine.run(strategy, data)

reporter = BacktestReporter(metrics, tca_reports=engine.get_tca_reports())
reporter.print_summary()
```

### Example 2: Walk-Forward Optimization

```python
from quantumtrade.backtesting import WalkForwardOptimizer
from quantumtrade.backtesting.engine import BacktestEngine

wfo = WalkForwardOptimizer(
    train_window_days=252,
    test_window_days=63,
    anchored=False,
    objective_metric="sharpe_ratio",
)

param_grid = [
    {"fast": 5, "slow": 20},
    {"fast": 10, "slow": 30},
    {"fast": 20, "slow": 50},
]

results = wfo.run(
    strategy_factory=lambda p: EMACrossoverStrategy(p["fast"], p["slow"]),
    param_grid=param_grid,
    data=data,
    initial_balance=50000,
)

print(results.oos_aggregate["mean_sharpe"])
print(f"Winning fold %: {results.oos_aggregate['positive_folds_pct']:.1f}%")

# Check parameter stability
for param, stats in results.parameter_stability.items():
    print(f"{param}: CV={stats['cv']:.2%}")  # <30% CV typically stable
```

### Example 3: Monte Carlo Robustness

```python
from quantumtrade.backtesting import MonteCarloRobustnessTester

tester = MonteCarloRobustnessTester(
    strategy_factory=lambda p: MyStrategy(**p),
    n_simulations=20000,
    seed=777,
)

results = tester.run_from_backtest(
    data=data,
    strategy_params={"threshold": 0.02},
    engine=engine,
    bootstrap_method="block",
    block_size=20,
)

reporter = MonteCarloReporter(results)
print(reporter.generate_summary_text())

# Key question: How bad can it get?
worst_5pct_return = results["total_return_pct"]["p5"]
print(f"5th percentile return (worst-case): {worst_5pct_return:.1f}%")
```

### Example 4: Comparing Impact Models

```python
from quantumtrade.backtesting.simulation import create_slippage_model

models = {
    "Fixed 1bps": create_slippage_model("fixed", fixed_slippage_bps=1.0),
    "Volume-based": create_slippage_model("volume", k=100.0),
    "Square-root": create_slippage_model("sqrt", sigma=0.02),
    "Almgren-Chriss": create_slippage_model("impact", impact_eta=0.01, impact_epsilon=0.05),
}

adv = 1_000_000
for name, model in models.items():
    bps = model.calculate_slippage_bps(
        side="BUY",
        quantity=10_000,
        price=100.0,
        avg_daily_volume=adv,
    )
    print(f"{name}: {bps:.1f} bps")
```

Output:
```
Fixed 1bps: 1.0 bps
Volume-based: 100.0 bps  (!) — inappropriate k
Square-root: 2.0 bps
Almgren-Chriss: ~3.5 bps (linear 1 + sqrt 2.5)
```

---

## Testing

All modules have ≥30 tests covering:

- Slippage model accuracy (`test_slippage_models.py`)
- Latency simulation (`test_latency_simulation.py`)
- Market impact formulas (`test_market_impact.py`)
- Liquidity & gap models (`test_gap_risk.py`)
- Walk-forward correctness (`test_walk_forward.py`)
- Monte Carlo distributions (`test_monte_carlo.py`)
- Full engine integration (`test_full_backtest_simulation.py`)

Run tests:

```bash
pytest quantumtrade/tests/unit/test_*.py -v
# or all tests:
pytest
```

---

## Success Criteria

✅ Slippage model produces realistic costs (1–10 bps typical for 1–5% ADV)  
✅ Latency simulation shifts fill price appropriately (sub-bps for 150ms)  
✅ Walk-forward produces stable OOS performance (low parameter variance)  
✅ Monte Carlo gives meaningful confidence intervals (5th/95th percentiles)  
✅ All 30+ tests pass  
✅ Backtest reports include realistic cost analysis  

---

## Further Reading

- **Almgren & Chriss (2000)**: "Optimal Execution of Portfolio Transactions"
- **Kissell (2006)**: "The Science of Algorithmic Trading"
- **TradeCost Analytics**: [Global market impact models](https://tradecostanalytics.com)
- **Market Microstructure**: Order book dynamics, spread formation

---

## License

Part of QuantumTrade trading system — use responsibly. Past simulation performance ≠ future results.
