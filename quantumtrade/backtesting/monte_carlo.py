"""
Monte Carlo robustness testing for backtest results.

Bootstrap resampling and randomization methods to assess strategy robustness
beyond a single historical path.

Methods:
1. **IID Bootstrap**: Resample trade returns with replacement
2. **Block Bootstrap**: Preserve serial correlation by resampling blocks
3. **Return Randomization**: Randomize trade order
4. **Parameter Shock**: Vary strategy parameters within plausible range

Generates distribution of possible outcomes:
- Percentile-based confidence intervals (5th, 95th)
- Probability of negative return
- Drawdown distribution
- Sharpe ratio distribution
- Win rate stability

Minimum 10,000 simulations recommended for stable percentiles.
"""

from typing import Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from datetime import datetime

from .engine import BacktestEngine
from strategy.base import BaseStrategy
from .metrics import BacktestMetrics, Trade


class MonteCarloRobustnessTester:
    """
    Monte Carlo robustness testing for trading strategies.

    Evaluates strategy stability by simulating many possible
    outcomes from the observed trade return distribution.

    Three test types:
    1. IID Bootstrap: Randomly resample individual trade returns
       Assumption: trades are independent (conservative)
    2. Block Bootstrap: Preserve time series correlation
       Resample consecutive blocks of trades (e.g., 10-trade blocks)
    3. Returns Randomization: Permute trade order (preserves correlation)
       Scrambles sequence while keeping P&L distribution fixed

    Output:
    - Distribution of final equity, total return, Sharpe, max drawdown
    - Confidence intervals (5%, 50%, 95%)
    - Probabilistic metrics (e.g., "5% worst case: -15% return")
    """

    def __init__(
        self,
        strategy_factory: Callable[[Dict[str, Any]], BaseStrategy],
        n_simulations: int = 10000,
        seed: Optional[int] = None,
    ):
        """
        Initialize Monte Carlo tester.

        Args:
            strategy_factory: Function(params) → strategy instance (with fixed params)
            n_simulations: Number of Monte Carlo paths (≥ 10,000)
            seed: Random seed for reproducibility
        """
        self.strategy_factory = strategy_factory
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(seed)

        # Results from original backtest (baseline)
        self.original_metrics: Optional[BacktestMetrics] = None
        self.original_trades: Optional[List[Trade]] = None

    def run_from_trades(
        self,
        trades: List[Trade],
        initial_balance: float = 10000.0,
        bootstrap_method: str = "iid",
        block_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo from list of completed trades.

        Extracts trade returns, resamples, and reconstructs equity curves.

        Args:
            trades: List of Trade objects from original backtest
            initial_balance: Starting equity
            bootstrap_method: "iid", "block", or "randomize"
            block_size: Block length for block bootstrap

        Returns:
            Dict with distribution statistics and confidence intervals
        """
        if not trades:
            return {"error": "No trades provided"}

        self.original_trades = trades

        # Extract trade returns (as fractional returns, not P&L dollars)
        # We need relative returns to scale to any starting balance
        trade_returns = []
        for trade in trades:
            # Use P&L % relative to trade size
            # Approximate: return = (exit - entry) / entry
            if trade.entry_price > 0:
                ret = (trade.exit_price - trade.entry_price) / trade.entry_price
                trade_returns.append(ret)

        if not trade_returns:
            return {"error": "No valid trade returns extracted"}

        trade_returns = np.array(trade_returns)

        # Run simulations
        results = self._run_simulations(
            trade_returns=trade_returns,
            initial_balance=initial_balance,
            method=bootstrap_method,
            block_size=block_size,
        )

        return results

    def run_from_backtest(
        self,
        data: pd.DataFrame,
        strategy_params: Dict[str, Any],
        engine: BacktestEngine,
        bootstrap_method: str = "iid",
        block_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo by first executing one backtest, then resampling.

        Args:
            data: Historical data (used for original backtest)
            strategy_params: Fixed strategy parameters
            engine: BacktestEngine instance
            bootstrap_method: Resampling method
            block_size: Block size for block bootstrap

        Returns:
            Monte Carlo distribution results
        """
        # Execute original backtest
        strategy = self.strategy_factory(strategy_params)
        self.original_metrics = engine.run(strategy=strategy, data=data)
        trades = self.original_metrics.trades

        if not trades:
            return {"error": "No trades in original backtest"}

        initial_balance = engine.initial_balance
        return self.run_from_trades(
            trades=trades,
            initial_balance=initial_balance,
            bootstrap_method=bootstrap_method,
            block_size=block_size,
        )

    def _run_simulations(
        self,
        trade_returns: np.ndarray,
        initial_balance: float,
        method: str = "iid",
        block_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Core Monte Carlo simulation loop.

        Generates n_simulations alternative equity curves.
        """
        n_trades = len(trade_returns)
        simulation_results: List[Dict[str, float]] = []

        for _ in range(self.n_simulations):
            # Resample returns according to method
            if method == "iid":
                sim_returns = self._bootstrap_iid(trade_returns)
            elif method == "block":
                sim_returns = self._bootstrap_block(trade_returns, block_size)
            elif method == "randomize":
                sim_returns = self._randomize_returns(trade_returns)
            else:
                raise ValueError(f"Unknown method: {method}")

            # Reconstruct equity curve
            equity = [initial_balance]
            for ret in sim_returns:
                if np.isnan(ret) or np.isinf(ret):
                    continue
                new_equity = equity[-1] * (1 + ret)
                equity.append(new_equity)

            equity = np.array(equity)

            # Compute metrics
            final_balance = equity[-1]
            total_return_pct = (final_balance - initial_balance) / initial_balance * 100

            # Drawdown
            running_max = np.maximum.accumulate(equity)
            drawdown = (running_max - equity) / running_max
            max_dd_pct = np.max(drawdown) * 100 if len(drawdown) > 0 else 0.0

            # Approximate Sharpe (using trade-based approximation, not daily)
            if len(sim_returns) > 1:
                mean_ret = np.mean(sim_returns)
                std_ret = np.std(sim_returns)
                # Assume average trade duration to annualize — default 5 days/trade
                # Annualization factor = sqrt(trades_per_year)
                # If avg trade duration = 5 trading days → ~50 trades/year
                annual_factor = np.sqrt(50)  # heuristic
                sharpe = (mean_ret * annual_factor) / (std_ret * annual_factor) if std_ret > 0 else 0.0
            else:
                sharpe = 0.0

            # Win rate
            win_rate = np.mean(sim_returns > 0) * 100

            simulation_results.append({
                "total_return_pct": total_return_pct,
                "final_balance": float(final_balance),
                "max_drawdown_pct": max_dd_pct,
                "sharpe_ratio": float(sharpe),
                "win_rate": float(win_rate),
            })

        return self._summarize_distribution(simulation_results)

    def _bootstrap_iid(self, returns: np.ndarray) -> np.ndarray:
        """IID bootstrap — sample trades with replacement."""
        indices = self.rng.integers(0, len(returns), size=len(returns))
        return returns[indices]

    def _bootstrap_block(self, returns: np.ndarray, block_size: int) -> np.ndarray:
        """Block bootstrap — resample consecutive blocks."""
        n = len(returns)
        n_blocks = int(np.ceil(n / block_size))
        blocks = []

        # Create overlapping blocks (moving window) or non-overlapping
        # For simplicity: non-overlapping blocks, repeat to fill
        for i in range(0, n - block_size + 1, block_size):
            blocks.append(returns[i:i+block_size])

        if not blocks:
            return returns.copy()

        # Sample blocks with replacement and concatenate
        block_indices = self.rng.integers(0, len(blocks), size=n_blocks)
        sampled_blocks = [blocks[i] for i in block_indices]
        concatenated = np.concatenate(sampled_blocks)

        # Trim to original length
        return concatenated[:n]

    def _randomize_returns(self, returns: np.ndarray) -> np.ndarray:
        """Randomize order — permutation test."""
        permuted = self.rng.permutation(returns)
        return permuted

    def _summarize_distribution(
        self,
        results: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """
        Compute percentiles and summary statistics.
        """
        df = pd.DataFrame(results)

        percentiles = [1, 5, 25, 50, 75, 95, 99]
        summary = {}

        for col in ["total_return_pct", "final_balance", "max_drawdown_pct", "sharpe_ratio", "win_rate"]:
            if col in df.columns:
                pct_vals = np.percentile(df[col], percentiles)
                summary[col] = {
                    "mean": float(np.mean(df[col])),
                    "std": float(np.std(df[col])),
                    "median": float(np.median(df[col])),
                }
                for p, val in zip(percentiles, pct_vals):
                    summary[col][f"p{p}"] = float(val)

        # Tail risk metrics
        summary["negative_return_probability"] = float(np.mean(df["total_return_pct"] < 0)) * 100
        summary["sharpe_negative_probability"] = float(np.mean(df["sharpe_ratio"] < 0)) * 100

        # 5th percentile worst-case
        summary["worst_5pct_return_pct"] = float(np.percentile(df["total_return_pct"], 5))
        summary["worst_5pct_max_dd_pct"] = float(np.percentile(df["max_drawdown_pct"], 95))  # high is bad

        # Compare to original if available
        if self.original_metrics:
            orig_summary = self.original_metrics.get_summary()
            orig_return = orig_summary.get("total_return", {}).get("percent", 0.0)
            orig_sharpe = orig_summary.get("sharpe_ratio", 0.0)

            summary["original_return_pct"] = float(orig_return)
            summary["original_sharpe"] = float(orig_sharpe)
            summary["return_percentile"] = float(
                np.mean(df["total_return_pct"] <= orig_return) * 100
            )
            summary["sharpe_percentile"] = float(
                np.mean(df["sharpe_ratio"] <= orig_sharpe) * 100
            )

        return summary

    def generate_report(self, results: Dict[str, Any]) -> str:
        """
        Generate text report of Monte Carlo results.
        """
        lines = [
            "=" * 70,
            "MONTE CARLO ROBUSTNESS TEST",
            "=" * 70,
            f"Simulations: {self.n_simulations}",
            "",
            "RETURN DISTRIBUTION",
            "-" * 70,
        ]

        ret = results.get("total_return_pct", {})
        if ret:
            lines.append(f"  Mean return:      {ret.get('mean', 0):.2f}%")
            lines.append(f"  Median return:    {ret.get('median', 0):.2f}%")
            lines.append(f"  5th percentile:   {ret.get('p5', 0):.2f}% (worst-case)")
            lines.append(f"  95th percentile:  {ret.get('p95', 0):.2f}% (best-case)")

        lines.extend([
            "",
            "RISK METRICS",
            "-" * 70,
        ])

        dd = results.get("max_drawdown_pct", {})
        if dd:
            lines.append(f"  Avg max drawdown: {dd.get('mean', 0):.2f}%")
            lines.append(f"  95th %ile DD:     {dd.get('p95', 0):.2f}% (worst-case)")

        lines.extend([
            "",
            "PROBABILITIES",
            "-" * 70,
            f"  P(negative return): {results.get('negative_return_probability', 0):.1f}%",
            f"  P(Sharpe < 0):      {results.get('sharpe_negative_probability', 0):.1f}%",
        ])

        if "original_return_pct" in results:
            lines.extend([
                "",
                "COMPARISON TO ORIGINAL BACKTEST",
                "-" * 70,
                f"  Original return:   {results['original_return_pct']:.2f}%",
                f"  Return percentile: {results['return_percentile']:.1f}%",
                f"  Original Sharpe:   {results['original_sharpe']:.2f}",
                f"  Sharpe percentile: {results['sharpe_percentile']:.1f}%",
            ])

        lines.append("=" * 70)
        return "\n".join(lines)


def bootstrap_test_significance(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    n_simulations: int = 10000,
) -> Dict[str, float]:
    """
    Bootstrap test for statistical significance of strategy outperformance.

    Tests: H0 = strategy == benchmark (no alpha)
    H1 = strategy > benchmark (positive alpha)

    Returns p-value and confidence intervals.
    """
    rng = np.random.default_rng(42)

    # Original excess returns
    excess_original = strategy_returns - benchmark_returns
    original_mean = np.mean(excess_original)

    # Bootstrap
    bootstrap_means = np.zeros(n_simulations)
    for i in range(n_simulations):
        sample = rng.choice(excess_original, size=len(excess_original), replace=True)
        bootstrap_means[i] = np.mean(sample)

    # One-sided p-value (proportion of bootstrap samples ≤ 0)
    p_value = np.mean(bootstrap_means <= 0)

    # Confidence interval (95%)
    ci_lower = np.percentile(bootstrap_means, 2.5)
    ci_upper = np.percentile(bootstrap_means, 97.5)

    return {
        "original_excess_return": float(original_mean),
        "p_value": float(p_value),
        "ci_2.5%": float(ci_lower),
        "ci_97.5%": float(ci_upper),
        "significant_5pct": p_value < 0.05,
    }
