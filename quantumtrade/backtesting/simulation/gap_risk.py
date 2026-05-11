"""
Overnight gap risk and limit move modeling.

Models:
- Overnight price gaps between sessions
- Weekend gaps (longer time horizon → larger gaps)
- Limit moves (maximum allowable price change)
- Gap probability estimation from historical data
- Stop-loss orders behavior across gaps (no guarantee!)
"""

from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, time
import numpy as np
import pandas as pd

from quantumtrade.adapters.execution.models import OrderSide


class GapRiskAnalyzer:
    """
    Analyze and simulate overnight gap risk.

    Gaps occur during market closures (overnight, weekends, holidays).
    Key characteristics:
    - Longer closure → higher probability & larger average gap
    - News events → increased gap probability
    - High volatility assets → larger gaps

    The model estimates gap distribution from historical overnight returns.
    """

    def __init__(
        self,
        historical_gaps: Optional[pd.Series] = None,
        base_gap_probability: float = 0.02,
        base_gap_mean_pct: float = 0.3,
        base_gap_std_pct: float = 0.8,
        max_gap_pct: float = 15.0,
    ):
        """
        Initialize gap risk model.

        Args:
            historical_gaps: Series of historical overnight gap percentages
                If provided, model learns parameters from data
            base_gap_probability: Daily gap probability (used if no history)
            base_gap_mean_pct: Average gap size in % (if no history)
            base_gap_std_pct: Std dev of gap size in % (if no history)
            max_gap_pct: Maximum plausible gap (e.g., 15% for stocks)
        """
        self.max_gap = max_gap_pct / 100

        if historical_gaps is not None and len(historical_gaps) > 10:
            self._calibrate_from_history(historical_gaps)
        else:
            self.gap_probability = base_gap_probability
            self.gap_mean = base_gap_mean_pct / 100
            self.gap_std = base_gap_std_pct / 100

    def _calibrate_from_history(self, gaps: pd.Series):
        """Fit log-normal distribution to historical gap data."""
        # Only use non-zero gaps
        non_zero_gaps = gaps[gaps != 0].abs() / 100  # Convert % → decimal

        if len(non_zero_gaps) == 0:
            self.gap_probability = 0.0
            self.gap_mean = 0.0
            self.gap_std = 0.0
            return

        self.gap_probability = len(non_zero_gaps) / len(gaps)

        # Fit log-normal to positive gap magnitudes
        log_gaps = np.log(non_zero_gaps.clip(lower=1e-9))
        self.gap_mean = float(np.mean(log_gaps))
        self.gap_std = float(np.std(log_gaps))

    def estimate_gap_probability(
        self,
        holding_days: int = 1,
        volatility: float = 0.02,
        is_earnings: bool = False,
    ) -> float:
        """
        Estimate gap probability for a given holding period.

        Args:
            holding_days: Number of overnight periods (1 = 1 night)
            volatility: Daily volatility (higher → higher gap risk)
            is_earnings: If True, add earnings announcement gap risk

        Returns:
            Probability of at least one gap during holding period
        """
        # Base daily probability from model
        daily_prob = self.gap_probability

        # Adjust by volatility: higher vol → more gaps
        vol_factor = volatility / 0.02  # normalized to 2% daily
        daily_prob *= vol_factor

        # Earnings bump: 3-5% additional probability
        if is_earnings:
            daily_prob += 0.03

        # Cap daily probability at 30%
        daily_prob = min(daily_prob, 0.30)

        # Probability of at least one gap in N days:
        # P = 1 - (1 - p)^N
        gap_prob = 1 - (1 - daily_prob) ** holding_days

        return float(np.clip(gap_prob, 0.0, 1.0))

    def simulate_overnight_gap(
        self,
        previous_close: float,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[float, float]:
        """
        Simulate a single overnight gap.

        Args:
            previous_close: Previous session closing price
            rng: Random generator

        Returns:
            (gap_pct, new_open):
                gap_pct as signed decimal (e.g., -0.023 = -2.3%)
                new_open is opening price after gap
        """
        rng = rng or np.random.default_rng()

        if rng.random() > self.gap_probability:
            return 0.0, previous_close

        # Sample gap magnitude from log-normal distribution
        raw_gap = rng.lognormal(mean=self.gap_mean, sigma=self.gap_std)
        gap_magnitude = min(raw_gap, self.max_gap)

        # Random direction with slight downward bias (-0.3% mean for equities)
        # But we'll keep symmetric for now
        direction = 1 if rng.random() > 0.5 else -1
        gap_pct = direction * gap_magnitude

        new_open = previous_close * (1 + gap_pct)

        return gap_pct, new_open

    def simulate_gap_distribution(
        self,
        n_simulations: int,
        previous_close: float = 100.0,
        seed: Optional[int] = None,
    ) -> np.ndarray:
        """
        Generate distribution of simulated overnight gaps.

        Useful for Monte Carlo analysis of gap risk.

        Args:
            n_simulations: Number of gap scenarios
            previous_close: Starting price
            seed: Random seed

        Returns:
            Array of gap percentages (signed)
        """
        rng = np.random.default_rng(seed)

        gaps = np.zeros(n_simulations)

        for i in range(n_simulations):
            gap_pct, _ = self.simulate_overnight_gap(previous_close, rng)
            gaps[i] = gap_pct * 100  # Return in percent

        return gaps

    def calculate_var_from_gaps(
        self,
        confidence_level: float = 0.95,
        holding_days: int = 1,
        position_size: float = 1.0,
    ) -> float:
        """
        Calculate VaR contribution from gap risk.

        Args:
            confidence_level: VaR confidence (e.g., 0.95)
            holding_days: Holding horizon in days
            position_size: Dollar size of position

        Returns:
            Dollar VaR from gaps (one-tailed loss)
        """
        # Simulate many gaps
        n_sims = 10000
        rng = np.random.default_rng(42)
        losses = []

        for _ in range(n_sims):
            gap_pct, _ = self.simulate_overnight_gap(100.0, rng)
            # Loss for long position: negative gap (gap down)
            if gap_pct < 0:
                loss = -gap_pct * position_size
                losses.append(loss)
            else:
                losses.append(0.0)

        losses = np.array(losses)
        var = np.percentile(losses, confidence_level * 100)

        return float(var)

    def get_gap_statistics(
        self,
        n_simulations: int = 10000,
    ) -> Dict[str, float]:
        """
        Compute statistics about gap distribution.

        Returns:
            dict with:
              - gap_frequency: % of days with a gap
              - avg_gap_magnitude_pct: Average |gap| when gaps occur
              - avg_gap_loss_pct: Average gap that hurts (down gaps for long)
              - p95_gap_pct: 95th percentile gap size
              - expected_loss_pct: E[loss] from gap risk (for long)
        """
        rng = np.random.default_rng(42)
        gaps_pct = []
        for _ in range(n_simulations):
            gap_pct, _ = self.simulate_overnight_gap(100.0, rng)
            gaps_pct.append(gap_pct)

        gaps_pct = np.array(gaps_pct)
        gaps_abs = np.abs(gaps_pct)
        loss_gaps = gaps_pct[gaps_pct < 0]

        stats = {
            "gap_frequency": float(np.mean(gaps_abs > 0)),
            "avg_gap_magnitude_pct": float(np.mean(gaps_abs[gaps_abs > 0])) if np.any(gaps_abs > 0) else 0.0,
            "avg_gap_loss_pct": float(np.mean(loss_gaps)) if len(loss_gaps) > 0 else 0.0,
            "p95_gap_pct": float(np.percentile(gaps_abs[gaps_abs > 0], 95)) if np.any(gaps_abs > 0) else 0.0,
            "expected_loss_pct": float(np.mean(-loss_gaps)) if len(loss_gaps) > 0 else 0.0,
        }

        return stats


class LimitMoveModel:
    """
    Model exchange limit-up/limit-down (LULD) bands.

    LULD rules (NYSE/NASDAQ):
    - Price bands based on reference price (usually previous close)
    - Limit Up: max +5% to +10% above reference
    - Limit Down: max -5% to -10% below reference
    - Shorter limits for cheap stocks (<$3) or ETFs
    - If price hits limit, trading halts in that direction; can only trade inside band
    """

    def __init__(
        self,
        reference_price: float,
        limit_level: float = 0.10,
        lower_limit: Optional[float] = None,
    ):
        """
        Args:
            reference_price: Reference price for calculating limits
            limit_level: Max % move (0.10 = 10% up/down)
            lower_limit: Optional custom lower band (as fraction negative)
        """
        self.ref_price = reference_price
        self.limit_level = limit_level

        self.upper_limit = reference_price * (1 + limit_level)
        self.lower_limit = lower_limit if lower_limit is not None else reference_price * (1 - limit_level)

    def is_at_limit(self, price: float) -> Tuple[bool, str]:
        """
        Check if price is at a limit.

        Returns:
            (is_at_limit, side):
                side: "upper", "lower", or ""
        """
        if price >= self.upper_limit:
            return True, "upper"
        elif price <= self.lower_limit:
            return True, "lower"
        return False, ""

    def constrain_price(
        self,
        price: float,
    ) -> Tuple[float, bool]:
        """
        Constrain a price to the limit band.

        Args:
            price: Proposed price

        Returns:
            (constrained_price, was_limited): Whether price hit a band
        """
        at_limit, side = self.is_at_limit(price)

        if at_limit:
            if side == "upper":
                return self.upper_limit, True
            else:
                return self.lower_limit, True
        return price, False

    def simulate_limited_trading(
        self,
        true_value: float,
        rng: Optional[np.random.Generator] = None,
    ) -> float:
        """
        Simulate an execution price under LULD constraints.

        If true_value is outside band, execution defaults to band edge.

        Args:
            true_value: "Fair" price without limits
            rng: Random generator (unused, currently deterministic)

        Returns:
            Execution price constrained to limit band
        """
        constrained, _ = self.constrain_price(true_value)
        return constrained
