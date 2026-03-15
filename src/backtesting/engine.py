"""
Main backtesting engine for simulating trades on historical data.

This module implements the core backtesting logic:
- Iterate over historical data chronologically
- Generate signals from strategy
- Simulate trade execution
- Track positions and account balance
- Calculate equity curve
"""

from typing import Optional, List
from datetime import datetime
import pandas as pd
import logging

from strategy.base import BaseStrategy
from strategy.signals import SignalType
from .metrics import BacktestMetrics, Trade

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Backtesting engine for testing strategies on historical data.
    
    How Backtesting Works:
    ----------------------
    1. Load historical OHLCV data
    2. Calculate indicators for the entire dataset
    3. Iterate chronologically through the data
    4. At each point, generate a signal using only past data
    5. Execute trades based on signals
    6. Track positions, balance, and equity
    7. Calculate performance metrics
    
    Trade Lifecycle:
    ----------------
    1. Signal Generation → Strategy generates BUY/SELL signal
    2. Position Entry → Open position at current price
    3. Position Management → Track open position
    4. Position Exit → Close position on exit signal
    5. Trade Record → Record completed trade with P&L
    
    Important: No Look-Ahead Bias
    ------------------------------
    - Only use data up to current_index
    - Never use future prices or indicators
    - Signals must be generated based on past data only
    """
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        commission: float = 0.001  # 0.1% commission
    ):
        """
        Initialize backtest engine.
        
        Args:
            initial_balance: Starting account balance
            commission: Commission per trade (as decimal, e.g., 0.001 = 0.1%)
        """
        self.initial_balance = initial_balance
        self.commission = commission
        self.metrics = BacktestMetrics(initial_balance)
        self.logger = logger
    
    def run(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame
    ) -> BacktestMetrics:
        """
        Run backtest on historical data.
        
        Args:
            strategy: Trading strategy to test
            data: DataFrame with OHLCV data (DatetimeIndex required)
        
        Returns:
            BacktestMetrics object with all calculated metrics
        
        Process:
        -------
        1. Validate data and strategy requirements
        2. Calculate indicators for entire dataset
        3. Initialize position tracking variables
        4. Iterate through data chronologically
        5. Generate signals and execute trades
        6. Update equity curve
        7. Return metrics
        """
        self.logger.info(f"Starting backtest with {strategy.name}")
        self.logger.info(f"Initial balance: ${self.initial_balance:,.2f}")
        self.logger.info(f"Data period: {data.index[0]} to {data.index[-1]} ({len(data)} periods)")
        
        # Validate data
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data must have DatetimeIndex")
        
        # Validate strategy can work with this data
        strategy.validate_data(data)
        
        # Calculate indicators
        self.logger.info("Calculating indicators...")
        data_with_indicators = strategy.calculate_indicators(data.copy())
        
        # Initialize position tracking
        position = None  # {'entry_price': float, 'entry_date': datetime, 'quantity': float}
        balance = self.initial_balance
        required_periods = strategy.get_required_periods()
        
        # Initialize equity curve
        self.metrics.update_equity(data.index[0], balance)
        
        # Iterate through data
        self.logger.info("Running backtest simulation...")
        
        for i in range(required_periods, len(data_with_indicators)):
            current_date = data_with_indicators.index[i]
            current_row = data_with_indicators.iloc[i]
            current_price = current_row['Close']
            
            # Generate signal (using only data up to current_index)
            signal = strategy.generate_signal(data_with_indicators, i)
            
            # Handle position exit first (if we have a position)
            if position is not None:
                # Check for exit signal
                if signal.signal_type == SignalType.SELL:
                    # Close position
                    exit_price = current_price
                    quantity = position['quantity']
                    
                    # Calculate trade P&L
                    entry_price = position['entry_price']
                    gross_pnl = (exit_price - entry_price) * quantity
                    commission_cost = (entry_price * quantity + exit_price * quantity) * self.commission
                    net_pnl = gross_pnl - commission_cost
                    pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                    
                    # Update balance
                    balance = balance + (exit_price * quantity) - commission_cost
                    
                    # Calculate trade duration
                    duration = (current_date - position['entry_date']).days
                    
                    # Record trade
                    trade = Trade(
                        entry_date=position['entry_date'],
                        exit_date=current_date,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=quantity,
                        pnl=net_pnl,
                        pnl_percent=pnl_percent,
                        duration=duration
                    )
                    self.metrics.add_trade(trade)
                    
                    self.logger.debug(
                        f"Exit trade: {quantity:.2f} shares @ ${exit_price:.2f}, "
                        f"P&L: ${net_pnl:.2f} ({pnl_percent:.2f}%)"
                    )
                    
                    # Clear position
                    position = None
            
            # Handle position entry (if we don't have a position)
            if position is None and signal.signal_type == SignalType.BUY:
                # Calculate position size (use all available cash)
                # In real trading, this would use risk management
                commission_cost_estimate = current_price * self.commission
                available_cash = balance - commission_cost_estimate
                quantity = available_cash / current_price
                
                if quantity > 0:
                    # Open position
                    entry_commission = current_price * quantity * self.commission
                    balance = balance - (current_price * quantity) - entry_commission
                    
                    position = {
                        'entry_price': current_price,
                        'entry_date': current_date,
                        'quantity': quantity
                    }
                    
                    self.logger.debug(
                        f"Enter trade: {quantity:.2f} shares @ ${current_price:.2f}, "
                        f"Balance: ${balance:.2f}"
                    )
            
            # Update equity curve (use current position value if position open)
            if position is not None:
                # Unrealized P&L
                position_value = current_price * position['quantity']
                equity = balance + position_value
            else:
                equity = balance
            
            self.metrics.update_equity(current_date, equity)
        
        # Close any open position at the end
        if position is not None:
            final_row = data_with_indicators.iloc[-1]
            final_price = final_row['Close']
            final_date = data_with_indicators.index[-1]
            
            quantity = position['quantity']
            entry_price = position['entry_price']
            
            gross_pnl = (final_price - entry_price) * quantity
            commission_cost = (entry_price * quantity + final_price * quantity) * self.commission
            net_pnl = gross_pnl - commission_cost
            pnl_percent = ((final_price - entry_price) / entry_price) * 100
            
            balance = balance + (final_price * quantity) - commission_cost
            duration = (final_date - position['entry_date']).days
            
            trade = Trade(
                entry_date=position['entry_date'],
                exit_date=final_date,
                entry_price=entry_price,
                exit_price=final_price,
                quantity=quantity,
                pnl=net_pnl,
                pnl_percent=pnl_percent,
                duration=duration
            )
            self.metrics.add_trade(trade)
            
            self.metrics.update_equity(final_date, balance)
        
        # Set final balance
        self.metrics.current_balance = balance
        
        self.logger.info(f"Backtest complete: {len(self.metrics.trades)} trades executed")
        
        return self.metrics

