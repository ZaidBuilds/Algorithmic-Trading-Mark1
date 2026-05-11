"""
Domain models for portfolio risk management.

This module contains dataclasses for positions, portfolios, risk limits,
and risk reports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class Position:
    """Represents a single position in the portfolio."""
    symbol: str
    quantity: float
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    market_value: float = 0.0
    sector: Optional[str] = None
    asset_class: Optional[str] = None

    def __post_init__(self):
        """Recalculate derived fields after initialization."""
        self.market_value = self.quantity * self.current_price
        self.unrealized_pnl = self.market_value - (self.quantity * self.avg_entry_price)

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate derived fields."""
        self.current_price = new_price
        self.market_value = self.quantity * new_price
        self.unrealized_pnl = self.market_value - (self.quantity * self.avg_entry_price)

    @property
    def pnl_pct(self) -> float:
        cost_basis = self.quantity * self.avg_entry_price
        if cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / cost_basis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_entry_price": self.avg_entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "market_value": self.market_value,
            "sector": self.sector,
            "asset_class": self.asset_class,
        }


@dataclass
class Portfolio:
    """Represents a portfolio with positions."""
    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_value(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def long_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.quantity > 0]

    @property
    def short_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.quantity < 0]

    @property
    def long_value(self) -> float:
        return sum(p.market_value for p in self.long_positions)

    @property
    def short_value(self) -> float:
        return sum(abs(p.market_value) for p in self.short_positions)

    @property
    def gross_exposure(self) -> float:
        return self.long_value + self.short_value

    @property
    def net_exposure(self) -> float:
        return self.long_value + self.short_value

    @property
    def gross_exposure_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return self.gross_exposure / self.total_value

    @property
    def net_exposure_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return self.net_exposure / self.total_value

    @property
    def position_count(self) -> int:
        return len(self.positions)

    def get_top_positions(self, n: int = 5) -> List[Position]:
        sorted_positions = sorted(
            self.positions.values(),
            key=lambda p: abs(p.market_value),
            reverse=True
        )
        return sorted_positions[:n]

    def get_concentration_ratio(self, top_n: int = 5) -> float:
        if not self.positions or self.total_value == 0:
            return 0.0
        top_positions = self.get_top_positions(top_n)
        return sum(abs(p.market_value) for p in top_positions) / self.total_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash": self.cash,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "total_value": self.total_value,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Exposure:
    """Represents exposure metrics for the portfolio."""
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    gross_exposure_pct: float = 0.0
    net_exposure_pct: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
            "gross_exposure_pct": self.gross_exposure_pct,
            "net_exposure_pct": self.net_exposure_pct,
        }


@dataclass
class RiskLimits:
    """Risk limits configuration for portfolio-level constraints."""
    max_position_pct: float = 0.10
    max_sector_exposure_pct: float = 0.30
    max_gross_exposure_pct: float = 1.5
    max_net_exposure_pct: float = 1.0
    var_95_limit_usd: Optional[float] = None
    var_99_limit_usd: Optional[float] = None
    max_drawdown_pct: float = 0.20
    max_daily_loss_pct: float = 0.05
    max_positions: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_position_pct": self.max_position_pct,
            "max_sector_exposure_pct": self.max_sector_exposure_pct,
            "max_gross_exposure_pct": self.max_gross_exposure_pct,
            "max_net_exposure_pct": self.max_net_exposure_pct,
            "var_95_limit_usd": self.var_95_limit_usd,
            "var_99_limit_usd": self.var_99_limit_usd,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_positions": self.max_positions,
        }


@dataclass
class RiskBreach:
    """Represents a risk limit breach."""
    limit_type: str
    current_value: float
    limit_value: float
    message: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "limit_type": self.limit_type,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class StressScenario:
    """Configuration for a stress test scenario."""
    name: str
    description: str
    shocks: Dict[str, float]  # symbol/sector -> price shock percentage
    correlation_shock: float = 0.0  # Additional correlation in crisis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "shocks": self.shocks,
            "correlation_shock": self.correlation_shock,
        }


@dataclass
class PortfolioVaR:
    """Value at Risk metrics."""
    var_95: float = 0.0
    var_99: float = 0.0
    expected_shortfall_95: float = 0.0
    expected_shortfall_99: float = 0.0
    confidence_level: float = 0.95
    time_horizon_days: int = 1

    def to_dict(self) -> Dict[str, float]:
        return {
            "var_95": self.var_95,
            "var_99": self.var_99,
            "expected_shortfall_95": self.expected_shortfall_95,
            "expected_shortfall_99": self.expected_shortfall_99,
            "confidence_level": self.confidence_level,
            "time_horizon_days": self.time_horizon_days,
        }


@dataclass
class CorrelationMetrics:
    """Correlation matrix and diversification metrics."""
    correlation_matrix: Optional[Any] = None
    diversification_score: float = 1.0
    market_factor_dominance: float = 0.0
    avg_correlation: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diversification_score": self.diversification_score,
            "market_factor_dominance": self.market_factor_dominance,
            "avg_correlation": self.avg_correlation,
        }


@dataclass
class DrawdownMetrics:
    """Drawdown metrics for the portfolio."""
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    days_underwater: int = 0
    peak_value: float = 0.0
    current_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "days_underwater": self.days_underwater,
            "peak_value": self.peak_value,
            "current_value": self.current_value,
        }


@dataclass
class SizingDecision:
    """Represents a position sizing decision with metadata."""
    quantity: int
    sizing_model: str
    risk_amount_usd: float
    risk_pct: float
    stop_distance_pct: float
    reason: str = ""
    kelly_fraction: Optional[float] = None
    volatility_adjustment: Optional[float] = None
    confidence_factor: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity": self.quantity,
            "sizing_model": self.sizing_model,
            "risk_amount_usd": self.risk_amount_usd,
            "risk_pct": self.risk_pct,
            "stop_distance_pct": self.stop_distance_pct,
            "reason": self.reason,
            "kelly_fraction": self.kelly_fraction,
            "volatility_adjustment": self.volatility_adjustment,
            "confidence_factor": self.confidence_factor,
        }


@dataclass
class RiskReport:
    """Comprehensive risk report for the portfolio."""
    timestamp: datetime
    portfolio_value: float
    cash: float
    total_exposure: Exposure
    position_count: int
    concentration_top5_pct: float
    var: PortfolioVaR
    correlation: CorrelationMetrics
    drawdown: DrawdownMetrics
    sector_exposure: Dict[str, float]
    beta_to_benchmark: float
    stress_test_results: Dict[str, Dict[str, float]]
    breaches: List[RiskBreach]
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "portfolio_value": self.portfolio_value,
            "cash": self.cash,
            "exposure": self.total_exposure.to_dict(),
            "position_count": self.position_count,
            "concentration_top5_pct": self.concentration_top5_pct,
            "var": self.var.to_dict(),
            "correlation": self.correlation.to_dict(),
            "drawdown": self.drawdown.to_dict(),
            "sector_exposure": self.sector_exposure,
            "beta_to_benchmark": self.beta_to_benchmark,
            "stress_test_results": self.stress_test_results,
            "breaches": [b.to_dict() for b in self.breaches],
            "errors": self.errors,
        }


@dataclass
class ExitSignal:
    """Signal indicating a position should be exited."""
    should_exit: bool
    exit_type: str  # "stop_loss" | "take_profit" | "trailing" | "time" | "signal" | "partial"
    quantity: float
    price: float
    reason: str
    metadata: Dict
    urgency: str  # "immediate" | "market_close" | "next_tick"
