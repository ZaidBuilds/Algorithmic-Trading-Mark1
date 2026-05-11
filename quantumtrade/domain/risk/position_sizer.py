"""
Position Sizing Engine - Multiple sophisticated sizing algorithms.

Implements 5 sizing strategies:
- Fixed Fractional: Risk fixed % of portfolio
- Kelly Criterion: Optimal f based on win rate and payoff ratio
- Volatility-Adjusted: Scale by inverse volatility (Paradoxical sizing)
- Equal Risk Allocation: Each position contributes equal portfolio risk
- Confidence-Weighted: Scale by strategy confidence
- Composite: Weighted combination of multiple models
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Optional, Tuple, Any, Callable
import numpy as np

from .models import SizingDecision

logger = logging.getLogger(__name__)


@dataclass
class SizingStrategyConfig:
    """Configuration for a sizing strategy."""
    enabled: bool = True
    weight: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)


class PositionSizer:
    """
    Advanced position sizing engine with multiple algorithms.

    Each strategy calculates position size differently:
    - Fixed Fractional: Base risk-based sizing
    - Kelly: Growth-optimal based on statistics
    - Volatility-Adjusted: Risk-adjusted for market conditions
    - Equal Risk: Positions contribute equal risk
    - Confidence-Weighted: Scaled by strategy confidence
    - Composite: Weighted ensemble of models
    """

    VALID_STRATEGIES = [
        "fixed_fractional",
        "kelly",
        "volatility_adjusted",
        "equal_risk",
        "confidence_weighted",
        "composite",
    ]

    def __init__(
        self,
        portfolio_value: float,
        risk_per_trade_pct: float = 0.02,
        max_position_pct: float = 0.10,
        strategy: str = "fixed_fractional",
        target_volatility: float = 0.20,
        kelly_fraction_cap: float = 0.05,
    ):
        self.portfolio_value = portfolio_value
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_position_pct = max_position_pct
        self.strategy = strategy
        self.target_volatility = target_volatility
        self.kelly_fraction_cap = kelly_fraction_cap

        if strategy not in self.VALID_STRATEGIES:
            raise ValueError(f"Invalid strategy: {strategy}. Must be one of {self.VALID_STRATEGIES}")

        self._volatility_cache: Dict[str, Tuple[float, float]] = {}

    def _kelly_fraction(
        self,
        win_rate: Optional[float],
        payoff_ratio: Optional[float],
    ) -> float:
        """
        Calculate Kelly fraction: f* = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio

        Args:
            win_rate: Historical win rate (0-1), defaults to 0.5 if unknown
            payoff_ratio: avg_win / avg_loss, defaults to 1.5 if unknown

        Returns:
            Optimal fraction (clamped to max 0.5 for safety)
        """
        wr = win_rate if win_rate is not None and 0 < win_rate < 1 else 0.5
        pr = payoff_ratio if payoff_ratio is not None and payoff_ratio > 0 else 1.5

        if pr <= 0:
            return 0.0

        kelly_f = (wr * pr - (1 - wr)) / pr

        capped_kelly = min(self.kelly_fraction_cap, max(0.0, kelly_f))

        return capped_kelly * 0.5

    def _estimate_volatility(self, symbol: str, volatility: Optional[float] = None) -> float:
        """
        Get volatility estimate, using cache if available.

        Args:
            symbol: Trading symbol
            volatility: Provided volatility value (optional)

        Returns:
            Annualized volatility (0.20 default if unknown)
        """
        if volatility is not None and volatility > 0:
            return volatility

        if symbol in self._volatility_cache:
            cached_vol, timestamp = self._volatility_cache[symbol]
            if np.isfinite(timestamp) and (np.datetime64('now') - timestamp).item() / 3600000000000 < 1:
                return cached_vol

        return self.target_volatility

    def _calculate_fixed_fractional(
        self,
        entry_price: float,
        stop_distance: float,
    ) -> Tuple[int, Dict[str, Any]]:
        """Fixed fractional sizing - risk fixed % of portfolio."""
        risk_amount = self.portfolio_value * self.risk_per_trade_pct
        quantity = int(risk_amount / stop_distance)

        return quantity, {
            "reason": "Fixed fractional: risk fixed % of portfolio",
            "risk_amount_usd": quantity * stop_distance,
        }

    def _calculate_kelly(
        self,
        entry_price: float,
        stop_distance: float,
        win_rate: Optional[float],
        payoff_ratio: Optional[float],
    ) -> Tuple[int, Dict[str, Any]]:
        """Kelly Criterion sizing - growth optimal."""
        kelly_f = self._kelly_fraction(win_rate, payoff_ratio)
        risk_amount = self.portfolio_value * kelly_f

        quantity = int(risk_amount / stop_distance)

        return quantity, {
            "reason": f"Kelly criterion: half-kelly={kelly_f:.4f}",
            "risk_amount_usd": quantity * stop_distance,
            "kelly_fraction": kelly_f,
        }

    def _calculate_volatility_adjusted(
        self,
        entry_price: float,
        stop_distance: float,
        volatility: Optional[float],
    ) -> Tuple[int, Dict[str, Any]]:
        """Volatility-adjusted sizing - inverse volatility weighting."""
        base_quantity = int((self.portfolio_value * self.risk_per_trade_pct) / stop_distance)

        if volatility and volatility > 0:
            adj = min(2.0, max(0.5, self.target_volatility / volatility))
        else:
            adj = 1.0

        quantity = int(base_quantity * adj)

        return quantity, {
            "reason": f"Vol-adjusted: adj={adj:.2f}x",
            "risk_amount_usd": quantity * stop_distance,
            "volatility_adjustment": adj,
        }

    def _calculate_equal_risk(
        self,
        entry_price: float,
        stop_distance: float,
    ) -> Tuple[int, Dict[str, Any]]:
        """Equal risk allocation - direct risk budget calculation."""
        risk_budget = self.portfolio_value * self.risk_per_trade_pct
        quantity = int(risk_budget / stop_distance)

        return quantity, {
            "reason": "Equal risk: risk_budget/stop_distance",
            "risk_amount_usd": quantity * stop_distance,
        }

    def _calculate_confidence_weighted(
        self,
        entry_price: float,
        stop_distance: float,
        confidence: Optional[float],
    ) -> Tuple[int, Dict[str, Any]]:
        """Confidence-weighted sizing - scaled by signal confidence."""
        base_risk = self.portfolio_value * self.risk_per_trade_pct
        conf = confidence if confidence is not None else 1.0
        conf = max(0.0, min(1.0, conf))

        risk_amount = base_risk * conf
        quantity = int(risk_amount / stop_distance)

        return quantity, {
            "reason": f"Conf-weighted: conf={conf:.2f}",
            "risk_amount_usd": quantity * stop_distance,
            "confidence_factor": conf,
        }

    def _calculate_composite(
        self,
        entry_price: float,
        stop_distance: float,
        confidence: Optional[float],
        volatility: Optional[float],
        win_rate: Optional[float],
        payoff_ratio: Optional[float],
        strategy_weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """Composite sizing - weighted ensemble of models."""
        weights = strategy_weights or {"kelly": 0.4, "volatility_adjusted": 0.3, "equal_risk": 0.3}

        sizes = {}

        kelly_q, kelly_m = self._calculate_kelly(entry_price, stop_distance, win_rate, payoff_ratio)
        sizes["kelly"] = kelly_q

        vol_q, vol_m = self._calculate_volatility_adjusted(entry_price, stop_distance, volatility)
        sizes["volatility_adjusted"] = vol_q

        eq_q, eq_m = self._calculate_equal_risk(entry_price, stop_distance)
        sizes["equal_risk"] = eq_q

        conf_q, conf_m = self._calculate_confidence_weighted(entry_price, stop_distance, confidence)
        sizes["confidence_weighted"] = conf_q

        weighted_sum = 0.0
        total_weight = 0.0
        for model, weight in weights.items():
            if model in sizes:
                weighted_sum += sizes[model] * weight
                total_weight += weight

        quantity = int(weighted_sum / total_weight) if total_weight > 0 else sizes["equal_risk"]

        return quantity, {
            "reason": f"Composite: weighted {weights}",
            "risk_amount_usd": quantity * stop_distance,
        }

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        confidence: Optional[float] = None,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_win_loss_ratio: Optional[float] = None,
        current_positions: int = 0,
        strategy_weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Calculate position size based on selected strategy.

        Args:
            symbol: Trading symbol
            entry_price: Proposed entry price
            stop_loss_price: Stop loss price for risk calculation
            confidence: Strategy confidence (0-1)
            volatility: Annualized volatility (optional)
            win_rate: Historical win rate (optional)
            avg_win_loss_ratio: Payoff ratio avg_win/avg_loss (optional)
            current_positions: Number of open positions
            strategy_weights: Weights for composite strategy

        Returns:
            Tuple of (quantity, metadata_dict)
        """
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance <= 0:
            return 0, {"error": "Zero or negative stop distance", "sizing_model": self.strategy}

        if entry_price <= 0:
            return 0, {"error": "Invalid entry price", "sizing_model": self.strategy}

        try:
            if self.strategy == "fixed_fractional":
                quantity, metadata = self._calculate_fixed_fractional(entry_price, stop_distance)
            elif self.strategy == "kelly":
                quantity, metadata = self._calculate_kelly(entry_price, stop_distance, win_rate, avg_win_loss_ratio)
            elif self.strategy == "volatility_adjusted":
                quantity, metadata = self._calculate_volatility_adjusted(entry_price, stop_distance, volatility)
            elif self.strategy == "equal_risk":
                quantity, metadata = self._calculate_equal_risk(entry_price, stop_distance)
            elif self.strategy == "confidence_weighted":
                quantity, metadata = self._calculate_confidence_weighted(entry_price, stop_distance, confidence)
            elif self.strategy == "composite":
                quantity, metadata = self._calculate_composite(
                    entry_price, stop_distance, confidence, volatility,
                    win_rate, avg_win_loss_ratio, strategy_weights
                )
            else:
                quantity, metadata = self._calculate_fixed_fractional(entry_price, stop_distance)

            if self.portfolio_value > 0:
                max_qty_by_cap = int((self.portfolio_value * self.max_position_pct) / entry_price)
                quantity = min(quantity, max_qty_by_cap)

            quantity = max(1, quantity)

            metadata["sizing_model"] = self.strategy
            metadata["stop_distance_pct"] = stop_distance / entry_price * 100
            if self.portfolio_value > 0:
                metadata["risk_pct"] = (quantity * stop_distance) / self.portfolio_value
            else:
                metadata["risk_pct"] = 0.0

            return quantity, metadata

        except Exception as e:
            logger.error(f"Position sizing failed for {symbol}: {e}")
            if self.portfolio_value > 0:
                fallback_qty = int((self.portfolio_value * self.risk_per_trade_pct) / stop_distance)
                fallback_qty = max(1, min(fallback_qty, int(self.portfolio_value * self.max_position_pct / entry_price)))
            else:
                fallback_qty = 1

            risk_pct = (fallback_qty * stop_distance) / self.portfolio_value if self.portfolio_value > 0 else 0.0
            return fallback_qty, {
                "sizing_model": self.strategy,
                "error": str(e),
                "risk_amount_usd": fallback_qty * stop_distance,
                "risk_pct": risk_pct,
            }

    def get_sizing_decision(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        confidence: Optional[float] = None,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_win_loss_ratio: Optional[float] = None,
        current_positions: int = 0,
    ) -> SizingDecision:
        """Get a typed SizingDecision object."""
        quantity, metadata = self.calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            confidence=confidence,
            volatility=volatility,
            win_rate=win_rate,
            avg_win_loss_ratio=avg_win_loss_ratio,
            current_positions=current_positions,
        )

        return SizingDecision(
            quantity=quantity,
            sizing_model=metadata.get("sizing_model", self.strategy),
            risk_amount_usd=metadata.get("risk_amount_usd", 0.0),
            risk_pct=metadata.get("risk_pct", 0.0),
            stop_distance_pct=metadata.get("stop_distance_pct", 0.0),
            reason=metadata.get("reason", ""),
            kelly_fraction=metadata.get("kelly_fraction"),
            volatility_adjustment=metadata.get("volatility_adjustment"),
            confidence_factor=metadata.get("confidence_factor"),
        )

    def set_strategy(self, strategy: str) -> None:
        """Change sizing strategy at runtime."""
        if strategy not in self.VALID_STRATEGIES:
            raise ValueError(f"Invalid strategy: {strategy}")
        self.strategy = strategy
        logger.info(f"Position sizing strategy changed to: {strategy}")