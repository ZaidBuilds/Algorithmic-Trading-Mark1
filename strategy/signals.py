"""
Signal generation utilities for trading strategies.

This module defines:
- Signal data structure
- Signal types (BUY, SELL, HOLD)
- Signal validation and utilities
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class SignalType(Enum):
    """Trading signal types."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    """
    Trading signal data structure.
    
    Attributes:
        signal_type: Type of signal (BUY, SELL, or HOLD)
        timestamp: When the signal was generated
        price: Price at which signal was generated
        confidence: Optional confidence level (0.0 to 1.0)
        metadata: Optional dictionary with additional signal information
    """
    signal_type: SignalType
    timestamp: datetime
    price: float
    confidence: Optional[float] = None
    metadata: Optional[dict] = None
    
    def __post_init__(self):
        """Validate signal after initialization."""
        if self.confidence is not None:
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
    
    def is_buy(self) -> bool:
        """Check if signal is a BUY signal."""
        return self.signal_type == SignalType.BUY
    
    def is_sell(self) -> bool:
        """Check if signal is a SELL signal."""
        return self.signal_type == SignalType.SELL
    
    def is_hold(self) -> bool:
        """Check if signal is a HOLD signal."""
        return self.signal_type == SignalType.HOLD
    
    def __str__(self) -> str:
        """String representation of signal."""
        conf_str = f" (confidence: {self.confidence:.2f})" if self.confidence else ""
        return f"{self.signal_type.value} @ ${self.price:.2f}{conf_str}"


def signal_to_string(signal_type: SignalType) -> str:
    """Convert SignalType enum to lowercase string for compatibility."""
    return signal_type.value.lower()

