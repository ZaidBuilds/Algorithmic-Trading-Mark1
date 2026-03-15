"""
Scalping Strategy — High-Frequency Short-Term Signals.

Strategy Logic:
  - Uses fast EMA (3/8 periods) for quick trend detection
  - Combines with Stochastic Oscillator for overbought/oversold readings
  - BUY when fast EMA crossover + Stochastic oversold + volume spike
  - SELL when fast EMA crossunder + Stochastic overbought + volume spike
  - Targets small, frequent profits (0.1% – 0.5%)

Best Used:
  - Very short timeframes (1m, 5m, 15m)
  - Highly liquid assets (top stocks, BTC, ETH)
  - Requires low latency & low commissions
"""

import pandas as pd
import numpy as np
from datetime import datetime

from .base import BaseStrategy
from .signals import Signal, SignalType


class ScalpingStrategy(BaseStrategy):
    """Fast scalping strategy with EMA + Stochastic + Volume."""

    def __init__(
        self,
        fast_ema: int = 3,
        slow_ema: int = 8,
        stoch_k: int = 5,
        stoch_d: int = 3,
        stoch_oversold: float = 20.0,
        stoch_overbought: float = 80.0,
        volume_spike: float = 1.5,
        name: str = "Scalping",
    ):
        """
        Args:
            fast_ema: Fast EMA period (very short for scalping)
            slow_ema: Slow EMA period
            stoch_k: Stochastic %K period
            stoch_d: Stochastic %D smoothing period
            stoch_oversold: Stochastic oversold threshold
            stoch_overbought: Stochastic overbought threshold
            volume_spike: Minimum volume ratio for confirmation
        """
        super().__init__(name)
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.stoch_k = stoch_k
        self.stoch_d = stoch_d
        self.stoch_oversold = stoch_oversold
        self.stoch_overbought = stoch_overbought
        self.volume_spike = volume_spike

    def get_required_periods(self) -> int:
        return 20

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # Fast EMAs
        df["scalp_ema_fast"] = df["Close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["scalp_ema_slow"] = df["Close"].ewm(span=self.slow_ema, adjust=False).mean()

        # Stochastic Oscillator
        low_min = df["Low"].rolling(self.stoch_k).min()
        high_max = df["High"].rolling(self.stoch_k).max()
        df["stoch_k"] = ((df["Close"] - low_min) / (high_max - low_min)) * 100
        df["stoch_d"] = df["stoch_k"].rolling(self.stoch_d).mean()

        # Volume ratio
        df["scalp_avg_vol"] = df["Volume"].rolling(10).mean()
        df["scalp_vol_ratio"] = df["Volume"] / df["scalp_avg_vol"]

        # Price spread (high - low as % of close)
        df["spread_pct"] = (df["High"] - df["Low"]) / df["Close"] * 100

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

        fast = curr.get("scalp_ema_fast")
        slow = curr.get("scalp_ema_slow")
        prev_fast = prev.get("scalp_ema_fast")
        prev_slow = prev.get("scalp_ema_slow")
        stoch = curr.get("stoch_k")
        vol_ratio = curr.get("scalp_vol_ratio", 1.0)

        if any(pd.isna(v) for v in [fast, slow, prev_fast, prev_slow, stoch]):
            return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)

        vol_ok = vol_ratio >= self.volume_spike if not pd.isna(vol_ratio) else False

        # Scalp BUY: fast EMA crosses above slow + stochastic oversold + volume
        if (prev_fast <= prev_slow and fast > slow and
                stoch <= self.stoch_oversold and vol_ok):
            conf = min(1.0, 0.6 + (self.stoch_oversold - stoch) * 0.01)
            return Signal(
                signal_type=SignalType.BUY,
                timestamp=timestamp,
                price=price,
                confidence=max(0.5, conf),
                metadata={
                    "reason": "Scalp BUY: EMA cross + stochastic oversold + volume",
                    "stochastic": float(stoch),
                    "volume_ratio": float(vol_ratio),
                },
            )

        # Scalp SELL: fast EMA crosses below slow + stochastic overbought + volume
        elif (prev_fast >= prev_slow and fast < slow and
              stoch >= self.stoch_overbought and vol_ok):
            conf = min(1.0, 0.6 + (stoch - self.stoch_overbought) * 0.01)
            return Signal(
                signal_type=SignalType.SELL,
                timestamp=timestamp,
                price=price,
                confidence=max(0.5, conf),
                metadata={
                    "reason": "Scalp SELL: EMA cross + stochastic overbought + volume",
                    "stochastic": float(stoch),
                    "volume_ratio": float(vol_ratio),
                },
            )

        return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)
