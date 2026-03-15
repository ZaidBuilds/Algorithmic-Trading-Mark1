"""
EMA (Exponential Moving Average) Crossover Strategy.

Strategy Logic:
---------------
1. Calculate two EMAs: Fast EMA (shorter period) and Slow EMA (longer period)
2. BUY signal: When Fast EMA crosses above Slow EMA (bullish crossover)
3. SELL signal: When Fast EMA crosses below Slow EMA (bearish crossover)
4. HOLD: When no crossover occurs

Why EMA over SMA?
-----------------
- EMA gives more weight to recent prices, reacting faster to price changes
- Better for trend-following strategies
- Reduces lag compared to Simple Moving Average (SMA)

Entry Rules:
-----------
- Enter long position when Fast EMA > Slow EMA AND previous period had Fast EMA <= Slow EMA
- This is a "golden cross" pattern indicating upward momentum

Exit Rules:
----------
- Exit long position when Fast EMA < Slow EMA AND previous period had Fast EMA >= Slow EMA
- This is a "death cross" pattern indicating downward momentum
"""

import pandas as pd
import numpy as np
from typing import Optional
from datetime import datetime

from .base import BaseStrategy
from .signals import Signal, SignalType


class EMACrossoverStrategy(BaseStrategy):
    """
    Exponential Moving Average Crossover Strategy.
    
    This strategy generates BUY signals when the fast EMA crosses above
    the slow EMA, and SELL signals when the fast EMA crosses below the slow EMA.
    """
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        name: str = "EMA Crossover"
    ):
        """
        Initialize EMA Crossover Strategy.
        
        Args:
            fast_period: Period for fast EMA (default: 12, typical for daily charts)
            slow_period: Period for slow EMA (default: 26, typical for daily charts)
            name: Strategy name
            
        Common Periods:
        ---------------
        - Daily charts: fast=12, slow=26 (MACD standard)
        - Hourly charts: fast=9, slow=21
        - 15-min charts: fast=9, slow=21
        
        The slow period must be greater than fast period.
        """
        if slow_period <= fast_period:
            raise ValueError(
                f"Slow period ({slow_period}) must be greater than "
                f"fast period ({fast_period})"
            )
        
        super().__init__(name)
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def get_required_periods(self) -> int:
        """
        Return minimum number of periods needed.
        
        We need at least slow_period periods to calculate the slow EMA,
        plus a few extra for stability.
        """
        return self.slow_period + 5
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Fast EMA and Slow EMA indicators.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added 'ema_fast' and 'ema_slow' columns
            
        EMA Calculation:
        ---------------
        EMA(today) = (Price(today) * multiplier) + (EMA(yesterday) * (1 - multiplier))
        multiplier = 2 / (period + 1)
        
        pandas.ewm() handles this calculation efficiently.
        """
        df = data.copy()
        
        # Calculate EMAs using pandas exponential weighted mean
        # adjust=False uses the standard EMA formula (no bias adjustment)
        df['ema_fast'] = df['Close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_slow'] = df['Close'].ewm(span=self.slow_period, adjust=False).mean()
        
        return df
    
    def generate_signal(
        self,
        data: pd.DataFrame,
        current_index: int
    ) -> Signal:
        """
        Generate trading signal at current_index.
        
        Args:
            data: DataFrame with OHLCV + indicator columns (must have 'ema_fast' and 'ema_slow')
            current_index: Current position in data (0-based)
        
        Returns:
            Signal object (BUY, SELL, or HOLD)
        
        Signal Generation Logic:
        -----------------------
        1. Get current and previous EMA values
        2. Check for crossover:
           - Bullish: Fast EMA was below Slow EMA, now above → BUY
           - Bearish: Fast EMA was above Slow EMA, now below → SELL
        3. No crossover → HOLD
        
        No Look-Ahead Bias:
        -------------------
        - Only uses data up to current_index
        - Checks previous period (current_index - 1) to detect crossovers
        - Never looks at future data
        """
        # Validate we have enough data
        if current_index < 1:
            # Need at least 2 periods to detect crossover
            current_price = data.iloc[current_index]['Close']
            timestamp = data.index[current_index]
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=timestamp,
                price=current_price,
                metadata={'reason': 'Insufficient data for crossover detection'}
            )
        
        # Get current and previous EMA values
        current_row = data.iloc[current_index]
        previous_row = data.iloc[current_index - 1]
        
        current_fast = current_row['ema_fast']
        current_slow = current_row['ema_slow']
        prev_fast = previous_row['ema_fast']
        prev_slow = previous_row['ema_slow']
        
        # Check for NaN values (shouldn't happen if indicators calculated correctly)
        if pd.isna(current_fast) or pd.isna(current_slow) or \
           pd.isna(prev_fast) or pd.isna(prev_slow):
            current_price = current_row['Close']
            timestamp = data.index[current_index]
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=timestamp,
                price=current_price,
                metadata={'reason': 'NaN values in indicators'}
            )
        
        current_price = current_row['Close']
        timestamp = data.index[current_index]
        
        # Detect crossover
        # Bullish crossover: Fast EMA crosses above Slow EMA
        if prev_fast <= prev_slow and current_fast > current_slow:
            signal_type = SignalType.BUY
            metadata = {
                'reason': 'Bullish crossover',
                'prev_fast': float(prev_fast),
                'prev_slow': float(prev_slow),
                'current_fast': float(current_fast),
                'current_slow': float(current_slow)
            }
            # Calculate confidence based on EMA separation
            separation = (current_fast - current_slow) / current_slow
            confidence = min(1.0, max(0.5, abs(separation) * 100))
        
        # Bearish crossover: Fast EMA crosses below Slow EMA
        elif prev_fast >= prev_slow and current_fast < current_slow:
            signal_type = SignalType.SELL
            metadata = {
                'reason': 'Bearish crossover',
                'prev_fast': float(prev_fast),
                'prev_slow': float(prev_slow),
                'current_fast': float(current_fast),
                'current_slow': float(current_slow)
            }
            # Calculate confidence based on EMA separation
            separation = (current_slow - current_fast) / current_slow
            confidence = min(1.0, max(0.5, abs(separation) * 100))
        
        # No crossover - HOLD
        else:
            signal_type = SignalType.HOLD
            metadata = {
                'reason': 'No crossover',
                'fast_above_slow': current_fast > current_slow
            }
            confidence = None
        
        signal = Signal(
            signal_type=signal_type,
            timestamp=timestamp,
            price=float(current_price),
            confidence=confidence,
            metadata=metadata
        )
        
        self.last_signal = signal
        return signal
    
    def get_entry_rules(self) -> dict:
        """Get entry rules for EMA crossover strategy."""
        return {
            'description': 'EMA Crossover Entry Rules',
            'conditions': [
                f'Fast EMA ({self.fast_period}) crosses above Slow EMA ({self.slow_period})',
                'This is a bullish "golden cross" signal',
                'Enter long position on crossover confirmation'
            ]
        }
    
    def get_exit_rules(self) -> dict:
        """Get exit rules for EMA crossover strategy."""
        return {
            'description': 'EMA Crossover Exit Rules',
            'conditions': [
                f'Fast EMA ({self.fast_period}) crosses below Slow EMA ({self.slow_period})',
                'This is a bearish "death cross" signal',
                'Exit long position on crossover confirmation'
            ]
        }

