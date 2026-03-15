"""
Backtest results reporting and visualization.

This module provides functionality to:
- Format and display backtest results
- Generate text reports
- Export results to CSV
"""

from typing import Optional
import pandas as pd
from pathlib import Path
from datetime import datetime

from .metrics import BacktestMetrics


class BacktestReporter:
    """
    Generate reports from backtest results.
    
    Why Reporting Matters:
    ---------------------
    1. Understand strategy performance at a glance
    2. Compare different strategies
    3. Identify areas for improvement
    4. Document results for analysis
    """
    
    def __init__(self, metrics: BacktestMetrics):
        """
        Initialize reporter with metrics.
        
        Args:
            metrics: BacktestMetrics object with calculated results
        """
        self.metrics = metrics
    
    def generate_summary_text(self) -> str:
        """
        Generate text summary of backtest results.
        
        Returns:
            Formatted string with summary
        """
        summary = self.metrics.get_summary()
        total_return = summary['total_return']
        win_rate = summary['win_rate']
        max_dd = summary['max_drawdown']
        avg_trade = summary['average_trade']
        
        lines = [
            "=" * 70,
            "BACKTEST RESULTS SUMMARY",
            "=" * 70,
            "",
            f"Initial Balance:     ${summary['initial_balance']:,.2f}",
            f"Final Balance:       ${summary['final_balance']:,.2f}",
            f"Total Return:        ${total_return['absolute']:,.2f} ({total_return['percent']:.2f}%)",
            "",
            "TRADE STATISTICS",
            "-" * 70,
            f"Total Trades:        {win_rate['total_trades']}",
            f"Winning Trades:      {win_rate['winning_trades']}",
            f"Losing Trades:       {win_rate['losing_trades']}",
            f"Win Rate:            {win_rate['win_rate']:.2f}%",
            f"Profit Factor:       {summary['profit_factor']:.2f}",
            "",
            "AVERAGE TRADE",
            "-" * 70,
            f"Average P&L:         ${avg_trade['avg_pnl']:,.2f}",
            f"Average Win:         ${avg_trade['avg_win']:,.2f}",
            f"Average Loss:        ${avg_trade['avg_loss']:,.2f}",
            f"Average Duration:    {avg_trade['avg_duration']:.1f} days",
            "",
            "RISK METRICS",
            "-" * 70,
            f"Max Drawdown:        ${max_dd['absolute']:,.2f} ({max_dd['percent']:.2f}%)",
        ]
        
        if max_dd['peak_date']:
            lines.append(f"Peak Date:           {max_dd['peak_date'].strftime('%Y-%m-%d')}")
        if max_dd['trough_date']:
            lines.append(f"Trough Date:         {max_dd['trough_date'].strftime('%Y-%m-%d')}")
        
        lines.extend([
            f"Sharpe Ratio:        {summary['sharpe_ratio']:.2f}",
            "",
            "=" * 70
        ])
        
        return "\n".join(lines)
    
    def print_summary(self):
        """Print summary to console."""
        print(self.generate_summary_text())
    
    def export_trades_to_csv(self, filepath: str):
        """
        Export trade history to CSV file.
        
        Args:
            filepath: Path to output CSV file
        """
        if len(self.metrics.trades) == 0:
            print("No trades to export")
            return
        
        trades_data = []
        for trade in self.metrics.trades:
            trades_data.append({
                'Entry Date': trade.entry_date.strftime('%Y-%m-%d'),
                'Exit Date': trade.exit_date.strftime('%Y-%m-%d'),
                'Entry Price': trade.entry_price,
                'Exit Price': trade.exit_price,
                'Quantity': trade.quantity,
                'PnL': trade.pnl,
                'PnL %': trade.pnl_percent,
                'Duration (days)': trade.duration,
                'Result': 'WIN' if trade.is_winning() else 'LOSS'
            })
        
        df = pd.DataFrame(trades_data)
        df.to_csv(filepath, index=False)
        print(f"Exported {len(self.metrics.trades)} trades to {filepath}")
    
    def export_equity_curve_to_csv(self, filepath: str):
        """
        Export equity curve to CSV file.
        
        Args:
            filepath: Path to output CSV file
        """
        if len(self.metrics.equity_curve) == 0:
            print("No equity curve data to export")
            return
        
        equity_data = {
            'Date': [d.strftime('%Y-%m-%d') for d in self.metrics.equity_dates],
            'Equity': self.metrics.equity_curve[1:]  # Skip initial balance
        }
        
        df = pd.DataFrame(equity_data)
        df.to_csv(filepath, index=False)
        print(f"Exported equity curve ({len(df)} data points) to {filepath}")
    
    def get_trade_list(self) -> pd.DataFrame:
        """
        Get trade list as pandas DataFrame.
        
        Returns:
            DataFrame with trade details
        """
        if len(self.metrics.trades) == 0:
            return pd.DataFrame()
        
        trades_data = []
        for trade in self.metrics.trades:
            trades_data.append({
                'Entry Date': trade.entry_date,
                'Exit Date': trade.exit_date,
                'Entry Price': trade.entry_price,
                'Exit Price': trade.exit_price,
                'Quantity': trade.quantity,
                'PnL': trade.pnl,
                'PnL %': trade.pnl_percent,
                'Duration (days)': trade.duration,
                'Result': 'WIN' if trade.is_winning() else 'LOSS'
            })
        
        return pd.DataFrame(trades_data)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """
        Get equity curve as pandas DataFrame.
        
        Returns:
            DataFrame with date and equity columns
        """
        if len(self.metrics.equity_curve) < 2:
            return pd.DataFrame()
        
        equity_data = {
            'Date': self.metrics.equity_dates,
            'Equity': self.metrics.equity_curve[1:]  # Skip initial balance
        }
        
        return pd.DataFrame(equity_data)

