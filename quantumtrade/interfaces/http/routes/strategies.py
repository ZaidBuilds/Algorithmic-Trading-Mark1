"""Strategy and backtest routes for QuantumTrade API."""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import Depends, HTTPException, APIRouter
from pydantic import BaseModel, Field

from strategy import STRATEGY_REGISTRY, get_strategy, list_strategies
from quantumtrade.backtesting.engine import BacktestEngine
from quantumtrade.backtesting.monte_carlo import MonteCarloRobustnessTester
from quantumtrade.interfaces.http.auth import JWTAuth

jwt_auth = JWTAuth()
router = APIRouter()


def _get_strategy_params(name: str) -> Dict[str, Any]:
    """Extract parameter schema from strategy class __init__."""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}")

    cls = STRATEGY_REGISTRY[name]
    sig = inspect.signature(cls.__init__)
    params = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        params[param_name] = {
            "type": "integer" if param.annotation in (int, "int") else
                    "number" if param.annotation in (float, "float") else
                    "string",
            "default": param.default if param.default is not inspect.Parameter.empty else None,
            "required": param.default is inspect.Parameter.empty,
        }
    return params


class StrategyInfo(BaseModel):
    """Response model for strategy listing."""
    name: str
    parameters: Dict[str, Any]


class StrategyDetail(BaseModel):
    """Response model for single strategy details."""
    name: str
    parameters: Dict[str, Any]
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]


class BacktestRequest(BaseModel):
    """Request model for backtest endpoint."""
    symbol: str = Field(..., description="Trading symbol")
    strategy_name: str = Field(..., description="Name of strategy to run")
    strategy_params: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    initial_balance: float = Field(default=10000.0, description="Starting capital")
    data: List[Dict[str, Any]] = Field(..., description="OHLCV data rows")


class BacktestResult(BaseModel):
    """Response model for backtest result."""
    symbol: str
    strategy_name: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    final_balance: float


class MonteCarloRequest(BaseModel):
    """Request model for Monte Carlo endpoint."""
    strategy_name: str = Field(..., description="Name of strategy to test")
    strategy_params: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    data: List[Dict[str, Any]] = Field(..., description="OHLCV data rows")
    n_simulations: int = Field(default=10000, ge=1000, le=100000, description="Number of simulations")
    bootstrap_method: str = Field(default="iid", description="Bootstrap method: iid, block, or randomize")
    block_size: int = Field(default=10, description="Block size for block bootstrap")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


def _prepare_dataframe(data: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert list of dicts to properly indexed DataFrame."""
    df = pd.DataFrame(data)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")
        df = df.dropna(subset=["time"]).set_index("time")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).set_index("timestamp")
    else:
        raise ValueError("data rows must include 'time' (unix seconds) or 'timestamp'")

    column_mapping = {
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"
    }
    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
    return df


@router.get("/api/strategies", response_model=List[StrategyInfo], dependencies=[Depends(jwt_auth.require_jwt)])
def list_strategies_endpoint():
    """List all available strategies with their parameter schemas."""
    strategies = []
    for name in list_strategies():
        strategies.append(StrategyInfo(
            name=name,
            parameters=_get_strategy_params(name)
        ))
    return strategies


@router.get("/api/strategies/{name}", response_model=StrategyDetail, dependencies=[Depends(jwt_auth.require_jwt)])
def get_strategy_endpoint(name: str):
    """Get details for a specific strategy."""
    if name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    strategy = STRATEGY_REGISTRY[name](**{})
    return StrategyDetail(
        name=name,
        parameters=_get_strategy_params(name),
        entry_rules=strategy.get_entry_rules(),
        exit_rules=strategy.get_exit_rules(),
    )


@router.post("/api/backtest", response_model=BacktestResult, dependencies=[Depends(jwt_auth.require_jwt)])
def run_backtest(request: BacktestRequest):
    """Run a single backtest with strategy parameters."""
    if request.strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{request.strategy_name}' not found")

    df = _prepare_dataframe(request.data)
    strategy = get_strategy(request.strategy_name, **request.strategy_params)

    engine = BacktestEngine(
        initial_balance=request.initial_balance,
        commission=0.001,
    )
    metrics = engine.run(strategy=strategy, data=df)

    summary = metrics.get_summary()
    return BacktestResult(
        symbol=request.symbol,
        strategy_name=request.strategy_name,
        total_return_pct=summary.get("total_return", {}).get("percent", 0.0),
        sharpe_ratio=summary.get("sharpe_ratio", 0.0),
        max_drawdown_pct=summary.get("max_drawdown", {}).get("percent", 0.0),
        total_trades=len(metrics.trades),
        win_rate=summary.get("win_rate", {}).get("win_rate", 0.0),
        final_balance=metrics.current_balance,
    )


@router.post("/api/monte-carlo", dependencies=[Depends(jwt_auth.require_jwt)])
def run_monte_carlo(request: MonteCarloRequest):
    """Run Monte Carlo robustness test on backtest results."""
    if request.strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy '{request.strategy_name}' not found")

    df = _prepare_dataframe(request.data)

    def strategy_factory(params: Dict[str, Any]):
        return get_strategy(request.strategy_name, **params)

    tester = MonteCarloRobustnessTester(
        strategy_factory=strategy_factory,
        n_simulations=request.n_simulations,
        seed=request.seed,
    )

    engine = BacktestEngine(initial_balance=10000.0)
    results = tester.run_from_backtest(
        data=df,
        strategy_params=request.strategy_params,
        engine=engine,
        bootstrap_method=request.bootstrap_method,
        block_size=request.block_size,
    )

    return results