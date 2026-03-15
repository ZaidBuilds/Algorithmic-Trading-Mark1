"""
Reporting module for trade logs and performance summaries.

This module provides:
- Trade log export to CSV
- Daily performance reports
- Console summaries
"""

from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, date
import csv
import logging

logger = logging.getLogger(__name__)


class TradeReporter:
    """
    Generate reports from trading activity.
    
    Features:
    - Trade log export to CSV
    - Daily performance summaries
    - Console reporting
    """
    
    def __init__(self, output_dir: str = "reports"):
        """
        Initialize reporter.
        
        Args:
            output_dir: Directory for report files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger
    
    def export_trades_to_csv(
        self,
        trades: List[Dict],
        filename: Optional[str] = None
    ) -> str:
        """
        Export trade list to CSV file.
        
        Args:
            trades: List of trade dictionaries
            filename: Output filename (defaults to trades_YYYYMMDD.csv)
        
        Returns:
            Path to created CSV file
        """
        if not trades:
            self.logger.warning("No trades to export")
            return ""
        
        if filename is None:
            filename = f"trades_{datetime.now().strftime('%Y%m%d')}.csv"
        
        filepath = self.output_dir / filename
        
        # Define CSV columns
        fieldnames = [
            'Entry Date',
            'Exit Date',
            'Symbol',
            'Side',
            'Quantity',
            'Entry Price',
            'Exit Price',
            'PnL',
            'PnL %',
            'Commission',
            'Duration (days)'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for trade in trades:
                    writer.writerow({
                        'Entry Date': trade.get('entry_date', ''),
                        'Exit Date': trade.get('exit_date', ''),
                        'Symbol': trade.get('symbol', ''),
                        'Side': trade.get('side', ''),
                        'Quantity': trade.get('quantity', 0),
                        'Entry Price': trade.get('entry_price', 0),
                        'Exit Price': trade.get('exit_price', 0),
                        'PnL': trade.get('pnl', 0),
                        'PnL %': trade.get('pnl_pct', 0),
                        'Commission': trade.get('commission', 0),
                        'Duration (days)': trade.get('duration_days', 0)
                    })
            
            self.logger.info(f"Exported {len(trades)} trades to {filepath}")
            return str(filepath)
        
        except Exception as e:
            self.logger.error(f"Error exporting trades to CSV: {e}")
            return ""
    
    def generate_daily_summary(
        self,
        date: date,
        summary: Dict,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate daily performance summary.
        
        Args:
            date: Trading date
            summary: Summary dictionary with performance metrics
            filename: Output filename (defaults to daily_summary_YYYYMMDD.txt)
        
        Returns:
            Path to created summary file
        """
        if filename is None:
            filename = f"daily_summary_{date.strftime('%Y%m%d')}.txt"
        
        filepath = self.output_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write(f"DAILY PERFORMANCE SUMMARY - {date.strftime('%Y-%m-%d')}\n")
                f.write("=" * 70 + "\n\n")
                
                f.write("ACCOUNT SUMMARY\n")
                f.write("-" * 70 + "\n")
                f.write(f"Initial Balance:     ${summary.get('initial_balance', 0):,.2f}\n")
                f.write(f"Current Balance:     ${summary.get('current_balance', 0):,.2f}\n")
                f.write(f"Total Equity:        ${summary.get('total_equity', 0):,.2f}\n")
                f.write(f"Daily P&L:           ${summary.get('daily_pnl', 0):,.2f}\n")
                f.write(f"Total P&L:           ${summary.get('total_pnl', 0):,.2f} "
                       f"({summary.get('total_pnl_pct', 0):.2f}%)\n\n")
                
                f.write("TRADE STATISTICS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Total Trades:        {summary.get('num_trades', 0)}\n")
                f.write(f"Winning Trades:      {summary.get('winning_trades', 0)}\n")
                f.write(f"Losing Trades:       {summary.get('losing_trades', 0)}\n")
                f.write(f"Win Rate:            {summary.get('win_rate', 0):.2f}%\n")
                f.write(f"Profit Factor:       {summary.get('profit_factor', 0):.2f}\n\n")
                
                f.write("POSITIONS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Open Positions:      {summary.get('num_positions', 0)}\n")
                
                positions = summary.get('positions', {})
                if positions:
                    for symbol, pos in positions.items():
                        f.write(f"\n  {symbol}:\n")
                        f.write(f"    Quantity:        {pos.get('quantity', 0):.2f}\n")
                        f.write(f"    Entry Price:     ${pos.get('entry_price', 0):.2f}\n")
                        f.write(f"    Current Price:   ${pos.get('current_price', 0):.2f}\n")
                        f.write(f"    Unrealized P&L:  ${pos.get('unrealized_pnl', 0):.2f} "
                               f"({pos.get('unrealized_pnl_pct', 0):.2f}%)\n")
                
                f.write("\n" + "=" * 70 + "\n")
            
            self.logger.info(f"Generated daily summary: {filepath}")
            return str(filepath)
        
        except Exception as e:
            self.logger.error(f"Error generating daily summary: {e}")
            return ""
    
    def print_console_summary(self, summary: Dict):
        """
        Print summary to console.
        
        Args:
            summary: Summary dictionary
        """
        print("\n" + "=" * 70)
        print("TRADING SUMMARY")
        print("=" * 70)
        
        print(f"\nAccount Balance:     ${summary.get('current_balance', 0):,.2f}")
        print(f"Total Equity:        ${summary.get('total_equity', 0):,.2f}")
        print(f"Total P&L:           ${summary.get('total_pnl', 0):,.2f} "
              f"({summary.get('total_pnl_pct', 0):.2f}%)")
        
        print(f"\nTrades:              {summary.get('num_trades', 0)}")
        print(f"Win Rate:            {summary.get('win_rate', 0):.2f}%")
        print(f"Profit Factor:       {summary.get('profit_factor', 0):.2f}")
        
        print(f"\nOpen Positions:      {summary.get('num_positions', 0)}")
        print("=" * 70 + "\n")

