"""
Correlation analysis for portfolio risk management.

Calculates correlation matrices, beta to benchmark, and diversification metrics.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from .models import CorrelationMetrics


def calculate_correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate correlation matrix from returns DataFrame."""
    if returns_df.empty or len(returns_df.columns) < 2:
        return pd.DataFrame()
    df = returns_df.dropna(axis=1, how='all').dropna(axis=0, how='all')
    if len(df.columns) < 2:
        return pd.DataFrame()
    return df.corr()


def calculate_beta(portfolio_returns: np.ndarray, benchmark_returns: np.ndarray) -> float:
    """Calculate portfolio beta to a benchmark."""
    if len(portfolio_returns) < 20 or len(benchmark_returns) < 20:
        return 1.0
    min_len = min(len(portfolio_returns), len(benchmark_returns))
    portfolio_returns = portfolio_returns[-min_len:]
    benchmark_returns = benchmark_returns[-min_len:]
    covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
    variance = np.var(benchmark_returns, ddof=1)
    if variance == 0:
        return 1.0
    return covariance / variance


def calculate_diversification_ratio(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """Calculate diversification ratio = portfolio vol / weighted avg vol."""
    if len(weights) < 2:
        return 1.0
    portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
    weighted_avg_vol = np.sum(np.abs(weights) * np.sqrt(np.diag(cov_matrix)))
    if weighted_avg_vol == 0:
        return 1.0
    return portfolio_vol / weighted_avg_vol


def calculate_average_correlation(corr_matrix: np.ndarray) -> float:
    """Calculate average correlation from correlation matrix."""
    if corr_matrix.shape[0] < 2:
        return 0.0
    return np.mean(corr_matrix[np.triu_indices_from(corr_matrix, 1)])


def get_largest_eigenvalue(cov_matrix: np.ndarray) -> float:
    """Get the largest eigenvalue from covariance matrix."""
    eigenvalues = np.linalg.eigvals(cov_matrix)
    return float(np.max(eigenvalues))


def calculate_portfolio_volatility(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """Calculate portfolio volatility from weights and covariance matrix."""
    return np.sqrt(weights @ cov_matrix @ weights)


class CorrelationAnalyzer:
    """
    Analyze correlations between portfolio holdings and compute diversification metrics.

    Key metrics:
    - Correlation matrix: How assets move together
    - Diversification score: 1 = perfectly diversified, 0 = single asset
    - Market factor dominance: Largest eigenvalue / sum of eigenvalues
    """

    def __init__(self, lookback_days: int = 252):
        self.lookback_days = lookback_days
        self._correlation_cache: Optional[np.ndarray] = None
        self._symbols: List[str] = []

    def calculate_correlation_matrix(
        self,
        returns_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix from returns DataFrame.

        Args:
            returns_df: DataFrame with dates as index, symbols as columns

        Returns:
            Correlation matrix DataFrame
        """
        if returns_df.empty or len(returns_df.columns) < 2:
            return pd.DataFrame()

        df = returns_df.dropna(axis=1, how='all').dropna(axis=0, how='all')

        if len(df.columns) < 2:
            return pd.DataFrame()

        corr_matrix = df.corr()
        self._correlation_cache = corr_matrix.values
        self._symbols = list(corr_matrix.columns)

        return corr_matrix

    def get_eigenvalue_metrics(
        self,
        corr_matrix: np.ndarray
    ) -> Tuple[float, float, float]:
        """
        Calculate eigenvalue-based diversification metrics.

        Args:
            corr_matrix: Correlation matrix as numpy array

        Returns:
            Tuple of (diversification_score, market_factor_dominance, avg_correlation)
        """
        try:
            eigenvalues = np.linalg.eigvals(corr_matrix)
            eigenvalues = np.sort(eigenvalues)[::-1]

            total_eigenvalues = np.sum(np.abs(eigenvalues))
            if total_eigenvalues == 0:
                return 1.0, 0.0, 0.5

            market_factor = eigenvalues[0] / total_eigenvalues

            n = len(eigenvalues)
            if n <= 1:
                diversification = 1.0
            else:
                # Diversification: how evenly the variance is spread
                # = 1 - (largest_eigenvalue / n) / n
                # Or equivalently: 1 - (lambda_max - 1) / (n - 1)
                diversification = 1.0 - (eigenvalues[0] - 1.0) / (n - 1) if n > 1 else 1.0

            avg_correlation = np.mean(corr_matrix[np.triu_indices_from(corr_matrix, 1)])

            return max(0.0, diversification), market_factor, avg_correlation

        except Exception:
            np.fill_diagonal(corr_matrix, 1.0)
            return 1.0, 0.0, 0.5

    def calculate_beta_to_benchmark(
        self,
        portfolio_returns: np.ndarray,
        benchmark_returns: np.ndarray
    ) -> float:
        """
        Calculate portfolio beta to a benchmark.

        Beta = Cov(portfolio, benchmark) / Var(benchmark)

        Args:
            portfolio_returns: Array of portfolio returns
            benchmark_returns: Array of benchmark returns

        Returns:
            Beta coefficient
        """
        if len(portfolio_returns) < 20 or len(benchmark_returns) < 20:
            return 1.0

        min_len = min(len(portfolio_returns), len(benchmark_returns))
        portfolio_returns = portfolio_returns[-min_len:]
        benchmark_returns = benchmark_returns[-min_len:]

        covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
        variance = np.var(benchmark_returns, ddof=1)

        if variance == 0:
            return 1.0

        return covariance / variance

    def calculate_weighted_beta(
        self,
        position_betas: Dict[str, float],
        position_weights: Dict[str, float]
    ) -> float:
        """
        Calculate portfolio beta as weighted average of individual betas.

        Args:
            position_betas: Dict mapping symbol to individual beta
            position_weights: Dict mapping symbol to portfolio weight

        Returns:
            Portfolio beta
        """
        if not position_betas or not position_weights:
            return 1.0

        total_weight = sum(position_weights.values())
        if total_weight == 0:
            return 1.0

        weighted_beta = 0.0
        for symbol, beta in position_betas.items():
            weight = position_weights.get(symbol, 0)
            weighted_beta += beta * weight

        return weighted_beta / total_weight

    def calculate_metrics(
        self,
        returns_df: pd.DataFrame
    ) -> CorrelationMetrics:
        """
        Calculate all correlation and diversification metrics.

        Args:
            returns_df: DataFrame with dates as index, symbols as columns

        Returns:
            CorrelationMetrics object
        """
        corr_matrix_df = self.calculate_correlation_matrix(returns_df)

        if corr_matrix_df.empty:
            return CorrelationMetrics()

        corr_matrix = corr_matrix_df.values

        diversification, market_factor, avg_corr = self.get_eigenvalue_metrics(
            corr_matrix
        )

        return CorrelationMetrics(
            correlation_matrix=corr_matrix_df,
            diversification_score=max(0, diversification),
            market_factor_dominance=market_factor,
            avg_correlation=avg_corr if not np.isnan(avg_corr) else 0.5
        )