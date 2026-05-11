"""
Risk Manager — integrates TCA into position sizing for dynamic risk adjustment.

Adjusts position sizes based on historical transaction costs to ensure
execution costs remain within risk budget. Uses TCA reports to adapt
risk_per_trade parameter on a per-symbol basis.
"""

from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field

from .position_sizer import PositionSizer
from .models import SizingDecision
from quantumtrade.adapters.execution.tca import TransactionCostAnalyzer
from quantumtrade.adapters.execution.models import BrokerOrder


@dataclass
class TCAStats:
    """Rolling statistics of execution costs for a symbol."""
    symbol: str
    cost_bps_history: deque = field(default_factory=lambda: deque(maxlen=50))
    avg_cost_bps: float = 0.0
    current_multiplier: float = 1.0  # scales risk_per_trade
    
    def update(self, cost_bps: float):
        """Add a new cost observation and recompute average."""
        self.cost_bps_history.append(cost_bps)
        if self.cost_bps_history:
            self.avg_cost_bps = sum(self.cost_bps_history) / len(self.cost_bps_history)
    
    def get_risk_scaling(self, base_risk_pct: float, cost_threshold_bps: float) -> float:
        """
        Compute risk scaling factor.
        
        If avg_cost_bps exceeds threshold, reduce risk proportionally.
        Minimum scaling is 0.5 to avoid zero positions.
        """
        if self.avg_cost_bps <= 0 or cost_threshold_bps <= 0:
            return 1.0
        if self.avg_cost_bps <= cost_threshold_bps:
            return 1.0
        # Inverse scaling: higher cost → lower risk
        scale = cost_threshold_bps / self.avg_cost_bps
        return max(0.5, min(1.0, scale))


class RiskManager:
    """
    Enterprise risk manager that adapts position sizing using TCA insights.
    
    Maintains rolling TCA history per symbol. When sizing a new position,
    scales the risk budget based on observed execution costs.
    
    This protects the portfolio from hidden costs eroding returns.
    """
    
    def __init__(
        self,
        position_sizer: PositionSizer,
        cost_threshold_bps: float = 50.0,  # e.g., 50bps total cost trigger
        lookback: int = 20,  # number of recent trades to consider
    ):
        """
        Initialize RiskManager.
        
        Args:
            position_sizer: Base position sizer (Fixed Fractional, Kelly, etc.)
            cost_threshold_bps: Threshold above which risk is scaled down
            lookback: Rolling window size for TCA history
        """
        self.position_sizer = position_sizer
        self.cost_threshold_bps = cost_threshold_bps
        self.lookback = lookback
        self.tca_analyzer = TransactionCostAnalyzer(benchmark="arrival")
        
        # Symbol-level TCA stats
        self.symbol_stats: Dict[str, TCAStats] = {}
        
        # Global stats (optional)
        self.global_stats = TCAStats(symbol="GLOBAL")
    
    def record_tca_report(self, report) -> None:
        """
        Record a TCA report for future risk adjustment.
        
        Args:
            report: TransactionCostReport (dict-like or object)
        """
        # Accept either dataclass instance or dict
        if hasattr(report, 'to_dict'):
            report_dict = report.to_dict()
        else:
            report_dict = report
        
        symbol = report_dict.get('symbol', 'UNKNOWN')
        total_cost_bps = report_dict.get('total_cost_bps', 0.0)
        
        stats = self.symbol_stats.get(symbol)
        if stats is None:
            stats = TCAStats(symbol=symbol)
            stats.cost_bps_history = deque(maxlen=self.lookback)
            self.symbol_stats[symbol] = stats
        
        stats.update(total_cost_bps)
        self.global_stats.update(total_cost_bps)
        
        # Update position sizer's risk budget based on this symbol's costs
        self._adjust_risk_parameters(symbol, stats)
    
    def _adjust_risk_parameters(self, symbol: str, stats: TCAStats) -> None:
        """
        Adjust the position sizer's risk_per_trade_pct based on symbol cost.
        
        We modify the PositionSizer's risk_per_trade_pct in place by scaling.
        """
        base_risk = self.position_sizer.risk_per_trade_pct
        scale = stats.get_risk_scaling(base_risk, self.cost_threshold_bps)
        # Apply scaling to the sizer's risk_per_trade_pct temporarily.
        # In a more advanced design, we would have per-symbol risk budgets.
        # Here we update the base globally; could be made per-symbol.
        self.position_sizer.risk_per_trade_pct = base_risk * scale
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        confidence: Optional[float] = None,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_win_loss_ratio: Optional[float] = None,
        current_positions: int = 0,
        strategy_weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Calculate position size using underlying sizer, then apply TCA-based adjustment.
        
        Returns:
            (quantity, metadata)
        """
        # Get base size
        base_qty, base_meta = self.position_sizer.calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            confidence=confidence,
            volatility=volatility,
            win_rate=win_rate,
            avg_win_loss_ratio=avg_win_loss_ratio,
            current_positions=current_positions,
            strategy_weights=strategy_weights,
        )
        
        # Apply TCA-based discount if symbol has high costs
        stats = self.symbol_stats.get(symbol, self.global_stats)
        scale = stats.get_risk_scaling(
            base_risk_pct=self.position_sizer.risk_per_trade_pct,
            cost_threshold_bps=self.cost_threshold_bps,
        )
        
        if scale < 1.0:
            adjusted_qty = max(1, int(base_qty * scale))
            base_meta['reason'] += f" [TCA-adjusted: scale={scale:.2f} due to avg_cost={stats.avg_cost_bps:.1f} bps]"
        else:
            adjusted_qty = base_qty
        
        return adjusted_qty, base_meta
    
    def get_tca_summary(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get TCA summary for a symbol or global."""
        if symbol is not None and symbol in self.symbol_stats:
            stats = self.symbol_stats[symbol]
        else:
            stats = self.global_stats
        
        return {
            "symbol": stats.symbol,
            "avg_cost_bps": stats.avg_cost_bps,
            "samples": len(stats.cost_bps_history),
            "current_multiplier": stats.current_multiplier,
        }
    
    def reset(self) -> None:
        """Clear all TCA history."""
        self.symbol_stats.clear()
        self.global_stats = TCAStats(symbol="GLOBAL")
