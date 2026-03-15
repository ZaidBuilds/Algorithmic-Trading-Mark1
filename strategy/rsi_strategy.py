"""
Relative Strength Index (RSI) Strategy.
"""

import pandas as pd
from typing import Optional
from .base import BaseStrategy
from .signals import Signal, SignalType


class RSIStrategy(BaseStrategy):
    """
    RSI Strategy.
    Generates BUY when RSI crosses below oversold and SELL when it crosses above overbought.
    """
    
    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        name: str = "RSI"
    ):
        super().__init__(name)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
    
    def get_required_periods(self) -> int:
        return self.period + 5
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        curr_row = data.iloc[current_index]
        rsi = curr_row['rsi']
        
        if pd.isna(rsi):
            return Signal(SignalType.HOLD, data.index[current_index], curr_row['Close'])
            
        if rsi < self.oversold:
            return Signal(SignalType.BUY, data.index[current_index], curr_row['Close'], metadata={'rsi': rsi, 'status': 'Oversold'})
        elif rsi > self.overbought:
            return Signal(SignalType.SELL, data.index[current_index], curr_row['Close'], metadata={'rsi': rsi, 'status': 'Overbought'})
            
        return Signal(SignalType.HOLD, data.index[current_index], curr_row['Close'])
