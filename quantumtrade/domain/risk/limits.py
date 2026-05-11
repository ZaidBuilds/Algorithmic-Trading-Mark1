"""
Risk limit checking and breach detection.

Validates portfolio against configured risk limits.
"""

from typing import List, Dict, Optional
from .models import (
    RiskLimits,
    RiskBreach,
    Exposure,
    PortfolioVaR,
    Position,
)


class RiskLimitChecker:
    """
    Check portfolio against risk limits and detect breaches.
    """

    def check_all_limits(
        self,
        positions: List[Position],
        exposure: Exposure,
        portfolio_value: float,
        var: PortfolioVaR,
        limits: RiskLimits,
        sector_exposure: Optional[Dict[str, float]] = None
    ) -> List[RiskBreach]:
        """
        Check all risk limits and return list of breaches.

        Args:
            positions: List of Position objects
            exposure: Exposure metrics
            portfolio_value: Total portfolio value
            var: VaR metrics
            limits: RiskLimits configuration
            sector_exposure: Optional sector exposure dict

        Returns:
            List of RiskBreach objects
        """
        breaches = []

        position_breaches = self._check_position_limits(
            positions, portfolio_value, limits.max_position_pct
        )
        breaches.extend(position_breaches)

        sector_breaches = self._check_sector_limits(
            sector_exposure or {}, limits.max_sector_exposure_pct
        )
        breaches.extend(sector_breaches)

        breach = self._check_gross_exposure_limit(exposure, limits)
        if breach:
            breaches.append(breach)

        breach = self._check_net_exposure_limit(exposure, limits)
        if breach:
            breaches.append(breach)

        breach = self._check_var_limit(var, limits)
        if breach:
            breaches.append(breach)

        return breaches

    def _check_position_limits(
        self,
        positions: List[Position],
        portfolio_value: float,
        max_pct: float
    ) -> List[RiskBreach]:
        """Check individual position size limits."""
        breaches = []

        if portfolio_value == 0:
            return breaches

        for pos in positions:
            position_pct = abs(pos.market_value) / portfolio_value
            if position_pct > max_pct:
                breaches.append(RiskBreach(
                    limit_type="position_size",
                    current_value=position_pct,
                    limit_value=max_pct,
                    message=f"{pos.symbol} exceeds position limit: {position_pct:.1%} > {max_pct:.1%}"
                ))

        return breaches

    def _check_sector_limits(
        self,
        sector_exposure: Dict[str, float],
        max_pct: float
    ) -> List[RiskBreach]:
        """Check sector exposure limits."""
        breaches = []

        for sector, exposure_pct in sector_exposure.items():
            if exposure_pct > max_pct:
                breaches.append(RiskBreach(
                    limit_type="sector_exposure",
                    current_value=exposure_pct,
                    limit_value=max_pct,
                    message=f"{sector} sector exceeds limit: {exposure_pct:.1%} > {max_pct:.1%}"
                ))

        return breaches

    def _check_gross_exposure_limit(
        self,
        exposure: Exposure,
        limits: RiskLimits
    ) -> Optional[RiskBreach]:
        """Check gross exposure limit."""
        if exposure.gross_exposure_pct > limits.max_gross_exposure_pct:
            return RiskBreach(
                limit_type="gross_exposure",
                current_value=exposure.gross_exposure_pct,
                limit_value=limits.max_gross_exposure_pct,
                message=f"Gross exposure exceeds limit: {exposure.gross_exposure_pct:.1%} > {limits.max_gross_exposure_pct:.1%}"
            )
        return None

    def _check_net_exposure_limit(
        self,
        exposure: Exposure,
        limits: RiskLimits
    ) -> Optional[RiskBreach]:
        """Check net exposure limit."""
        if abs(exposure.net_exposure_pct) > limits.max_net_exposure_pct:
            return RiskBreach(
                limit_type="net_exposure",
                current_value=abs(exposure.net_exposure_pct),
                limit_value=limits.max_net_exposure_pct,
                message=f"Net exposure exceeds limit: {exposure.net_exposure_pct:.1%} > {limits.max_net_exposure_pct:.1%}"
            )
        return None

    def _check_var_limit(
        self,
        var: PortfolioVaR,
        limits: RiskLimits
    ) -> Optional[RiskBreach]:
        """Check VaR limit if configured."""
        if limits.var_95_limit_usd is None:
            return None

        if var.var_95 > limits.var_95_limit_usd:
            return RiskBreach(
                limit_type="var",
                current_value=var.var_95,
                limit_value=limits.var_95_limit_usd,
                message=f"VaR 95 exceeds limit: ${var.var_95:,.0f} > ${limits.var_95_limit_usd:,.0f}"
            )
        return None

    def is_trading_allowed(self, breaches: List[RiskBreach]) -> bool:
        """Check if trading should be allowed given current breaches."""
        return len(breaches) == 0

    def get_breach_summary(self, breaches: List[RiskBreach]) -> Dict[str, int]:
        """Get summary of breaches by type."""
        summary: Dict[str, int] = {}
        for breach in breaches:
            summary[breach.limit_type] = summary.get(breach.limit_type, 0) + 1
        return summary