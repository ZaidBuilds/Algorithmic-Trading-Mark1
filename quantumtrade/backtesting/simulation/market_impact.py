"""
Market impact models — Almgren-Chriss optimal execution framework.

Market impact is the permanent or temporary price change caused by trading.
Two components:
- Permanent impact: persistent price shift after trade
- Temporary impact: temporary price movement that reverts

Almgren-Chriss model solves for optimal trading schedule to minimize:
  Total Cost = Impact Cost + Risk Cost
  where Risk Cost = variance penalty from holding position over time

Closed-form solution yields hyperbolic cosine trading acceleration:
  q(t) ∝ sinh(λt)  — front-loaded for risk-averse traders
"""

from typing import Optional, Dict, Tuple
import numpy as np
from scipy.optimize import minimize_scalar

from quantumtrade.adapters.execution.models import OrderSide


class AlmgrenChrissImpact:
    """
    Almgren-Chriss (2000) optimal execution model.

    Minimizes total expected cost of liquidating Q shares over T days:
      Cost = ½ ∫₀ᵀ (η q(t)² + λ σ² (Q - Q(t))²) dt

    Closed-form optimal trajectory:
      q(t) = (Q/2) * (1 - cosh(κ (T-t)) / cosh(κ T))
      where κ = sqrt(λ η / σ²)

    For practical purposes, we use the approximate permanent + temporary
    impact formulas:
      Permanent impact (bps) = η * (Q / ADV) * 10000
      Temporary impact (bps) = ε * sqrt(Q / ADV) * 10000

    The model can also generate an optimal execution schedule.
    """

    def __init__(
        self,
        eta: float = 0.01,
        epsilon: float = 0.05,
        lambda_risk: float = 0.001,
        daily_volatility: float = 0.02,
    ):
        """
        Initialize Almgren-Chriss model parameters.

        Args:
            eta: Permanent impact coefficient (linear in participation)
                 Typical: 0.001–0.01 for equities
            epsilon: Temporary impact coefficient (sqrt in participation)
                 Typical: 0.01–0.1
            lambda_risk: Risk aversion parameter (λ)
                 Higher λ → trade faster to reduce risk
                 Typical: 1e-6 to 1e-2 depending on horizon
            daily_volatility: Daily price volatility (σ)
                 Usually 1-3% for liquid stocks
        """
        self.eta = eta
        self.epsilon = epsilon
        self.lambda_risk = lambda_risk
        self.sigma = daily_volatility

    def calculate_impact(
        self,
        order_quantity: float,
        avg_daily_volume: float,
        price: float,
        side: OrderSide,
    ) -> Dict[str, float]:
        """
        Calculate permanent and temporary market impact.

        Args:
            order_quantity: Number of shares to trade
            avg_daily_volume: Average daily volume (ADV)
            price: Current price (for converting bps → dollars)
            side: Order side (impact direction)

        Returns:
            dict with:
              - 'permanent_bps': Permanent impact in basis points
              - 'temporary_bps': Temporary impact in bps
              - 'total_bps': Combined impact
              - 'permanent_dollars': Permanent impact in $
              - 'temporary_dollars': Temporary impact in $
              - 'total_dollars': Total impact cost in $
        """
        if avg_daily_volume <= 0 or order_quantity <= 0:
            return {
                "permanent_bps": 0.0,
                "temporary_bps": 0.0,
                "total_bps": 0.0,
                "permanent_dollars": 0.0,
                "temporary_dollars": 0.0,
                "total_dollars": 0.0,
            }

        participation = order_quantity / avg_daily_volume

        # Permanent impact: linear in participation
        permanent_bps = self.eta * participation * 10000

        # Temporary impact: sqrt in participation
        temporary_bps = self.epsilon * np.sqrt(participation) * 10000

        total_bps = permanent_bps + temporary_bps

        # Convert to dollar costs
        notional = order_quantity * price
        permanent_dollars = notional * (permanent_bps / 10000)
        temporary_dollars = notional * (temporary_bps / 10000)
        total_dollars = permanent_dollars + temporary_dollars

        return {
            "permanent_bps": permanent_bps,
            "temporary_bps": temporary_bps,
            "total_bps": total_bps,
            "permanent_dollars": permanent_dollars,
            "temporary_dollars": temporary_dollars,
            "total_dollars": total_dollars,
        }

    def calculate_impact_components(
        self,
        order_quantity: float,
        avg_daily_volume: float,
    ) -> Dict[str, float]:
        """
        Return permanent and temporary impact components (bps only).

        Convenience wrapper that calls calculate_impact with neutral side.
        """
        result = self.calculate_impact(
            order_quantity=order_quantity,
            avg_daily_volume=avg_daily_volume,
            price=100.0,  # dummy price; bps independent
            side=OrderSide.BUY,
        )
        return {
            "permanent_bps": result["permanent_bps"],
            "temporary_bps": result["temporary_bps"],
            "total_bps": result["total_bps"],
        }

    def calculate_optimal_execution_trajectory(
        self,
        total_quantity: float,
        time_horizon_days: float,
        num_periods: int = 100,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute optimal liquidation schedule using closed-form solution.

        The optimal trading trajectory for complete liquidation (Almgren-Chriss) is:

          Shares remaining at time t:  x(t) = Q * sinh(κ(T-t)) / sinh(κT)
          Trading rate (shares per time): μ(t) = Qκ * cosh(κ(T-t)) / sinh(κT)

        where κ = sqrt(λ η) / σ

        Args:
            total_quantity: Total shares to liquidate (Q)
            time_horizon_days: Total execution horizon T in days
            num_periods: Number of discrete time steps to return

        Returns:
            (times, quantities): Arrays of times (0 to T) and optimal q(t)
        """
        if total_quantity <= 0 or time_horizon_days <= 0:
            return np.array([]), np.array([])

        # Compute κ (kappa)
        if self.sigma <= 0 or self.lambda_risk <= 0:
            # If risk aversion is 0, trade immediately (all at t=0)
            return np.array([0.0]), np.array([total_quantity])

        kappa = np.sqrt(self.lambda_risk * self.eta) / self.sigma

        # Time grid
        times = np.linspace(0, time_horizon_days, num_periods)
        T = time_horizon_days

        with np.errstate(over='ignore', invalid='ignore'):
            sinh_total = np.sinh(kappa * T)
            if sinh_total == 0 or np.isinf(sinh_total) or np.isnan(sinh_total):
                quantities = np.zeros_like(times)
                quantities[0] = total_quantity
                return times, quantities

            # Shares remaining at each time t: x(t) = Q * sinh(κ(T-t)) / sinh(κT)
            remaining = total_quantity * np.sinh(kappa * (T - times)) / sinh_total

            # Shares sold by time t: Q - x(t)
            sold = total_quantity - remaining

            # Trading rate per discrete interval
            quantities = np.diff(np.concatenate([[0], sold]))

        # Sanity: sum(quantities) should equal total_quantity (within tolerance)
        if not np.isclose(np.sum(quantities), total_quantity, rtol=1e-3):
            quantities = np.full_like(times, total_quantity / num_periods)

        return times, quantities

    def calculate_optimal_horizon(
        self,
        order_quantity: float,
        avg_daily_volume: float,
        risk_aversion: Optional[float] = None,
    ) -> float:
        """
        Estimate optimal execution horizon (T*) for a given order.

        Heuristic: larger orders → longer horizon.
        T* ∝ sqrt(Q / ADV) for typical parameters.

        Args:
            order_quantity: Order size (Q)
            avg_daily_volume: Average daily volume (ADV)
            risk_aversion: Override λ (uses model's default if None)

        Returns:
            Optimal horizon in trading days
        """
        if avg_daily_volume <= 0 or order_quantity <= 0:
            return 0.0

        participation = order_quantity / avg_daily_volume

        # Use risk aversion override if provided
        lambda_used = risk_aversion or self.lambda_risk

        if lambda_used <= 0:
            return 0.0  # Immediate execution

        # Simplified closed-form from Almgren-Chriss:
        # Optimal horizon T* = sqrt( (η Q) / (λ σ² ADV) )
        # Or expressed differently:
        try:
            T_star = np.sqrt(
                (self.eta * order_quantity) /
                (lambda_used * self.sigma**2 * avg_daily_volume)
            )
        except (ZeroDivisionError, FloatingPointError):
            T_star = 1.0  # Default 1 day

        # Clamp to reasonable bounds: 0.1 day (1 hour) to 30 days
        T_star = np.clip(T_star, 0.1, 30.0)

        return float(T_star)

    def participation_rate_to_impact(
        self,
        participation_rate: float,
    ) -> Dict[str, float]:
        """
        Convert participation rate (Q/ADV) directly to impact bps.

        Args:
            participation_rate: Order size / ADV (e.g., 0.1 = 10% of ADV)

        Returns:
            dict with permanent, temporary, total bps and dollar impacts
            (assuming price=100 for dollar conversion)
        """
        if participation_rate <= 0:
            return {
                "permanent_bps": 0.0,
                "temporary_bps": 0.0,
                "total_bps": 0.0,
                "permanent_dollars": 0.0,
                "temporary_dollars": 0.0,
                "total_dollars": 0.0,
            }

        permanent_bps = self.eta * participation_rate * 10000
        temporary_bps = self.epsilon * np.sqrt(participation_rate) * 10000
        total_bps = permanent_bps + temporary_bps

        # Dollar impact at $100 reference price, 100 shares = $10,000 notional
        reference_notional = 10000.0
        permanent_dollars = reference_notional * (permanent_bps / 10000)
        temporary_dollars = reference_notional * (temporary_bps / 10000)
        total_dollars = permanent_dollars + temporary_dollars

        return {
            "permanent_bps": permanent_bps,
            "temporary_bps": temporary_bps,
            "total_bps": total_bps,
            "permanent_dollars": permanent_dollars,
            "temporary_dollars": temporary_dollars,
            "total_dollars": total_dollars,
        }


class ImpactCalibrator:
    """
    Calibrate impact model parameters from historical data.

    Uses regression of realized impact on order characteristics.
    """

    @staticmethod
    def calibrate_from_executions(
        order_quantities: np.ndarray,
        adv_values: np.ndarray,
        impact_bps: np.ndarray,
    ) -> Dict[str, float]:
        """
        Estimate eta and epsilon from historical trade data.

        Linear regression:
          impact_bps = (eta * (Q/ADV) + epsilon * sqrt(Q/ADV)) * 10000

        We solve for (eta, epsilon) via non-linear least squares.

        Args:
            order_quantities: Array of order sizes (Q)
            adv_values: Array of ADV for each trade
            impact_bps: Realized impact in bps

        Returns:
            dict with 'eta' and 'epsilon' estimates
        """
        if len(order_quantities) != len(adv_values) or len(order_quantities) != len(impact_bps):
            raise ValueError("Arrays must have same length")

        participation = order_quantities / adv_values
        sqrt_participation = np.sqrt(participation)

        # Design matrix: [participation, sqrt_participation]
        X = np.column_stack([participation, sqrt_participation])
        y = impact_bps

        # Solve via least squares: y = X * [eta*10000, epsilon*10000]
        try:
            coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            eta_est = coeffs[0] / 10000
            epsilon_est = coeffs[1] / 10000
        except Exception:
            eta_est = 0.01
            epsilon_est = 0.05

        return {
            "eta": float(eta_est),
            "epsilon": float(epsilon_est),
        }
