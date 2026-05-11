"""
Template Strategy - A starting point for creating custom strategies.

This template demonstrates the minimum interface required for a custom strategy
to work with the QuantumTrade plugin system.

To create your own strategy:
1. Copy this file to a new file in the plugins directory
2. Rename the class to match your strategy
3. Implement the required methods:
   - calculate_indicators()
   - generate_signal()
   - get_required_periods()
4. Optionally override get_entry_rules() and get_exit_rules()
"""

import pandas as pd
from typing import Optional
from datetime import datetime

from strategy.base import BaseStrategy
from strategy.signals import Signal, SignalType


class TemplateStrategy(BaseStrategy):
    """
    Template strategy showing the basic structure for custom strategies.
    
    This is a simple example that generates a BUY signal when price crosses
    above a moving average, and SELL when it crosses below.
    """
    
    def __init__(
        self,
        ma_period: int = 20,
        name: str = "Template Strategy",
    ):
        """
        Initialize the template strategy.
        
        Args:
            ma_period: Period for the moving average
            name: Strategy name
        """
        super().__init__(name)
        self.ma_period = ma_period
    
    def get_required_periods(self) -> int:
        """
        Get minimum number of periods needed.
        
        Returns:
            Minimum number of data periods required
        """
        return self.ma_period + 10
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators needed for this strategy.
        
        Args:
            data: DataFrame with OHLCV data (DatetimeIndex)
            
        Returns:
            DataFrame with original data plus indicator columns
        """
        df = data.copy()
        
        # Calculate simple moving average
        df['ma'] = df['Close'].rolling(window=self.ma_period).mean()
        
        return df
    
    def generate_signal(
        self,
        data: pd.DataFrame,
        current_index: int,
    ) -> Signal:
        """
        Generate a trading signal at a specific point in time.
        
        Args:
            data: DataFrame with OHLCV + indicator columns
            current_index: Index position to generate signal for (0-based)
            
        Returns:
            Signal object (BUY, SELL, or HOLD)
        """
        # Get current and previous values
        current_price = data.iloc[current_index]['Close']
        timestamp = data.index[current_index]
        
        current_ma = data.iloc[current_index]['ma']
        
        # Need previous period for crossover detection
        if current_index < 1:
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=timestamp,
                price=float(current_price),
                metadata={'reason': 'Insufficient data'}
            )
        
        prev_price = data.iloc[current_index - 1]['Close']
        prev_ma = data.iloc[current_index - 1]['ma']
        
        # Check for NaN (not enough data for MA)
        if pd.isna(current_ma) or pd.isna(prev_ma):
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=timestamp,
                price=float(current_price),
                metadata={'reason': 'MA not yet calculated'}
            )
        
        # Generate signal based on price vs MA crossover
        if prev_price <= prev_ma and current_price > current_ma:
            signal_type = SignalType.BUY
            metadata = {
                'reason': 'Price crossed above MA',
                'price': current_price,
                'ma': current_ma,
            }
            confidence = 0.7
        elif prev_price >= prev_ma and current_price < current_ma:
            signal_type = SignalType.SELL
            metadata = {
                'reason': 'Price crossed below MA',
                'price': current_price,
                'ma': current_ma,
            }
            confidence = 0.7
        else:
            signal_type = SignalType.HOLD
            metadata = {
                'reason': 'No crossover',
                'price': current_price,
                'ma': current_ma,
            }
            confidence = None
        
        signal = Signal(
            signal_type=signal_type,
            timestamp=timestamp,
            price=float(current_price),
            confidence=confidence,
            metadata=metadata,
        )
        
        self.last_signal = signal
        return signal
    
    def get_entry_rules(self) -> dict:
        """Get entry rules for this strategy."""
        return {
            'description': 'Template Strategy Entry Rules',
            'conditions': [
                f'Price crosses above {self.ma_period}-period moving average',
                'This indicates potential upward momentum'
            ]
        }
    
    def get_exit_rules(self) -> dict:
        """Get exit rules for this strategy."""
        return {
            'description': 'Template Strategy Exit Rules',
            'conditions': [
                f'Price crosses below {self.ma_period}-period moving average',
                'This indicates potential downward momentum'
            ]
        }


# Example: Custom parameters can be added as needed
class CustomStrategy(TemplateStrategy):
    """Extended template with custom parameters."""
    
    def __init__(
        self,
        ma_period: int = 20,
        deviation_threshold: float = 0.02,
        name: str = "Custom Strategy",
    ):
        super().__init__(ma_period=ma_period, name=name)
        self.deviation_threshold = deviation_threshold
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = super().calculate_indicators(data)
        df['ma_std'] = df['Close'].rolling(window=self.ma_period).std()
        df['upper_band'] = df['ma'] + (df['ma_std'] * 2)
        df['lower_band'] = df['ma'] - (df['ma_std'] * 2)
        return df