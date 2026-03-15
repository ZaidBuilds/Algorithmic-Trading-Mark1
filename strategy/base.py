"""
Abstract base class for all trading strategies.

This module defines the interface that all strategies must implement.
The base class ensures consistency across different strategy implementations.
"""

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd
from datetime import datetime

from .signals import Signal, SignalType


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Why an abstract base class?
    ----------------------------
    1. **Consistency**: Ensures all strategies follow the same interface
    2. **Type Safety**: Makes it clear what methods strategies must implement
    3. **Testing**: Easier to mock and test strategies
    4. **Extensibility**: Adding new strategies is straightforward
    5. **Documentation**: Clear contract for what a strategy should do
    
    Strategy Responsibilities:
    --------------------------
    - Calculate technical indicators
    - Generate trading signals based on data (NO look-ahead bias)
    - Specify minimum data requirements
    """
    
    def __init__(self, name: str):
        """
        Initialize the strategy.
        
        Args:
            name: Human-readable name for this strategy
        """
        self.name = name
        self.last_signal: Optional[Signal] = None
    
    @abstractmethod
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators needed for this strategy.
        
        Args:
            data: DataFrame with OHLCV data (DatetimeIndex)
            
        Returns:
            DataFrame with original data plus indicator columns
            
        Note:
            This method should add indicator columns to the DataFrame.
            Example: data['ema_fast'], data['ema_slow']
        """
        pass
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        """
        Generate a trading signal at a specific point in time.
        
        Args:
            data: DataFrame with OHLCV + indicator columns
            current_index: Index position to generate signal for (0-based)
                          Only data up to and including this index should be used
        
        Returns:
            Signal object with signal type, price, and timestamp
            
        CRITICAL: No Look-Ahead Bias
        -----------------------------
        - Only use data from indices 0 to current_index (inclusive)
        - Do NOT access data[current_index + 1:] or any future data
        - This ensures backtesting reflects real-world trading conditions
        
        Example:
            # CORRECT - uses only past and current data
            current_price = data.loc[data.index[current_index], 'Close']
            prev_ema = data.loc[data.index[current_index - 1], 'ema_fast']
            
            # WRONG - look-ahead bias!
            future_price = data.loc[data.index[current_index + 1], 'Close']
        """
        pass
    
    @abstractmethod
    def get_required_periods(self) -> int:
        """
        Get minimum number of data periods required for this strategy.
        
        Returns:
            Minimum number of periods (rows) needed before strategy can generate signals
            
        Example:
            EMA crossover with 50-day EMA needs at least 50 periods.
        """
        pass
    
    def get_entry_rules(self) -> dict:
        """
        Get entry rules for this strategy.
        
        Returns:
            Dictionary describing entry conditions
            
        Note:
            Override in subclasses to provide strategy-specific entry rules.
            This is informational and doesn't affect signal generation.
        """
        return {
            'description': 'Generic entry rules',
            'conditions': []
        }
    
    def get_exit_rules(self) -> dict:
        """
        Get exit rules for this strategy.
        
        Returns:
            Dictionary describing exit conditions
            
        Note:
            Override in subclasses to provide strategy-specific exit rules.
            This is informational and doesn't affect signal generation.
        """
        return {
            'description': 'Generic exit rules',
            'conditions': []
        }
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate that input data meets requirements.
        
        Args:
            data: DataFrame to validate
            
        Returns:
            True if data is valid, False otherwise
        """
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing = [col for col in required_columns if col not in data.columns]
        
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        if len(data) < self.get_required_periods():
            raise ValueError(
                f"Insufficient data: need {self.get_required_periods()} periods, "
                f"got {len(data)}"
            )
        
        return True
    
    def __str__(self) -> str:
        """String representation of strategy."""
        return f"{self.__class__.__name__}(name='{self.name}')"
    
    def __repr__(self) -> str:
        """Representation of strategy."""
        return self.__str__()

