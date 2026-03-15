"""
VWAP (Volume-Weighted Average Price) Strategy.

Strategy Logic:
  - VWAP = cumulative(Price × Volume) / cumulative(Volume)
  - BUY when price crosses above VWAP (bullish momentum)
  - SELL when price crosses below VWAP (bearish reversal)
  - Confidence scales with volume confirmation

Best Used:
  - Intraday trading (1m, 5m, 15m timeframes)
  - High-volume stocks with clear institutional interest
  - Mean-reversion setups around VWAP
"""

import pandas as pd
import numpy as np
from datetime import datetime

from .base import BaseStrategy
from .signals import Signal, SignalType


class VWAPStrategy(BaseStrategy):
    """VWAP-based trading strategy with volume confirmation."""

    def __init__(
        self,
        std_multiplier: float = 1.5,
        volume_threshold: float = 1.2,
        name: str = "VWAP",
    ):
        """
        Args:
            std_multiplier: Standard deviations for VWAP bands
            volume_threshold: Volume must exceed this × average to confirm signal
        """
        super().__init__(name)
        self.std_multiplier = std_multiplier
        self.volume_threshold = volume_threshold

    def get_required_periods(self) -> int:
        return 30

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # Typical price
        df["typical_price"] = (df["High"] + df["Low"] + df["Close"]) / 3

        # Cumulative VWAP
        df["cum_vol"] = df["Volume"].cumsum()
        df["cum_tp_vol"] = (df["typical_price"] * df["Volume"]).cumsum()
        df["vwap"] = df["cum_tp_vol"] / df["cum_vol"]

        # VWAP bands (standard deviation)
        df["vwap_std"] = df["typical_price"].rolling(20).std()
        df["vwap_upper"] = df["vwap"] + (df["vwap_std"] * self.std_multiplier)
        df["vwap_lower"] = df["vwap"] - (df["vwap_std"] * self.std_multiplier)

        # Relative volume
        df["avg_volume"] = df["Volume"].rolling(20).mean()
        df["rel_volume"] = df["Volume"] / df["avg_volume"]

        return df

    def generate_signal(self, data: pd.DataFrame, current_index: int) -> Signal:
        if current_index < 2:
            return Signal(
                signal_type=SignalType.HOLD,
                timestamp=data.index[current_index],
                price=float(data.iloc[current_index]["Close"]),
            )

        curr = data.iloc[current_index]
        prev = data.iloc[current_index - 1]
        price = float(curr["Close"])
        timestamp = data.index[current_index]

        if pd.isna(curr.get("vwap")) or pd.isna(prev.get("vwap")):
            return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)

        vwap = curr["vwap"]
        prev_close = prev["Close"]
        prev_vwap = prev["vwap"]
        rel_vol = curr.get("rel_volume", 1.0)

        # Bullish: price crosses above VWAP with volume
        if prev_close <= prev_vwap and price > vwap:
            vol_confirmed = rel_vol >= self.volume_threshold if not pd.isna(rel_vol) else False
            confidence = min(1.0, 0.5 + (0.3 if vol_confirmed else 0))
            return Signal(
                signal_type=SignalType.BUY,
                timestamp=timestamp,
                price=price,
                confidence=confidence,
                metadata={
                    "reason": "Price crossed above VWAP",
                    "vwap": float(vwap),
                    "volume_confirmed": vol_confirmed,
                },
            )

        # Bearish: price crosses below VWAP
        elif prev_close >= prev_vwap and price < vwap:
            confidence = min(1.0, 0.5 + (0.3 if rel_vol >= self.volume_threshold else 0))
            return Signal(
                signal_type=SignalType.SELL,
                timestamp=timestamp,
                price=price,
                confidence=confidence,
                metadata={
                    "reason": "Price crossed below VWAP",
                    "vwap": float(vwap),
                },
            )

        return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)
