"""
Value at Risk (VaR) calculations for portfolio risk management.

Supports multiple VaR calculation methods:
- Historical VaR: Uses historical return percentiles
- Parametric VaR: Assumes normal distribution of returns
- Expected Shortfall (CVaR): Average loss beyond VaR threshold
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple
from .models import PortfolioVaR


def historical_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Calculate historical VaR using percentile method."""
    if len(returns) < 20:
        return 0.0
    percentile = (1 - confidence) * 100
    var = np.percentile(returns, percentile)
    return abs(var)


def parametric_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Calculate parametric VaR assuming normal distribution."""
    if len(returns) < 20:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std == 0:
        return 0.0
    from scipy import stats
    z_score = stats.norm.ppf(1 - confidence)
    var = -(mean + z_score * std)
    return max(0, var)


def monte_carlo_var(returns: np.ndarray, confidence: float = 0.95, simulations: int = 10000) -> float:
    """Calculate Monte Carlo VaR using parametric bootstrapping."""
    if len(returns) < 20:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std == 0:
        return 0.0
    np.random.seed(42)
    sim_returns = np.random.normal(mean, std, simulations)
    return abs(np.percentile(sim_returns, (1 - confidence) * 100))


def expected_shortfall(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Calculate Expected Shortfall (CVaR) - average loss beyond VaR."""
    if len(returns) < 20:
        return 0.0
    percentile = (1 - confidence) * 100
    var_threshold = np.percentile(returns, percentile)
    tail_losses = returns[returns <= var_threshold]
    if len(tail_losses) == 0:
        return abs(var_threshold)
    return abs(np.mean(tail_losses))


def calculate_portfolio_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    confidence: float = 0.95,
    portfolio_value: float = 1.0
) -> Tuple[float, float]:
    """Calculate portfolio VaR and volatility using weights and covariance matrix."""
    if len(weights) < 2 or cov_matrix.shape[0] != len(weights):
        return 0.0, 0.0
    portfolio_var = np.sqrt(weights @ cov_matrix @ weights)
    from scipy import stats
    z_score = stats.norm.ppf(1 - confidence)
    var_pct = abs(z_score * portfolio_var)
    return var_pct * portfolio_value, portfolio_var


def calculate_expected_shortfall_portfolio(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    confidence: float = 0.95,
    portfolio_value: float = 1.0
) -> float:
    """Calculate Expected Shortfall for portfolio using parametric approach."""
    if len(weights) < 2 or cov_matrix.shape[0] != len(weights):
        return 0.0
    portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
    if portfolio_vol == 0:
        return 0.0
    from scipy import stats
    # For normal distribution, ES = VaR * (phi(z)/alpha) where alpha = 1-confidence
    z_score = stats.norm.ppf(1 - confidence)
    alpha = 1 - confidence
    es_multiplier = stats.norm.pdf(z_score) / alpha
    return max(0, z_score * portfolio_vol * es_multiplier) * portfolio_value


def calculate_var_time_scaled(base_var: float, base_horizon: int, target_horizon: int) -> float:
    """Scale VaR to different time horizons using square root of time."""
    if base_horizon <= 0:
        return base_var
    return base_var * np.sqrt(target_horizon / base_horizon)


class VaRCalculator:
    """
    Calculate Value at Risk using multiple methodologies.

    VaR represents the maximum expected loss over a given time horizon
    at a given confidence level. For example, 1-day 95% VaR of $10,000
    means there's a 5% chance of losing more than $10,000 tomorrow.
    """

    def __init__(self, lookback_days: int = 252, time_horizon_days: int = 1):
        self.lookback_days = lookback_days
        self.time_horizon_days = time_horizon_days

    def calculate_historical_var(
        self,
        returns: np.ndarray,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate historical VaR using percentile method.

        Args:
            returns: Array of historical returns (positive = gain, negative = loss)
            confidence: Confidence level (0.95 = 95% VaR)

        Returns:
            VaR as positive number representing potential loss
        """
        if len(returns) < 20:
            return 0.0

        percentile = (1 - confidence) * 100
        var = np.percentile(returns, percentile)
        return abs(var)

    def calculate_parametric_var(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
        portfolio_value: float = 1.0
    ) -> float:
        """
        Calculate parametric VaR assuming normal distribution.

        Args:
            returns: Array of historical returns
            confidence: Confidence level
            portfolio_value: Current portfolio value for scaling

        Returns:
            VaR as positive number representing potential loss
        """
        if len(returns) < 20:
            return 0.0

        mean = np.mean(returns)
        std = np.std(returns, ddof=1)

        from scipy import stats
        z_score = stats.norm.ppf(1 - confidence)
        var = -(mean + z_score * std)

        return max(0, var) * portfolio_value * np.sqrt(self.time_horizon_days)

    def calculate_expected_shortfall(
        self,
        returns: np.ndarray,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Expected Shortfall (CVaR) - average loss beyond VaR.

        ES is always >= VaR (mathematical property).

        Args:
            returns: Array of historical returns
            confidence: Confidence level

        Returns:
            Expected Shortfall as positive number
        """
        if len(returns) < 20:
            return 0.0

        percentile = (1 - confidence) * 100
        var_threshold = np.percentile(returns, percentile)
        tail_losses = returns[returns <= var_threshold]

        if len(tail_losses) == 0:
            return abs(var_threshold)

        es = np.mean(tail_losses)
        return abs(es)

    def calculate_portfolio_var(
        self,
        portfolio_returns: np.ndarray,
        portfolio_value: float,
        confidence_levels: Tuple[float, ...] = (0.95, 0.99)
    ) -> PortfolioVaR:
        """
        Calculate comprehensive VaR metrics for a portfolio.

        Args:
            portfolio_returns: Array of portfolio daily returns
            portfolio_value: Current portfolio value
            confidence_levels: Confidence levels to calculate

        Returns:
            PortfolioVaR object with all metrics
        """
        results = PortfolioVaR(time_horizon_days=self.time_horizon_days)

        if len(portfolio_returns) < 20:
            return results

        for conf in confidence_levels:
            var = self.calculate_historical_var(portfolio_returns, conf)
            es = self.calculate_expected_shortfall(portfolio_returns, conf)

            if conf == 0.95:
                results.var_95 = var * portfolio_value
                results.expected_shortfall_95 = es * portfolio_value
            elif conf == 0.99:
                results.var_99 = var * portfolio_value
                results.expected_shortfall_99 = es * portfolio_value

        return results

    def calculate_component_var(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
        confidence: float = 0.95
    ) -> np.ndarray:
        """
        Calculate component VaR for each position (marginal contributions).

        Args:
            weights: Portfolio weights
            cov_matrix: Covariance matrix of returns
            confidence: Confidence level

        Returns:
            Array of component VaRs
        """
        from scipy import stats
        z = stats.norm.ppf(1 - confidence)

        portfolio_var = np.sqrt(weights @ cov_matrix @ weights) * z
        marginal_var = cov_matrix @ weights * z / portfolio_var
        component_var = weights * marginal_var

        return np.abs(component_var)