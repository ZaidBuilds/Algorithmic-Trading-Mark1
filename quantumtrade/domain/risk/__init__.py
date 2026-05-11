"""
Portfolio Risk Management Package.

Exports the core risk engine and models for calculating and managing
portfolio-level risk metrics in real-time.
"""

from .models import (
    Position,
    Portfolio,
    Exposure,
    RiskLimits,
    RiskBreach,
    StressScenario,
    PortfolioVaR,
    CorrelationMetrics,
    DrawdownMetrics,
    RiskReport,
    SizingDecision,
)
from .portfolio_risk import PortfolioRiskEngine
from .var import VaRCalculator
from .exposure import ExposureCalculator
from .correlation import CorrelationAnalyzer
from .stress import StressTester
from .limits import RiskLimitChecker
from .position_sizer import PositionSizer, SizingStrategyConfig
from .risk_manager import RiskManager  # newly added

__all__ = [
    # Models
    "Position",
    "Portfolio",
    "Exposure",
    "RiskLimits",
    "RiskBreach",
    "StressScenario",
    "PortfolioVaR",
    "CorrelationMetrics",
    "DrawdownMetrics",
    "RiskReport",
    "SizingDecision",
    # Engines
    "PortfolioRiskEngine",
    "VaRCalculator",
    "ExposureCalculator",
    "CorrelationAnalyzer",
    "StressTester",
    "RiskLimitChecker",
    # Position Sizing
    "PositionSizer",
    "SizingStrategyConfig",
    # Risk Manager with TCA integration
    "RiskManager",
]
