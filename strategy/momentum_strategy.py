"""
Momentum Strategy — Multi-Timeframe Trend Rider.

Strategy Logic:
  - Measures Rate of Change (ROC) across multiple lookback periods
  - Confirms with ADX (Average Directional Index) for trend strength
  - BUY when multi-period momentum is positive AND trend is strong
  - SELL when momentum turns negative with trend confirmation
  - Higher ADX = stronger trend = higher confidence

Best Used:
  - Trending markets (NOT sideways/ranging)
  - Growth stocks & crypto assets
  - Daily timeframe with swing-trading holding periods
"""

import pandas as pd
import numpy as np
from datetime import datetime

from .base import BaseStrategy
from .signals import Signal, SignalType


class MomentumStrategy(BaseStrategy):
    """Multi-period momentum with ADX trend confirmation."""

    def __init__(
        self,
        fast_roc: int = 5,
        mid_roc: int = 10,
        slow_roc: int = 20,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        name: str = "Momentum",
    ):
        """
        Args:
            fast_roc: Short-term ROC period (5 days)
            mid_roc: Medium-term ROC period (10 days)
            slow_roc: Long-term ROC period (20 days)
            adx_period: ADX calculation period
            adx_threshold: Minimum ADX for trend confirmation (>25 = trending)
        """
        super().__init__(name)
        self.fast_roc = fast_roc
        self.mid_roc = mid_roc
        self.slow_roc = slow_roc
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold

    def get_required_periods(self) -> int:
        return self.slow_roc + self.adx_period + 5

    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()

        # Rate of Change (ROC) — percentage change over N periods
        df["roc_fast"] = df["Close"].pct_change(self.fast_roc) * 100
        df["roc_mid"] = df["Close"].pct_change(self.mid_roc) * 100
        df["roc_slow"] = df["Close"].pct_change(self.slow_roc) * 100

        # Composite momentum score (weighted average)
        df["momentum_score"] = (
            df["roc_fast"] * 0.5 +
            df["roc_mid"] * 0.3 +
            df["roc_slow"] * 0.2
        )

        # ADX (Average Directional Index) for trend strength
        df["adx"] = self._calculate_adx(df, self.adx_period)

        # Momentum acceleration (is momentum increasing?)
        df["momentum_accel"] = df["momentum_score"].diff()

        return df

    def _calculate_adx(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate ADX (Average Directional Index)."""
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        # +DM / -DM
        plus_dm = high.diff()
        minus_dm = low.diff().abs()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)  # noqa

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Smoothed TR, +DM, -DM
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        # DX and ADX
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.rolling(period).mean()

        return adx

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

        mom = curr.get("momentum_score")
        adx = curr.get("adx")
        accel = curr.get("momentum_accel")
        prev_mom = prev.get("momentum_score")

        if pd.isna(mom) or pd.isna(adx):
            return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)

        is_trending = adx >= self.adx_threshold if not pd.isna(adx) else False
        mom_accel = accel > 0 if not pd.isna(accel) else False

        # Bullish momentum: composite score crosses above 0 with trend
        if prev_mom is not None and not pd.isna(prev_mom):
            if prev_mom <= 0 and mom > 0 and is_trending:
                conf = min(1.0, 0.5 + (float(adx) - self.adx_threshold) * 0.01)
                return Signal(
                    signal_type=SignalType.BUY,
                    timestamp=timestamp,
                    price=price,
                    confidence=max(0.5, conf),
                    metadata={
                        "reason": "Bullish momentum crossover with trend",
                        "momentum_score": float(mom),
                        "adx": float(adx),
                        "accelerating": mom_accel,
                    },
                )

            # Bearish momentum: composite score crosses below 0 with trend
            elif prev_mom >= 0 and mom < 0 and is_trending:
                conf = min(1.0, 0.5 + (float(adx) - self.adx_threshold) * 0.01)
                return Signal(
                    signal_type=SignalType.SELL,
                    timestamp=timestamp,
                    price=price,
                    confidence=max(0.5, conf),
                    metadata={
                        "reason": "Bearish momentum crossover with trend",
                        "momentum_score": float(mom),
                        "adx": float(adx),
                        "accelerating": mom_accel,
                    },
                )

        return Signal(signal_type=SignalType.HOLD, timestamp=timestamp, price=price)
