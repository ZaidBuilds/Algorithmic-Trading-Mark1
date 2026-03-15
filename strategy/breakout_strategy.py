"""
Breakout Strategy — Support & Resistance Levels.

Strategy Logic:
  - Identify support (recent low) and resistance (recent high) levels
  - BUY when price breaks above resistance with volume confirmation
  - SELL when price breaks below support
  - Uses ATR (Average True Range) to filter noise and set targets

Best Used:
  - Trending markets with consolidation phases
  - Stocks approaching key price levels
  - Works on all timeframes (daily, hourly)
"""

import pandas as pd
import numpy as np
from datetime import datetime

from .base import BaseStrategy
from .signals import Signal, SignalType


class BreakoutStrategy(BaseStrategy):
    """Support/resistance breakout strategy with ATR confirmation."""

    def __init__(
        self,
        lookback: int = 20,
        atr_period: int = 14,
        atr_multiplier: float = 0.5,
        volume_surge: float = 1.5,
        name: str = "Breakout",
    ):
        """
        Args:
            lookback: Periods to look back for support/resistance
            atr_period: ATR calculation period
            atr_multiplier: ATR fraction price must exceed for valid breakout
            volume_surge: Volume must exceed this × average for confirmation
        """
        super().__init__(name)
        self.lookback = lookback
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.volume_surge = volume_surge

    def get_required_periods(self) -> int:
        return max(self.lookback, self.atr_period) + 5

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # Support & Resistance
        df["resistance"] = df["High"].rolling(self.lookback).max()
        df["support"] = df["Low"].rolling(self.lookback).min()

        # ATR (Average True Range)
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift(1)).abs()
        low_close = (df["Low"] - df["Close"].shift(1)).abs()
        df["true_range"] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = df["true_range"].rolling(self.atr_period).mean()

        # Volume average
        df["avg_volume"] = df["Volume"].rolling(self.lookback).mean()
        df["vol_ratio"] = df["Volume"] / df["avg_volume"]

        return df

    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        if current_index < self.get_required_periods():
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=data.index[current_index],
                price=float(data.iloc[current_index]["Close"]),
            )

        curr = data.iloc[current_index]
        prev = data.iloc[current_index - 1]
        price = float(curr["Close"])
        timestamp = data.index[current_index]

        resistance = curr.get("resistance")
        support = curr.get("support")
        atr = curr.get("atr", 0)
        vol_ratio = curr.get("vol_ratio", 1.0)

        if pd.isna(resistance) or pd.isna(support) or pd.isna(atr):
            return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)

        atr_filter = atr * self.atr_multiplier
        vol_confirmed = vol_ratio >= self.volume_surge if not pd.isna(vol_ratio) else False

        # Bullish breakout: close above resistance with ATR margin
        if price > resistance + atr_filter and prev["Close"] <= resistance:
            conf = 0.6 + (0.2 if vol_confirmed else 0)
            return Signal(
                signal_type=SignalType.BUY,
                timestamp=timestamp,
                price=price,
                confidence=min(1.0, conf),
                metadata={
                    "reason": "Resistance breakout",
                    "resistance": float(resistance),
                    "atr": float(atr),
                    "volume_confirmed": vol_confirmed,
                },
            )

        # Bearish breakdown: close below support with ATR margin
        elif price < support - atr_filter and prev["Close"] >= support:
            conf = 0.6 + (0.2 if vol_confirmed else 0)
            return Signal(
                signal_type=SignalType.SELL,
                timestamp=timestamp,
                price=price,
                confidence=min(1.0, conf),
                metadata={
                    "reason": "Support breakdown",
                    "support": float(support),
                    "atr": float(atr),
                    "volume_confirmed": vol_confirmed,
                },
            )

        return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)
