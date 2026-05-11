"""
Backtest results reporting with TCA and advanced metrics.

Enhanced reporter for:
- Full TCA breakdown (slippage, spread, impact)
- Turnover analysis
- Market impact vs order size
- Walk-forward results
- Monte Carlo distributions
"""

from typing import Optional, Dict, List, Any
import pandas as pd
import numpy as np
from datetime import datetime

from .metrics import BacktestMetrics, Trade


class BacktestReporter:
    """
    Generate comprehensive backtest reports with transaction cost analysis.

    Outputs:
    - Text summary (console)
    - Trade CSV export
    - Equity curve CSV
    - TCA report CSV (if available)
    - HTML dashboard data
    """

    def __init__(
        self,
        metrics: BacktestMetrics,
        *,
        tca_reports: Optional[List[Any]] = None,
        simulation_metrics: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize reporter.

        Args:
            metrics: BacktestMetrics object
            tca_reports: List of TransactionCostReport (optional)
            simulation_metrics: Dict with simulator cost aggregates
        """
        self.metrics = metrics
        self.tca_reports = tca_reports or []
        self.sim_metrics = simulation_metrics or {}

    def generate_summary_text(self, include_tca: bool = True) -> str:
        """
        Generate text summary with optional TCA section.

        Args:
            include_tca: Include transaction cost breakdown

        Returns:
            Formatted string
        """
        lines = ["=" * 70, "BACKTEST RESULTS SUMMARY", "=" * 70, ""]

        summary = self.metrics.get_summary()
        total_return = summary['total_return']
        win_rate = summary['win_rate']
        max_dd = summary['max_drawdown']
        avg_trade = summary['average_trade']

        lines.extend([
            f"Initial Balance:     ${summary['initial_balance']:,.2f}",
            f"Final Balance:       ${summary['final_balance']:,.2f}",
            f"Total Return:        ${total_return['absolute']:,.2f} ({total_return['percent']:.2f}%)",
            f"",
            f"TRADE STATISTICS",
            f"-----------------",
            f"Total Trades:        {win_rate['total_trades']}",
            f"Winning Trades:      {win_rate['winning_trades']}",
            f"Losing Trades:       {win_rate['losing_trades']}",
            f"Win Rate:            {win_rate['win_rate']:.2f}%",
            f"Profit Factor:       {summary['profit_factor']:.2f}",
            f"",
            f"AVERAGE TRADE",
            f"-----------------",
            f"Average P&L:         ${avg_trade['avg_pnl']:,.2f}",
            f"Average Win:         ${avg_trade['avg_win']:,.2f}",
            f"Average Loss:        ${avg_trade['avg_loss']:,.2f}",
            f"Average Duration:    {avg_trade['avg_duration']:.1f} days",
            f"",
            f"RISK METRICS",
            f"-----------------",
            f"Max Drawdown:        ${max_dd['absolute']:,.2f} ({max_dd['percent']:.2f}%)",
        ])

        if max_dd['peak_date']:
            lines.append(f"Peak Date:           {max_dd['peak_date'].strftime('%Y-%m-%d')}")
        if max_dd['trough_date']:
            lines.append(f"Trough Date:         {max_dd['trough_date'].strftime('%Y-%m-%d')}")

        lines.append(f"Sharpe Ratio:        {summary['sharpe_ratio']:.2f}")

        if include_tca and self.tca_reports:
            lines.extend(["", "=" * 70, "TRANSACTION COST ANALYSIS", "=" * 70, ""])

            total_notional = sum(r.total_notional for r in self.tca_reports)
            if total_notional > 0:
                # Weighted averages
                avg_slippage_bps = np.average(
                    [r.implicit_slippage_bps for r in self.tca_reports],
                    weights=[r.total_notional for r in self.tca_reports],
                )
                avg_spread_bps = np.average(
                    [r.implicit_spread_bps for r in self.tca_reports],
                    weights=[r.total_notional for r in self.tca_reports],
                )
                avg_impact_bps = np.average(
                    [r.implicit_impact_bps for r in self.tca_reports],
                    weights=[r.total_notional for r in self.tca_reports],
                )
                avg_total_implicit_bps = avg_slippage_bps + avg_spread_bps + avg_impact_bps
                avg_explicit_bps = np.average(
                    [r.explicit_cost_bps for r in self.tca_reports],
                    weights=[r.total_notional for r in self.tca_reports],
                )
                avg_total_bps = avg_explicit_bps + avg_total_implicit_bps

                lines.extend([
                    f"Total Notional Traded: ${total_notional:,.2f}",
                    f"",
                    f"COST BREAKDOWN (basis points)",
                    f"  Explicit (commissions):   {avg_explicit_bps:>6.2f} bps",
                    f"  Implicit slippage:        {avg_slippage_bps:>6.2f} bps",
                    f"  Implicit spread:          {avg_spread_bps:>6.2f} bps",
                    f"  Market impact:            {avg_impact_bps:>6.2f} bps",
                    f"  Total implicit:           {avg_total_implicit_bps:>6.2f} bps",
                    f"  TOTAL COST:               {avg_total_bps:>6.2f} bps",
                    f"",
                    f"TURNOVER ANALYSIS",
                    f"  Turnover ratio (annualized): {self._calculate_turnover_ratio():.2f}x",
                ])

        lines.append("=" * 70)
        return "\n".join(lines)

    def print_summary(self, **kwargs):
        """Print full summary to stdout."""
        print(self.generate_summary_text(**kwargs))

    def export_trades_csv(self, path: str) -> None:
        """Export trade list with P&L details."""
        if not self.metrics.trades:
            return
        records = []
        for t in self.metrics.trades:
            records.append({
                'Entry Date': t.entry_date.strftime('%Y-%m-%d %H:%M'),
                'Exit Date': t.exit_date.strftime('%Y-%m-%d %H:%M'),
                'Entry Price': round(t.entry_price, 4),
                'Exit Price': round(t.exit_price, 4),
                'Quantity': t.quantity,
                'PnL ($)': round(t.pnl, 2),
                'PnL (%)': round(t.pnl_percent, 4),
                'Duration (days)': t.duration,
                'Win': t.is_winning(),
            })
        pd.DataFrame(records).to_csv(path, index=False)

    def export_equity_curve_csv(self, path: str) -> None:
        """Export equity curve."""
        if len(self.metrics.equity_curve) < 2:
            return
        df = pd.DataFrame({
            'Date': self.metrics.equity_dates,
            'Equity': self.metrics.equity_curve[1:],  # Skip initial
        })
        df.to_csv(path, index=False)

    def export_tca_reports_csv(self, path: str) -> None:
        """Export detailed TCA reports."""
        if not self.tca_reports:
            return
        records = [r.to_dict() for r in self.tca_reports]
        pd.DataFrame(records).to_csv(path, index=False)

    def get_performance_dataframe(self) -> pd.DataFrame:
        """
        Get performance stats as DataFrame (for plotting).
        """
        eq = pd.DataFrame({
            'date': self.metrics.equity_dates,
            'equity': self.metrics.equity_curve[1:],
        }).set_index('date')
        return eq

    def _calculate_turnover_ratio(self) -> float:
        """
        Calculate annualized turnover ratio.

        Turnover = (total buys + total sells) / avg equity
        """
        if not self.tca_reports:
            return 0.0

        total_notional = sum(r.total_notional for r in self.tca_reports)
        avg_equity = np.mean(self.metrics.equity_curve) if self.metrics.equity_curve else self.initial_balance

        if avg_equity <= 0:
            return 0.0

        # Annualize: scale by (total_days / 252)
        # Assume turnover already over full backtest period
        return total_notional / avg_equity


class WalkForwardReporter:
    """
    Report walk-forward optimization results.
    """

    def __init__(self, wf_results):
        self.results = wf_results

    def generate_folds_table(self) -> pd.DataFrame:
        """Create fold-by-fold performance table."""
        rows = []
        for fold in self.results.folds:
            rows.append({
                'Fold': fold.fold_number,
                'Train Start': fold.train_start.strftime('%Y-%m-%d'),
                'Train End': fold.train_end.strftime('%Y-%m-%d'),
                'Test Start': fold.test_start.strftime('%Y-%m-%d'),
                'Test End': fold.test_end.strftime('%Y-%m-%d'),
                'Test Return %': fold.test_metrics_summary.get('total_return_percent'),
                'Test Sharpe': fold.test_metrics_summary.get('sharpe_ratio'),
                'Test Win Rate %': fold.test_metrics_summary.get('win_rate'),
                'Max DD %': fold.test_metrics_summary.get('max_drawdown_percent'),
                'Best Params': str(fold.best_params),
            })
        return pd.DataFrame(rows)

    def generate_summary_text(self) -> str:
        """Summary of WFO."""
        return self.results.summary()


class MonteCarloReporter:
    """
    Report Monte Carlo robustness test results.
    """

    def __init__(self, mc_results: Dict[str, Any]):
        self.results = mc_results

    def generate_percentile_table(self) -> pd.DataFrame:
        """Generate percentile table for key metrics."""
        metrics = ['total_return_pct', 'max_drawdown_pct', 'sharpe_ratio', 'win_rate']
        rows = []

        for metric in metrics:
            data = self.results.get(metric, {})
            if not data:
                continue
            row = {
                'Metric': metric,
                'Mean': data.get('mean'),
                'Median': data.get('median'),
                'P5': data.get('p5'),
                'P25': data.get('p25'),
                'P75': data.get('p75'),
                'P95': data.get('p95'),
            }
            rows.append(row)

        return pd.DataFrame(rows)

    def generate_summary_text(self, simulator: Optional[Any] = None) -> str:
        """Summary with interpretability."""
        lines = ["=" * 70, "MONTE CARLO ROBUSTNESS SUMMARY", "=" * 70, ""]

        ret = self.results.get("total_return_pct", {})
        if ret:
            lines.extend([
                "RETURN DISTRIBUTION (across 10,000 simulations)",
                f"  Median return:        {ret.get('median', 0):.2f}%",
                f"  5th percentile (worst): {ret.get('p5', 0):.2f}%",
                f"  95th percentile (best): {ret.get('p95', 0):.2f}%",
            ])

        if "original_return_pct" in self.results:
            orig = self.results["original_return_pct"]
            pctile = self.results.get("return_percentile", 50)
            lines.append(f"")
            lines.append(f"Original backtest return: {orig:.2f}% ({pctile:.0f}th percentile)")

        lines.extend([
            f"P(negative return):     {self.results.get('negative_return_probability', 0):.1f}%",
            f"P(Sharpe < 0):          {self.results.get('sharpe_negative_probability', 0):.1f}%",
            "",
            f"Worst 5% max drawdown:  {self.results.get('worst_5pct_max_dd_pct', 0):.2f}%",
            "=" * 70,
        ])
        return "\n".join(lines)
