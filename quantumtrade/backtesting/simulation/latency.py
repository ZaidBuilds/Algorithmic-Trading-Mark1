"""
Latency simulation for backtesting.

Models the delay between signal generation and order execution.
During latency, price may move → slippage.

Latency sources:
- Network latency: 50-200ms typical
- Broker API: 100-500ms
- Exchange matching: 0-100ms
"""

from typing import Optional
from datetime import datetime, timedelta
import numpy as np

from quantumtrade.adapters.execution.models import OrderSide


class LatencyModel:
    """
    Simulates execution latency in trading systems.

    Models random network delays, broker processing times, and
    exchange matching latency. During the latency window, the
    market price may move, creating inevitable slippage.

    The model converts latency (milliseconds) into an expected
    price movement based on the asset's volatility.
    """

    def __init__(
        self,
        mean_latency_ms: float = 150.0,
        std_latency_ms: float = 50.0,
        min_latency_ms: float = 10.0,
        max_latency_ms: float = 1000.0,
    ):
        """
        Initialize latency model.

        Args:
            mean_latency_ms: Mean latency in milliseconds (default 150ms)
            std_latency_ms: Standard deviation of latency (default 50ms)
            min_latency_ms: Minimum possible latency (default 10ms)
            max_latency_ms: Maximum possible latency (default 1000ms)
        """
        self.mean_ms = mean_latency_ms
        self.std_ms = std_latency_ms
        self.min_ms = min_latency_ms
        self.max_ms = max_latency_ms

    def sample_latency(self, rng: Optional[np.random.Generator] = None) -> float:
        """
        Sample a random latency value.

        Uses truncated normal distribution bounded by min/max.

        Args:
            rng: Optional numpy random generator for reproducibility

        Returns:
            Latency in milliseconds
        """
        rng = rng or np.random.default_rng()

        # Sample from normal then clip
        latency = rng.normal(self.mean_ms, self.std_ms)
        latency = np.clip(latency, self.min_ms, self.max_ms)

        return float(latency)

    def calculate_price_shift(
        self,
        latency_ms: float,
        volatility: float,
        current_price: float,
        side: OrderSide,
    ) -> float:
        """
        Calculate expected price movement during latency period.

        Assumes geometric Brownian motion: price change ~ volatility * sqrt(dt)

        Args:
            latency_ms: Latency in milliseconds
            volatility: Annualized volatility (e.g., 0.20 = 20%)
            current_price: Current price (mid or last)
            side: Order side (determines adverse direction)

        Returns:
            Shifted price (slippage applied to current_price)

        Example:
            latency = 150ms, volatility = 25% annual
            → daily vol ≈ 0.25 / sqrt(252) ≈ 0.0158
            → 150ms vol ≈ 0.0158 * sqrt(150/86400000) ≈ 0.00023
            → price shift ≈ current_price * 0.023% (0.23 bps)
        """
        if latency_ms <= 0 or volatility <= 0 or current_price <= 0:
            return current_price

        # Convert annual volatility to per-millisecond volatility
        # Assuming 252 trading days * 6.5 hours * 3600 seconds * 1000 ms
        # But simpler: use sqrt(time_ratio) where time_ratio = dt / T
        # T = 1 year in ms = 365.25 * 24 * 3600 * 1000 ≈ 31.5 billion ms
        # Or use trading days: 252 days * 6.5h * 3600s * 1000 = ~21 billion ms per year

        ms_per_year = 252 * 6.5 * 3600 * 1000  # ≈ 21.5B ms per trading year
        time_ratio = latency_ms / ms_per_year

        # Standard deviation of log returns over latency period
        sigma_dt = volatility * np.sqrt(time_ratio)

        # Expected absolute price movement (rough approximation)
        # For small dt, price change ≈ price * sigma_dt
        expected_shift = current_price * sigma_dt

        # For adverse selection: assume worst-case direction
        # For buy: price goes up; for sell: price goes down
        if side == OrderSide.BUY:
            adverse_shift = expected_shift
        else:
            adverse_shift = -expected_shift

        return current_price + adverse_shift

    def estimate_slippage_bps(
        self,
        latency_ms: float,
        volatility: float,
        current_price: float,
    ) -> float:
        """
        Estimate expected slippage in bps from latency alone.

        Args:
            latency_ms: Simulated latency
            volatility: Annualized volatility
            current_price: Current price

        Returns:
            Slippage in basis points (positive value)
        """
        if latency_ms <= 0 or volatility <= 0 or current_price <= 0:
            return 0.0

        shifted = self.calculate_price_shift(
            latency_ms, volatility, current_price, OrderSide.BUY
        )
        slippage_bps = abs((shifted - current_price) / current_price) * 10000

        return slippage_bps


class FixedLatencyModel(LatencyModel):
    """Deterministic fixed latency (no randomness)."""

    def __init__(self, fixed_latency_ms: float = 150.0):
        super().__init__(
            mean_latency_ms=fixed_latency_ms,
            std_latency_ms=0.0,
            min_latency_ms=fixed_latency_ms,
            max_latency_ms=fixed_latency_ms,
        )


class LatencyDistribution:
    """
    Statistical model of latency distributions across multiple sources.

    Combines: network + broker + exchange latency distributions.
    """

    def __init__(
        self,
        network_mean_ms: float = 100.0,
        network_std_ms: float = 50.0,
        broker_mean_ms: float = 200.0,
        broker_std_ms: float = 100.0,
        exchange_mean_ms: float = 50.0,
        exchange_std_ms: float = 30.0,
    ):
        """
        Initialize multi-component latency model.

        Args:
            network_mean_ms: Network RTT mean
            network_std_ms: Network RTT std dev
            broker_mean_ms: Broker API processing time mean
            broker_std_ms: Broker API processing time std dev
            exchange_mean_ms: Exchange matching engine latency
            exchange_std_ms: Exchange matching engine std dev
        """
        self.network_mean = network_mean_ms
        self.network_std = network_std_ms
        self.broker_mean = broker_mean_ms
        self.broker_std = broker_std_ms
        self.exchange_mean = exchange_mean_ms
        self.exchange_std = exchange_std_ms

    def sample_total_latency(self, rng: Optional[np.random.Generator] = None) -> float:
        """
        Sample total latency by summing independent components.

        Each component is sampled from a log-normal distribution
        (since latency cannot be negative and is often right-skewed).

        Args:
            rng: Optional random generator

        Returns:
            Total latency in milliseconds
        """
        rng = rng or np.random.default_rng()

        # Log-normal is more realistic for network latency
        def sample_lognormal(mean, std):
            # Convert mean/std to lognormal mu/sigma
            # For lognormal: mean = exp(mu + sigma^2/2), var = ...
            phi = np.sqrt(std**2 + mean**2)
            mu = np.log(mean**2 / phi)
            sigma = np.sqrt(np.log(phi**2 / mean**2))
            return rng.lognormal(mean=mu, sigma=sigma)

        network = sample_lognormal(self.network_mean, self.network_std)
        broker = sample_lognormal(self.broker_mean, self.broker_std)
        exchange = sample_lognormal(self.exchange_mean, self.exchange_std)

        total = network + broker + exchange

        return float(total)
