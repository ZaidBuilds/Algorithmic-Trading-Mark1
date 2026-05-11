"""
Walk-forward optimization (WFO) with rolling windows.

Prevents overfitting by:
1. Splitting data into sequential training/testing windows
2. Optimizing strategy parameters on training set
3. Evaluating on subsequent test set
4. Rolling forward and repeating

Two modes:
- Rolling: fixed-size sliding windows
- Anchored: training window grows (expanding)

Example rolling (default):
  Train [0:252]  → Test [252:315]
  Train [63:315] → Test [315:378]
  Train [126:378] → Test [378:441]
  ...

Example anchored:
  Train [0:252]  → Test [252:315]
  Train [0:315]  → Test [315:378]
  Train [0:378]  → Test [378:441]
  ...

Key metrics:
- OOS (out-of-sample) performance aggregation
- Parameter stability across folds
- Walk-forward efficiency ratio (WFER)
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from .engine import BacktestEngine
from strategy.base import BaseStrategy
from strategy.signals import SignalType
from .metrics import BacktestMetrics


@dataclass(frozen=True)
class WalkForwardFold:
    """Results for a single walk-forward fold."""
    fold_number: int
    train_start: Any
    train_end: Any
    test_start: Any
    test_end: Any
    best_params: Dict[str, Any]
    train_metrics_summary: Dict[str, Any]
    test_metrics_summary: Dict[str, Any]


@dataclass
class WalkForwardResults:
    """
    Aggregate walk-forward optimization results.

    Contains per-fold results and OOS aggregation.
    """
    folds: List[WalkForwardFold] = field(default_factory=list)
    oos_aggregate: Dict[str, Any] = field(default_factory=dict)
    parameter_stability: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate text summary."""
        n_folds = len(self.folds)
        if n_folds == 0:
            return "No walk-forward folds executed."

        lines = [
            "=" * 70,
            "WALK-FORWARD OPTIMIZATION RESULTS",
            "=" * 70,
            f"Number of folds: {n_folds}",
            "",
            "OUT-OF-SAMPLE AGGREGATE",
            "-" * 70,
        ]

        agg = self.oos_aggregate
        lines.append(f"OOS Total Return:   {agg.get('mean_return_pct', 0):.2f}%")
        lines.append(f"OOS Win Rate:        {agg.get('mean_win_rate', 0):.2f}%")
        lines.append(f"OOS Sharpe Ratio:    {agg.get('mean_sharpe', 0):.2f}")
        lines.append(f"OOS Max Drawdown:    {agg.get('mean_max_dd_pct', 0):.2f}%")

        if "positive_folds_pct" in agg:
            lines.append(f"Winning Fold %:      {agg['positive_folds_pct']:.1f}%")

        lines.extend([
            "",
            "PARAMETER STABILITY",
            "-" * 70,
        ])

        stab = self.parameter_stability
        for param, stats in stab.items():
            lines.append(
                f"{param}: mean={stats.get('mean', 0):.4f}, "
                f"std={stats.get('std', 0):.4f}, cv={stats.get('cv', 0):.2%}"
            )

        lines.append("=" * 70)
        return "\n".join(lines)


