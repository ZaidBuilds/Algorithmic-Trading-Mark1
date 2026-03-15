"""
Performance metrics calculation for backtesting results.

This module calculates various performance metrics:
- Total return and percentage return
- Win rate and profit factor
- Maximum drawdown
- Sharpe ratio
- Equity curve
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np
from datetime import datetime


@dataclass
class Trade:
    """
    Represents a completed trade.
    
    Attributes:
        entry_date: Date when trade was opened
        exit_date: Date when trade was closed
        entry_price: Price at entry
        exit_price: Price at exit
        quantity: Number of shares/units
        pnl: Profit/Loss (in currency units)
        pnl_percent: Profit/Loss as percentage
        duration: Trade duration in days
    """
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    duration: int
    
    def is_winning(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0
    
    def is_losing(self) -> bool:
        """Check if trade was losing."""
        return self.pnl < 0


class BacktestMetrics:
    """
    Calculate performance metrics from backtest results.
    
    Why these metrics matter:
    -------------------------
    1. **Total Return**: Overall profitability
    2. **Win Rate**: Percentage of profitable trades
    3. **Profit Factor**: Ratio of gross profit to gross loss
    4. **Max Drawdown**: Largest peak-to-trough decline (risk measure)
    5. **Sharpe Ratio**: Risk-adjusted return (higher is better)
    6. **Equity Curve**: Visual representation of account value over time
    """
    
    def __init__(self, initial_balance: float):
        """
        Initialize metrics calculator.
        
        Args:
            initial_balance: Starting account balance
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [initial_balance]
        self.equity_dates: List[datetime] = []
    
    def add_trade(self, trade: Trade):
        """Add a completed trade to the metrics."""
        self.trades.append(trade)
    
    def update_equity(self, date: datetime, balance: float):
        """
        Update equity curve with current balance.
        
        Args:
            date: Current date
            balance: Current account balance
        """
        self.current_balance = balance
        self.equity_curve.append(balance)
        self.equity_dates.append(date)
    
    def calculate_total_return(self) -> Dict[str, float]:
        """
        Calculate total return metrics.
        
        Returns:
            Dictionary with 'absolute' and 'percent' returns
        """
        total_return = self.current_balance - self.initial_balance
        total_return_pct = (total_return / self.initial_balance * 100) if self.initial_balance > 0 else 0.0
        
        return {
            'absolute': total_return,
            'percent': total_return_pct
        }
    
    def calculate_win_rate(self) -> Dict[str, float]:
        """
        Calculate win rate statistics.
        
        Returns:
            Dictionary with 'win_rate', 'winning_trades', 'losing_trades', 'total_trades'
        """
        if len(self.trades) == 0:
            return {
                'win_rate': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_trades': 0
            }
        
        winning_trades = [t for t in self.trades if t.is_winning()]
        losing_trades = [t for t in self.trades if t.is_losing()]
        
        win_rate = (len(winning_trades) / len(self.trades)) * 100
        
        return {
            'win_rate': win_rate,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'total_trades': len(self.trades)
        }
    
    def calculate_profit_factor(self) -> float:
        """
        Calculate profit factor (gross profit / gross loss).
        
        Returns:
            Profit factor (1.0 means break-even, >1.0 is profitable)
        """
        if len(self.trades) == 0:
            return 0.0
        
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def calculate_max_drawdown(self) -> Dict[str, float]:
        """
        Calculate maximum drawdown.
        
        Drawdown: Decline from a peak to a trough
        Max Drawdown: Largest such decline in the equity curve
        
        Returns:
            Dictionary with 'absolute', 'percent', 'peak_date', 'trough_date'
        """
        if len(self.equity_curve) < 2:
            return {
                'absolute': 0.0,
                'percent': 0.0,
                'peak_date': None,
                'trough_date': None
            }
        
        # Convert to numpy for easier calculation
        equity_array = np.array(self.equity_curve)
        
        # Calculate running maximum (peak)
        running_max = np.maximum.accumulate(equity_array)
        
        # Calculate drawdown at each point
        drawdown = running_max - equity_array
        
        # Find maximum drawdown
        max_dd_index = np.argmax(drawdown)
        max_drawdown_absolute = drawdown[max_dd_index]
        
        # Find peak before this drawdown
        peak_index = np.argmax(equity_array[:max_dd_index + 1])
        peak_value = equity_array[peak_index]
        
        max_drawdown_percent = (max_drawdown_absolute / peak_value * 100) if peak_value > 0 else 0.0
        
        peak_date = self.equity_dates[peak_index] if peak_index < len(self.equity_dates) else None
        trough_date = self.equity_dates[max_dd_index] if max_dd_index < len(self.equity_dates) else None
        
        return {
            'absolute': float(max_drawdown_absolute),
            'percent': float(max_drawdown_percent),
            'peak_date': peak_date,
            'trough_date': trough_date
        }
    
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe ratio (annualized).
        
        Sharpe Ratio = (Average Return - Risk Free Rate) / Standard Deviation of Returns
        
        Args:
            risk_free_rate: Annual risk-free rate (default: 2% = 0.02)
        
        Returns:
            Sharpe ratio (higher is better, typically > 1.0 is good)
        """
        if len(self.equity_curve) < 2:
            return 0.0
        
        # Calculate period returns (daily if daily data)
        equity_array = np.array(self.equity_curve)
        returns = np.diff(equity_array) / equity_array[:-1]
        
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        
        # Annualize returns (assuming daily data)
        # Average daily return * 252 trading days = annual return
        avg_return = np.mean(returns) * 252
        std_return = np.std(returns) * np.sqrt(252)
        
        if std_return == 0:
            return 0.0
        
        sharpe = (avg_return - risk_free_rate) / std_return
        return float(sharpe)
    
    def calculate_average_trade(self) -> Dict[str, float]:
        """
        Calculate average trade statistics.
        
        Returns:
            Dictionary with average PnL, average win, average loss, average duration
        """
        if len(self.trades) == 0:
            return {
                'avg_pnl': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'avg_duration': 0.0
            }
        
        avg_pnl = np.mean([t.pnl for t in self.trades])
        
        winning_trades = [t for t in self.trades if t.is_winning()]
        losing_trades = [t for t in self.trades if t.is_losing()]
        
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0.0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0.0
        avg_duration = np.mean([t.duration for t in self.trades])
        
        return {
            'avg_pnl': float(avg_pnl),
            'avg_win': float(avg_win),
            'avg_loss': float(avg_loss),
            'avg_duration': float(avg_duration)
        }
    
    def get_summary(self) -> Dict:
        """
        Get complete metrics summary.
        
        Returns:
            Dictionary with all calculated metrics
        """
        total_return = self.calculate_total_return()
        win_rate = self.calculate_win_rate()
        max_dd = self.calculate_max_drawdown()
        avg_trade = self.calculate_average_trade()
        
        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.current_balance,
            'total_return': total_return,
            'win_rate': win_rate,
            'profit_factor': self.calculate_profit_factor(),
            'max_drawdown': max_dd,
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'average_trade': avg_trade,
            'equity_curve': self.equity_curve,
            'equity_dates': self.equity_dates,
            'trades': self.trades
        }

