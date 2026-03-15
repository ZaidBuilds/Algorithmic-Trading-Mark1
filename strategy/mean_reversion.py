"""
Mean Reversion Strategy — Z-Score Based.

Strategy Logic:
  - Calculate a rolling Z-Score of price relative to its moving average
  - BUY when Z-Score drops below -threshold (oversold → expect bounce)
  - SELL when Z-Score rises above +threshold (overbought → expect pullback)
  - Uses both price and RSI Z-scores for dual confirmation

Best Used:
  - Range-bound / sideways markets
  - Large-cap stocks with strong mean-reversion tendencies
  - Daily or hourly timeframes
"""

import pandas as pd
import numpy as np
from datetime import datetime

from .base import BaseStrategy
from .signals import Signal, SignalType


class MeanReversionStrategy(BaseStrategy):
    """Z-Score mean reversion with dual price + RSI confirmation."""

    def __init__(
        self,
        lookback: int = 20,
        z_entry: float = 2.0,
        z_exit: float = 0.5,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        name: str = "Mean Reversion",
    ):
        """
        Args:
            lookback: Rolling window for mean and std
            z_entry: Z-Score threshold to enter trade (e.g. 2.0)
            z_exit: Z-Score threshold to exit (e.g. 0.5)
            rsi_period: RSI calculation period
            rsi_oversold: RSI threshold for oversold confirmation
            rsi_overbought: RSI threshold for overbought confirmation
        """
        super().__init__(name)
        self.lookback = lookback
        self.z_entry = z_entry
        self.z_exit = z_exit
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def get_required_periods(self) -> int:
        return max(self.lookback, self.rsi_period) + 5

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # Z-Score of price
        df["rolling_mean"] = df["Close"].rolling(self.lookback).mean()
        df["rolling_std"] = df["Close"].rolling(self.lookback).std()
        df["z_score"] = (df["Close"] - df["rolling_mean"]) / df["rolling_std"]

        # RSI
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(self.rsi_period).mean()
        avg_loss = loss.rolling(self.rsi_period).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # Bollinger %B (position within Bollinger Bands)
        df["bb_upper"] = df["rolling_mean"] + 2 * df["rolling_std"]
        df["bb_lower"] = df["rolling_mean"] - 2 * df["rolling_std"]
        df["bb_pct"] = (df["Close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        return df

    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        if current_index < self.get_required_periods():
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=data.index[current_index],
                price=float(data.iloc[current_index]["Close"]),
            )

        curr = data.iloc[current_index]
        price = float(curr["Close"])
        timestamp = data.index[current_index]

        z = curr.get("z_score")
        rsi = curr.get("rsi")

        if pd.isna(z) or pd.isna(rsi):
            return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)

        # Oversold → BUY (mean reversion upward expected)
        if z <= -self.z_entry and rsi <= self.rsi_oversold:
            confidence = min(1.0, 0.5 + abs(z) * 0.15)
            return Signal(
                signal_type=SignalType.BUY,
                timestamp=timestamp,
                price=price,
                confidence=confidence,
                metadata={
                    "reason": "Z-Score oversold + RSI confirmation",
                    "z_score": float(z),
                    "rsi": float(rsi),
                },
            )

        # Overbought → SELL (mean reversion downward expected)
        elif z >= self.z_entry and rsi >= self.rsi_overbought:
            confidence = min(1.0, 0.5 + abs(z) * 0.15)
            return Signal(
                signal_type=SignalType.SELL,
                timestamp=timestamp,
                price=price,
                confidence=confidence,
                metadata={
                    "reason": "Z-Score overbought + RSI confirmation",
                    "z_score": float(z),
                    "rsi": float(rsi),
                },
            )

        return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)
