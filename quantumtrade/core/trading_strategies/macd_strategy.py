"""
Moving Average Convergence Divergence (MACD) Strategy.
"""

import pandas as pd
from .base import BaseStrategy
from .signals import Signal, SignalType


class MACDStrategy(BaseStrategy):
    """
    MACD Strategy.
    Generates signals based on MACD line and Signal line crossovers.
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        name: str = "MACD"
    ):
        super().__init__(name)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
    
    def get_required_periods(self) -> int:
        return self.slow_period + self.signal_period + 5
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        ema_fast = df['Close'].ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = df['Close'].ewm(span=self.slow_period, adjust=False).mean()
        
        df['macd_line'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd_line'].ewm(span=self.signal_period, adjust=False).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal']
        
        return df
    
    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        if current_index < 1:
            return Signal(SignalType.HOLD, data.index[current_index], data.iloc[current_index]['Close'])
            
        curr = data.iloc[current_index]
        prev = data.iloc[current_index - 1]
        
        if pd.isna(curr['macd_line']) or pd.isna(curr['macd_signal']):
            return Signal(SignalType.HOLD, data.index[current_index], curr['Close'])
            
        # Bullish: MACD line crosses above Signal line
        if prev['macd_line'] <= prev['macd_signal'] and curr['macd_line'] > curr['macd_signal']:
            return Signal(SignalType.BUY, data.index[current_index], curr['Close'], metadata={'reason': 'MACD Crossover'})
        # Bearish: MACD line crosses below Signal line
        elif prev['macd_line'] >= prev['macd_signal'] and curr['macd_line'] < curr['macd_signal']:
            return Signal(SignalType.SELL, data.index[current_index], curr['Close'], metadata={'reason': 'MACD Death Cross'})
            
        return Signal(SignalType.HOLD, data.index[current_index], curr['Close'])
