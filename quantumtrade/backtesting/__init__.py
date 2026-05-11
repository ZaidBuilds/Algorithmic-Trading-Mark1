"""
Backtesting package — production-grade historical strategy simulation.

Components:
- engine: BacktestEngine with MarketSimulator
- metrics: BacktestMetrics, Trade dataclass
- reporter: BacktestReporter, WalkForwardReporter, MonteCarloReporter
- simulation: Microstructure simulation (slippage, latency, spread, impact, liquidity)
- walk_forward: WalkForwardOptimizer for out-of-sample testing
- monte_carlo: MonteCarloRobustnessTester for statistical confidence

Typical usage:

    from quantumtrade.backtesting import BacktestEngine, BacktestReporter
    from quantumtrade.backtesting.simulation import MarketSimulator

    engine = BacktestEngine(
        initial_balance=10000,
        commission=0.001,
        simulator_config={
            "slippage_model": "volume",
            "latency_ms": 150,
            "spread_bps": 1.0,
            "enable_impact": True,
        }
    )
    metrics = engine.run(strategy, data)
    reporter = BacktestReporter(metrics, tca_reports=engine.get_tca_reports())
    reporter.print_summary()
"""

from .engine import BacktestEngine
from .metrics import BacktestMetrics, Trade
from .reporter import BacktestReporter, WalkForwardReporter, MonteCarloReporter
from .walk_forward import WalkForwardOptimizer, WalkForwardResults, WalkForwardFold
from .monte_carlo import MonteCarloRobustnessTester, bootstrap_test_significance
from .simulation import (
    MarketSimulator,
    MarketFill,
    BaseSlippageModel,
    FixedSlippageModel,
    VolumeBasedSlippageModel,
    SquareRootSlippageModel,
    AlmgrenChrissSlippageModel,
    LatencyModel,
    SpreadCostModel,
    AlmgrenChrissImpact,
    LiquidityModel,
    GapRiskModel,
)

__all__ = [
    # Core
    "BacktestEngine",
    "BacktestMetrics",
    "Trade",
    "BacktestReporter",
    # Walk-forward
    "WalkForwardOptimizer",
    "WalkForwardResults",
    "WalkForwardFold",
    "WalkForwardReporter",
    # Monte Carlo
    "MonteCarloRobustnessTester",
    "MonteCarloReporter",
    "bootstrap_test_significance",
    # Simulation subpackage
    "MarketSimulator",
    "MarketFill",
    "BaseSlippageModel",
    "FixedSlippageModel",
    "VolumeBasedSlippageModel",
    "SquareRootSlippageModel",
    "AlmgrenChrissSlippageModel",
    "LatencyModel",
    "SpreadCostModel",
    "AlmgrenChrissImpact",
    "LiquidityModel",
    "GapRiskModel",
]
