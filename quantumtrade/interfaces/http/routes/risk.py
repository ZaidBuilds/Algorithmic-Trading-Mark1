"""Risk management routes for QuantumTrade API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, APIRouter
from pydantic import BaseModel, Field

from quantumtrade.domain.risk.position_sizer import PositionSizer
from quantumtrade.domain.risk.portfolio_risk import PortfolioRiskEngine
from quantumtrade.domain.risk.models import Position
from quantumtrade.interfaces.http.auth import JWTAuth

jwt_auth = JWTAuth()
router = APIRouter()


class PositionSizeRequest(BaseModel):
    """Request model for position size calculation."""
    symbol: str = Field(..., description="Trading symbol")
    entry_price: float = Field(..., gt=0, description="Proposed entry price")
    stop_loss_price: float = Field(..., description="Stop loss price")
    portfolio_value: float = Field(..., gt=0, description="Total portfolio value")
    risk_per_trade_pct: float = Field(default=0.02, gt=0, le=1, description="Risk per trade as fraction")
    strategy: str = Field(default="fixed_fractional", description="Sizing strategy")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Strategy confidence (0-1)")
    volatility: Optional[float] = Field(None, description="Annualized volatility")
    win_rate: Optional[float] = Field(None, ge=0, le=1, description="Historical win rate")
    avg_win_loss_ratio: Optional[float] = Field(None, gt=0, description="Payoff ratio")
    strategy_weights: Optional[Dict[str, float]] = Field(None, description="Weights for composite strategy")


class PositionSizeResponse(BaseModel):
    """Response model for position size calculation."""
    quantity: int
    sizing_model: str
    risk_amount_usd: float
    risk_pct: float
    stop_distance_pct: float
    reason: str
    kelly_fraction: Optional[float] = None
    volatility_adjustment: Optional[float] = None
    confidence_factor: Optional[float] = None


class VarRequest(BaseModel):
    """Request model for VaR calculation."""
    portfolio_value: float = Field(..., gt=0, description="Total portfolio value")
    positions: List[Dict[str, Any]] = Field(default_factory=list, description="Current positions")
    lookback_days: int = Field(default=250, ge=30, description="Historical lookback period")


class VarResponse(BaseModel):
    """Response model for VaR calculation."""
    var_95: float
    var_99: float
    expected_shortfall_95: float
    expected_shortfall_99: float
    portfolio_value: float
    exposure_pct: float
    beta_to_benchmark: float
    breaches: List[Dict[str, Any]]


@router.post("/api/position-size", response_model=PositionSizeResponse, dependencies=[Depends(jwt_auth.require_jwt)])
def calculate_position_size(request: PositionSizeRequest):
    """Calculate position size using PositionSizer."""
    sizer = PositionSizer(
        portfolio_value=request.portfolio_value,
        risk_per_trade_pct=request.risk_per_trade_pct,
        strategy=request.strategy,
    )

    quantity, metadata = sizer.calculate_position_size(
        symbol=request.symbol,
        entry_price=request.entry_price,
        stop_loss_price=request.stop_loss_price,
        confidence=request.confidence,
        volatility=request.volatility,
        win_rate=request.win_rate,
        avg_win_loss_ratio=request.avg_win_loss_ratio,
        strategy_weights=request.strategy_weights,
    )

    return PositionSizeResponse(
        quantity=quantity,
        sizing_model=metadata.get("sizing_model", request.strategy),
        risk_amount_usd=metadata.get("risk_amount_usd", 0.0),
        risk_pct=metadata.get("risk_pct", 0.0),
        stop_distance_pct=metadata.get("stop_distance_pct", 0.0),
        reason=metadata.get("reason", ""),
        kelly_fraction=metadata.get("kelly_fraction"),
        volatility_adjustment=metadata.get("volatility_adjustment"),
        confidence_factor=metadata.get("confidence_factor"),
    )


@router.post("/api/var", response_model=VarResponse, dependencies=[Depends(jwt_auth.require_jwt)])
def calculate_var(request: VarRequest):
    """Calculate VaR and risk metrics using PortfolioRiskEngine."""
    positions = []
    for pos_data in request.positions:
        positions.append(Position(
            symbol=pos_data.get("symbol", ""),
            quantity=pos_data.get("quantity", 0.0),
            avg_entry_price=pos_data.get("avg_entry_price", 0.0),
            current_price=pos_data.get("current_price", 0.0),
            sector=pos_data.get("sector"),
            asset_class=pos_data.get("asset_class"),
        ))

    engine = PortfolioRiskEngine(
        broker=None,
        data_client=None,
        lookback_days=request.lookback_days,
    )

    report = engine.calculate_risk_metrics()

    return VarResponse(
        var_95=report.var.var_95,
        var_99=report.var.var_99,
        expected_shortfall_95=report.var.expected_shortfall_95,
        expected_shortfall_99=report.var.expected_shortfall_99,
        portfolio_value=report.portfolio_value,
        exposure_pct=report.total_exposure.gross_exposure_pct,
        beta_to_benchmark=report.beta_to_benchmark,
        breaches=[b.to_dict() for b in report.breaches],
    )