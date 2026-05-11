"""
Exposure tracking for portfolio positions.

Calculates gross/net exposure, sector exposure, and concentration metrics.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from .models import Exposure, Position, Portfolio


def calculate_gross_exposure(portfolio: Portfolio) -> float:
    """Calculate gross exposure (long + short) for a portfolio."""
    return portfolio.gross_exposure


def calculate_net_exposure(portfolio: Portfolio) -> float:
    """Calculate net exposure (long - short) for a portfolio."""
    return portfolio.net_exposure


def calculate_gross_exposure_pct(portfolio: Portfolio) -> float:
    """Calculate gross exposure as percentage of portfolio value."""
    return portfolio.gross_exposure_pct


def calculate_net_exposure_pct(portfolio: Portfolio) -> float:
    """Calculate net exposure as percentage of portfolio value."""
    return portfolio.net_exposure_pct


def get_symbol_exposure(portfolio: Portfolio) -> Dict[str, float]:
    """Get exposure by symbol as percentage of portfolio value."""
    total_value = portfolio.total_value
    if total_value == 0:
        return {}
    return {symbol: abs(pos.market_value) / total_value for symbol, pos in portfolio.positions.items()}


def get_sector_exposure(portfolio: Portfolio, sector_mapping: Optional[Dict[str, str]] = None) -> Dict[str, float]:
    """Get exposure by sector using optional mapping for missing sectors."""
    total_value = portfolio.total_value
    if total_value == 0:
        return {}

    sector_exposure: Dict[str, float] = {}
    for symbol, pos in portfolio.positions.items():
        sector = pos.sector or (sector_mapping.get(symbol) if sector_mapping else None) or "Unknown"
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + abs(pos.market_value)

    return {s: v / total_value for s, v in sector_exposure.items()}


def get_asset_class_exposure(portfolio: Portfolio) -> Dict[str, float]:
    """Get exposure by asset class as percentage of portfolio value."""
    total_value = portfolio.total_value
    if total_value == 0:
        return {}

    asset_exposure: Dict[str, float] = {}
    for pos in portfolio.positions.values():
        asset_class = pos.asset_class or "Unknown"
        asset_exposure[asset_class] = asset_exposure.get(asset_class, 0.0) + abs(pos.market_value)

    return {a: v / total_value for a, v in asset_exposure.items()}


def calculate_concentration_ratio(portfolio: Portfolio, top_n: int = 5) -> float:
    """Calculate concentration ratio for top N positions."""
    return portfolio.get_concentration_ratio(top_n)


def check_exposure_limits(
    portfolio: Portfolio,
    max_gross_pct: float,
    max_net_pct: float,
    max_sector_pct: float,
    sector_mapping: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """Check exposure limits and return list of breaches."""
    breaches = []

    if portfolio.gross_exposure_pct > max_gross_pct:
        breaches.append({
            "limit_type": "gross_exposure",
            "current_value": portfolio.gross_exposure_pct,
            "limit_value": max_gross_pct,
            "message": f"Gross exposure {portfolio.gross_exposure_pct:.1%} exceeds limit {max_gross_pct:.1%}"
        })

    if abs(portfolio.net_exposure_pct) > max_net_pct:
        breaches.append({
            "limit_type": "net_exposure",
            "current_value": abs(portfolio.net_exposure_pct),
            "limit_value": max_net_pct,
            "message": f"Net exposure {portfolio.net_exposure_pct:.1%} exceeds limit {max_net_pct:.1%}"
        })

    sector_exp = get_sector_exposure(portfolio, sector_mapping)
    for sector, exp_pct in sector_exp.items():
        if exp_pct > max_sector_pct:
            breaches.append({
                "limit_type": "sector_exposure",
                "current_value": exp_pct,
                "limit_value": max_sector_pct,
                "message": f"Sector {sector} exposure {exp_pct:.1%} exceeds limit {max_sector_pct:.1%}"
            })

    return breaches


class ExposureCalculator:
    """
    Calculate portfolio exposure metrics.

    Exposure metrics help understand how leveraged/exposed the portfolio is.
    """

    def calculate_exposure(
        self,
        positions: List[Position],
        portfolio_value: float
    ) -> Exposure:
        """
        Calculate gross and net exposure for the portfolio.

        Args:
            positions: List of Position objects
            portfolio_value: Total portfolio value (including cash)

        Returns:
            Exposure object with all exposure metrics
        """
        exp = Exposure()

        long_value = 0.0
        short_value = 0.0

        for pos in positions:
            if pos.quantity > 0:
                long_value += pos.market_value
            elif pos.quantity < 0:
                short_value += abs(pos.market_value)

        exp.long_exposure = long_value
        exp.short_exposure = short_value
        exp.gross_exposure = long_value + short_value
        exp.net_exposure = long_value - short_value

        if portfolio_value > 0:
            exp.gross_exposure_pct = exp.gross_exposure / portfolio_value
            exp.net_exposure_pct = exp.net_exposure / portfolio_value

        return exp

    def calculate_sector_exposure(
        self,
        positions: List[Position],
        portfolio_value: float
    ) -> Dict[str, float]:
        """
        Calculate exposure by sector.

        Args:
            positions: List of Position objects
            portfolio_value: Total portfolio value

        Returns:
            Dictionary mapping sector to exposure percentage
        """
        sector_exposure: Dict[str, float] = {}

        for pos in positions:
            if pos.sector is None:
                sector = "Unknown"
            else:
                sector = pos.sector

            abs_value = abs(pos.market_value)
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + abs_value

        for sector in sector_exposure:
            sector_exposure[sector] /= portfolio_value if portfolio_value > 0 else 1.0

        return sector_exposure

    def calculate_concentration(
        self,
        positions: List[Position],
        portfolio_value: float
    ) -> float:
        """
        Calculate concentration as percentage of top 5 positions.

        Args:
            positions: List of Position objects
            portfolio_value: Total portfolio value

        Returns:
            Concentration ratio (0-1)
        """
        if not positions or portfolio_value == 0:
            return 0.0

        position_values = [abs(pos.market_value) for pos in positions]
        position_values.sort(reverse=True)

        top_5_total = sum(position_values[:5])
        return top_5_total / portfolio_value

    def calculate_asset_class_exposure(
        self,
        positions: List[Position],
        portfolio_value: float
    ) -> Dict[str, float]:
        """
        Calculate exposure by asset class.

        Args:
            positions: List of Position objects
            portfolio_value: Total portfolio value

        Returns:
            Dictionary mapping asset class to exposure percentage
        """
        asset_exposure: Dict[str, float] = {}

        for pos in positions:
            asset_class = pos.asset_class or "Unknown"
            abs_value = abs(pos.market_value)
            asset_exposure[asset_class] = asset_exposure.get(asset_class, 0.0) + abs_value

        for asset in asset_exposure:
            asset_exposure[asset] /= portfolio_value if portfolio_value > 0 else 1.0

        return asset_exposure

    def get_largest_positions(
        self,
        positions: List[Position],
        n: int = 5
    ) -> List[Position]:
        """
        Get the n largest positions by market value.

        Args:
            positions: List of Position objects
            n: Number of positions to return

        Returns:
            List of n largest positions
        """
        sorted_positions = sorted(
            positions,
            key=lambda p: abs(p.market_value),
            reverse=True
        )
        return sorted_positions[:n]