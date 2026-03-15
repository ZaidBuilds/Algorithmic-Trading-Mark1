"""
Simple Moving Average (SMA) Crossover Strategy.
"""

import pandas as pd
from typing import Optional
from .base import BaseStrategy
from .signals import Signal, SignalType


class SMAStrategy(BaseStrategy):
    """
    Simple Moving Average Crossover Strategy.
    """
    
    def __init__(
        self,
        short_period: int = 20,
        long_period: int = 50,
        name: str = "SMA Crossover"
    ):
        if long_period <= short_period:
            raise ValueError(f"Long period ({long_period}) must be greater than short period ({short_period})")
        
        super().__init__(name)
        self.short_period = short_period
        self.long_period = long_period
    
    def get_required_periods(self) -> int:
        return self.long_period + 5
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df['sma_short'] = df['Close'].rolling(window=self.short_period).mean()
        df['sma_long'] = df['Close'].rolling(window=self.long_period).mean()
        return df
    
    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        if current_index < 1:
            return Signal(SignalType.HOLD, data.index[current_index], data.iloc[current_index]['Close'])
        
        current_row = data.iloc[current_index]
        prev_row = data.iloc[current_index - 1]
        
        curr_short = current_row['sma_short']
        curr_long = current_row['sma_long']
        prev_short = prev_row['sma_short']
        prev_long = prev_row['sma_long']
        
        if pd.isna(curr_short) or pd.isna(curr_long) or pd.isna(prev_short) or pd.isna(prev_long):
            return Signal(SignalType.HOLD, data.index[current_index], current_row['Close'], metadata={'reason': 'Indicators still calculating'})
            
        if prev_short <= prev_long and curr_short > curr_long:
            return Signal(SignalType.BUY, data.index[current_index], current_row['Close'], metadata={'reason': 'SMA Bullish Crossover'})
        elif prev_short >= prev_long and curr_short < curr_long:
            return Signal(SignalType.SELL, data.index[current_index], current_row['Close'], metadata={'reason': 'SMA Bearish Crossover'})
            
        return Signal(SignalType.HOLD, data.index[current_index], current_row['Close'])
