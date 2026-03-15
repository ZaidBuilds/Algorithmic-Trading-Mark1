"""
Bollinger Bands Strategy.
"""

import pandas as pd
from .base import BaseStrategy
from .signals import Signal, SignalType


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands Strategy.
    BUY when price hits lower band, SELL when price hits upper band.
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0, name: str = "Bollinger"):
        super().__init__(name)
        self.period = period
        self.std_dev = std_dev
    
    def get_required_periods(self) -> int:
        return self.period + 5
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df['bb_mid'] = df['Close'].rolling(window=self.period).mean()
        df['bb_std'] = df['Close'].rolling(window=self.period).std()
        df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * self.std_dev)
        df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * self.std_dev)
        return df
    
    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        curr = data.iloc[current_index]
        
        if pd.isna(curr['bb_upper']) or pd.isna(curr['bb_lower']):
            return Signal(SignalType.HOLD, data.index[current_index], curr['Close'])
            
        if curr['Close'] <= curr['bb_lower']:
            return Signal(SignalType.BUY, data.index[current_index], curr['Close'], metadata={'status': 'Lower Band Hit'})
        elif curr['Close'] >= curr['bb_upper']:
            return Signal(SignalType.SELL, data.index[current_index], curr['Close'], metadata={'status': 'Upper Band Hit'})
            
        return Signal(SignalType.HOLD, data.index[current_index], curr['Close'])