class WalkForwardOptimizer:
    """
    Walk-forward optimization engine.

    Executes rolling-or-anchored window backtests with parameter optimization
    on each training window, then OOS testing on subsequent window.

    Process:
        For each window:
          1. Split data into train_df, test_df
          2. Grid-search parameters on train set
          3. Run backtest on test set with best params
          4. Record results
          5. Advance window
    """

    def __init__(
        self,
        train_window_days: int = 252,
        test_window_days: int = 63,
        step_days: Optional[int] = None,
        anchored: bool = False,
        objective_metric: str = "total_return_percent",
        greater_is_better: bool = True,
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            train_window_days: Length of training window in trading days
            test_window_days: Length of testing window in trading days
            step_days: Step size between folds (default = test_window_days for rolling)
            anchored: If True, train window expands (anchored WFO)
                     If False, train window slides (rolling WFO)
            objective_metric: Metric to optimize (e.g., "total_return_percent", "sharpe_ratio")
            greater_is_better: Higher metric value is better?
        """
        self.train_window = train_window_days
        self.test_window = test_window_days
        self.step_days = step_days or test_window_days
        self.anchored = anchored
        self.objective_metric = objective_metric
        self.greater_is_better = greater_is_better

    def run(
        self,
        strategy_factory: Callable[[Dict[str, Any]], BaseStrategy],
        param_grid: List[Dict[str, Any]],
        data: pd.DataFrame,
        initial_balance: float = 10000.0,
        commission: float = 0.001,
        **engine_kwargs,
    ) -> WalkForwardResults:
        """
        Execute walk-forward optimization.

        Args:
            strategy_factory: Function(param_dict) -> BaseStrategy instance
            param_grid: List of parameter dicts to search
            data: Full OHLCV DataFrame with DatetimeIndex
            initial_balance: Starting account value
            commission: Commission per trade (e.g., 0.001 = 0.1%)
            **engine_kwargs: Additional args for BacktestEngine

        Returns:
            WalkForwardResults with per-fold and aggregate metrics
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data must have DatetimeIndex")

        if len(data) < self.train_window + self.test_window:
            raise ValueError(
                f"Not enough data: need at least {self.train_window + self.test_window} bars"
            )

        data = data.sort_index()
        folds: List[WalkForwardFold] = []

        # Create single engine reused across folds
        engine = BacktestEngine(
            initial_balance=initial_balance,
            commission=commission,
            **engine_kwargs,
        )

        # Calculate number of folds
        n_folds = (len(data) - self.train_window - self.test_window) // self.step_days + 1
        if n_folds <= 0:
            raise ValueError("Insufficient data for at least one fold")

        # Iterate folds
        for fold_idx in range(n_folds):
            if self.anchored:
                # Anchored: training window grows from start
                train_start_idx = 0
                train_end_idx = self.train_window + fold_idx * self.step_days
            else:
                # Rolling: fixed-size sliding window
                train_start_idx = fold_idx * self.step_days
                train_end_idx = train_start_idx + self.train_window

            test_start_idx = train_end_idx
            test_end_idx = test_start_idx + self.test_window

            # Safety bounds check
            if test_end_idx > len(data):
                break

            train_df = data.iloc[train_start_idx:train_end_idx].copy()
            test_df = data.iloc[test_start_idx:test_end_idx].copy()

            if len(train_df) == 0 or len(test_df) == 0:
                continue

            # Step 1: Optimize on training set
            best_params, train_summary = self._optimize_parameters(
                strategy_factory=strategy_factory,
                param_grid=param_grid,
                train_data=train_df,
                engine=engine,
            )

            # Step 2: Test on OOS with best params
            best_strategy = strategy_factory(best_params)
            test_metrics = engine.run(strategy=best_strategy, data=test_df)
            test_summary = test_metrics.get_summary()

            # Extract summary dict (handle nested vs flat)
            test_metrics_summary = {
                "final_balance": test_summary.get("final_balance"),
                "total_return": test_summary.get("total_return"),
                "total_return_percent": (
                    test_summary.get("total_return", {}).get("percent")
                    if isinstance(test_summary.get("total_return"), dict)
                    else test_summary.get("total_return_percent")
                ),
                "win_rate": (
                    test_summary.get("win_rate", {}).get("win_rate")
                    if isinstance(test_summary.get("win_rate"), dict)
                    else test_summary.get("win_rate")
                ),
                "profit_factor": test_summary.get("profit_factor"),
                "sharpe_ratio": test_summary.get("sharpe_ratio"),
                "max_drawdown": test_summary.get("max_drawdown"),
                "max_drawdown_percent": (
                    test_summary.get("max_drawdown", {}).get("percent")
                    if isinstance(test_summary.get("max_drawdown"), dict)
                    else test_summary.get("max_drawdown_percent")
                ),
            }

            train_metrics_summary = {
                "final_balance": train_summary.get("final_balance"),
                "total_return_percent": train_summary.get("total_return", {}).get("percent"),
                "win_rate": train_summary.get("win_rate", {}).get("win_rate"),
                "profit_factor": train_summary.get("profit_factor"),
                "sharpe_ratio": train_summary.get("sharpe_ratio"),
            }

            fold = WalkForwardFold(
                fold_number=fold_idx + 1,
                train_start=train_df.index[0],
                train_end=train_df.index[-1],
                test_start=test_df.index[0],
                test_end=test_df.index[-1],
                best_params=dict(best_params),
                train_metrics_summary=train_metrics_summary,
                test_metrics_summary=test_metrics_summary,
            )
            folds.append(fold)

        # Aggregate OOS results
        oos_aggregate = self._aggregate_oos_metrics(folds)

        # Parameter stability analysis
        param_stability = self._analyze_parameter_stability(folds)

        results = WalkForwardResults(
            folds=folds,
            oos_aggregate=oos_aggregate,
            parameter_stability=param_stability,
        )

        return results

    def _optimize_parameters(
        self,
        strategy_factory: Callable[[Dict[str, Any]], BaseStrategy],
        param_grid: List[Dict[str, Any]],
        train_data: pd.DataFrame,
        engine: BacktestEngine,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Grid search over parameter combinations on training set.

        Returns:
            (best_params, best_metrics_summary)
        """
        best_score = float("-inf") if self.greater_is_better else float("inf")
        best_params = None
        best_summary = {}

        for params in param_grid:
            strategy = strategy_factory(params)
            metrics = engine.run(strategy=strategy, data=train_data)
            summary = metrics.get_summary()

            # Extract objective metric
            if self.objective_metric == "total_return_percent":
                score = summary.get("total_return", {}).get("percent", 0.0)
            elif self.objective_metric == "sharpe_ratio":
                score = summary.get("sharpe_ratio", 0.0)
            elif self.objective_metric == "final_balance":
                score = summary.get("final_balance", 0.0)
            else:
                score = summary.get(self.objective_metric, 0.0)

            if self.greater_is_better:
                if score > best_score:
                    best_score = score
                    best_params = params
                    best_summary = summary
            else:
                if score < best_score:
                    best_score = score
                    best_params = params
                    best_summary = summary

        return best_params or {}, best_summary

    def _aggregate_oos_metrics(self, folds: List[WalkForwardFold]) -> Dict[str, Any]:
        """Compute OOS aggregate statistics."""
        if not folds:
            return {}

        returns = np.array([f.test_metrics_summary.get("total_return_percent") or 0.0 for f in folds])
        win_rates = np.array([f.test_metrics_summary.get("win_rate") or 0.0 for f in folds])
        sharpes = np.array([f.test_metrics_summary.get("sharpe_ratio") or 0.0 for f in folds])
        max_dds = np.array([f.test_metrics_summary.get("max_drawdown_percent") or 0.0 for f in folds])

        return {
            "n_folds": len(folds),
            "mean_return_pct": float(np.mean(returns)),
            "std_return_pct": float(np.std(returns)),
            "mean_win_rate": float(np.mean(win_rates)),
            "mean_sharpe": float(np.mean(sharpes)),
            "mean_max_dd_pct": float(np.mean(max_dds)),
            "positive_folds_pct": float(np.mean(returns > 0) * 100),
            "median_return_pct": float(np.median(returns)),
            "best_fold_return_pct": float(np.max(returns)),
            "worst_fold_return_pct": float(np.min(returns)),
        }

    def _analyze_parameter_stability(
        self,
        folds: List[WalkForwardFold],
    ) -> Dict[str, Dict[str, float]]:
        """
        Check how much optimal parameters vary across folds.

        High variance indicates strategy is sensitive → less robust.
        """
        if not folds or not folds[0].best_params:
            return {}

        param_values: Dict[str, List[Any]] = {}
        for fold in folds:
            for param, value in fold.best_params.items():
                if param not in param_values:
                    param_values[param] = []
                param_values[param].append(value)

        stability = {}
        for param, values in param_values.items():
            arr = np.array(values, dtype=float)
            if len(arr) > 1:
                mean_val = np.mean(arr)
                std_val = np.std(arr)
                cv = std_val / abs(mean_val) if mean_val != 0 else float("inf")
                stability[param] = {
                    "mean": float(mean_val),
                    "std": float(std_val),
                    "cv": float(cv),
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                }

        return stability


def walk_forward_analysis(
    results: WalkForwardResults,
    data: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Post-analysis of walk-forward results.

    Computes:
    - Walk-forward efficiency ratio (WFER) = OOS / IS performance
    - Consistency score (folds with positive returns)
    - Parameter stability index
    """
    if not results.folds:
        return {}

    # Average IS vs OOS
    is_returns = []
    oos_returns = []

    for fold in results.folds:
        is_ret = fold.train_metrics_summary.get("total_return_percent", 0.0)
        oos_ret = fold.test_metrics_summary.get("total_return_percent", 0.0)
        if is_ret is not None and oos_ret is not None:
            is_returns.append(is_ret)
            oos_returns.append(oos_ret)

    if is_returns and oos_returns:
        avg_is = np.mean(is_returns)
        avg_oos = np.mean(oos_returns)
        wfer = avg_oos / avg_is if avg_is != 0 else 0.0
    else:
        wfer = 0.0

    return {
        "walk_forward_efficiency_ratio": wfer,
        "is_oos_gap_pct": ((avg_oos - avg_is) / abs(avg_is) * 100) if avg_is != 0 else 0.0,
        "oos_positive_pct": results.oos_aggregate.get("positive_folds_pct", 0.0),
        "parameter_violations": len([f for f in results.folds if not f.best_params]),
    }
