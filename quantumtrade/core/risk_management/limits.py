"""
Risk limits module for enforcing trading limits.

Risk limits protect against:
1. Excessive losses in a single day
2. Over-concentration in single positions
3. Overtrading
4. Account blow-ups
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskLimitResult:
    """Result of risk limit check."""
    is_allowed: bool
    reason: str
    current_value: float = 0.0
    limit_value: float = 0.0


class RiskLimits:
    """
    Enforce risk limits on trading activity.
    
    Why Risk Limits Matter:
    ----------------------
    Risk management is often MORE IMPORTANT than entry signals:
    1. **Capital Preservation**: Limits prevent account destruction
    2. **Emotional Control**: Prevents revenge trading after losses
    3. **Consistency**: Maintains discipline across all trades
    4. **Survivability**: Keeps trader in the game during drawdowns
    5. **Long-term Success**: Most traders fail due to poor risk management
    
    Key Limits:
    ----------
    - Daily Loss Limit: Stop trading if daily loss exceeds threshold
    - Max Position Size: Limit position size as % of account
    - Max Open Positions: Limit number of concurrent positions
    - Max Drawdown: Stop trading if account drawdown exceeds threshold
    """
    
    def __init__(
        self,
        initial_balance: float,
        max_daily_loss_pct: float = 0.05,  # 5% max daily loss
        max_position_pct: float = 0.25,  # Max 25% in one position
        max_open_positions: int = 5,  # Max 5 concurrent positions
        max_drawdown_pct: float = 0.20  # 20% max drawdown from peak
    ):
        """
        Initialize risk limits.
        
        Args:
            initial_balance: Starting account balance
            max_daily_loss_pct: Maximum daily loss as % of account (0.05 = 5%)
            max_position_pct: Maximum position size as % of account (0.25 = 25%)
            max_open_positions: Maximum number of concurrent positions
            max_drawdown_pct: Maximum drawdown from peak balance (0.20 = 20%)
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.peak_balance = initial_balance
        
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_position_pct = max_position_pct
        self.max_open_positions = max_open_positions
        self.max_drawdown_pct = max_drawdown_pct
        
        # Track daily P&L
        self.current_date: Optional[date] = None
        self.daily_starting_balance: float = initial_balance
        self.daily_pnl: float = 0.0
        
        self.logger = logger
    
    def update_balance(self, new_balance: float, current_date: Optional[date] = None):
        """
        Update account balance and check daily limits.
        
        Args:
            new_balance: New account balance
            current_date: Current date (for daily tracking)
        """
        # Check if new day
        if current_date is not None and current_date != self.current_date:
            # Reset daily tracking
            self.current_date = current_date
            self.daily_starting_balance = self.current_balance
            self.daily_pnl = 0.0
            self.logger.debug(f"New trading day: {current_date}, starting balance: ${self.daily_starting_balance:,.2f}")
        
        # Update balance
        old_balance = self.current_balance
        self.current_balance = new_balance
        
        # Update peak balance
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
        
        # Update daily P&L
        if current_date is not None and current_date == self.current_date:
            self.daily_pnl = new_balance - self.daily_starting_balance
    
    def check_daily_loss_limit(self) -> RiskLimitResult:
        """
        Check if daily loss limit has been exceeded.
        
        Returns:
            RiskLimitResult indicating if trading is allowed
        """
        if self.current_date is None:
            # Can't check daily limit without date tracking
            return RiskLimitResult(
                is_allowed=True,
                reason="Daily tracking not initialized",
                current_value=0.0,
                limit_value=0.0
            )
        
        daily_loss_limit = self.daily_starting_balance * self.max_daily_loss_pct
        
        if self.daily_pnl <= -daily_loss_limit:
            return RiskLimitResult(
                is_allowed=False,
                reason=f"Daily loss limit exceeded: ${abs(self.daily_pnl):,.2f} >= ${daily_loss_limit:,.2f}",
                current_value=abs(self.daily_pnl),
                limit_value=daily_loss_limit
            )
        
        return RiskLimitResult(
            is_allowed=True,
            reason="OK",
            current_value=abs(self.daily_pnl) if self.daily_pnl < 0 else 0.0,
            limit_value=daily_loss_limit
        )
    
    def check_position_size_limit(self, position_value: float) -> RiskLimitResult:
        """
        Check if position size exceeds maximum allowed.
        
        Args:
            position_value: Value of the position
        
        Returns:
            RiskLimitResult indicating if position is allowed
        """
        max_position_value = self.current_balance * self.max_position_pct
        
        if position_value > max_position_value:
            return RiskLimitResult(
                is_allowed=False,
                reason=f"Position size exceeds limit: ${position_value:,.2f} > ${max_position_value:,.2f}",
                current_value=position_value,
                limit_value=max_position_value
            )
        
        return RiskLimitResult(
            is_allowed=True,
            reason="OK",
            current_value=position_value,
            limit_value=max_position_value
        )
    
    def check_open_positions_limit(self, num_open_positions: int) -> RiskLimitResult:
        """
        Check if number of open positions exceeds maximum.
        
        Args:
            num_open_positions: Current number of open positions
        
        Returns:
            RiskLimitResult indicating if new position is allowed
        """
        if num_open_positions >= self.max_open_positions:
            return RiskLimitResult(
                is_allowed=False,
                reason=f"Max open positions reached: {num_open_positions} >= {self.max_open_positions}",
                current_value=num_open_positions,
                limit_value=self.max_open_positions
            )
        
        return RiskLimitResult(
            is_allowed=True,
            reason="OK",
            current_value=num_open_positions,
            limit_value=self.max_open_positions
        )
    
    def check_max_drawdown(self) -> RiskLimitResult:
        """
        Check if account drawdown exceeds maximum allowed.
        
        Returns:
            RiskLimitResult indicating if trading is allowed
        """
        if self.peak_balance == 0:
            return RiskLimitResult(
                is_allowed=False,
                reason="Peak balance is zero",
                current_value=0.0,
                limit_value=0.0
            )
        
        drawdown = self.peak_balance - self.current_balance
        drawdown_pct = (drawdown / self.peak_balance)
        max_drawdown = self.peak_balance * self.max_drawdown_pct
        
        if drawdown_pct >= self.max_drawdown_pct:
            return RiskLimitResult(
                is_allowed=False,
                reason=f"Max drawdown exceeded: {drawdown_pct*100:.2f}% >= {self.max_drawdown_pct*100:.2f}%",
                current_value=drawdown,
                limit_value=max_drawdown
            )
        
        return RiskLimitResult(
            is_allowed=True,
            reason="OK",
            current_value=drawdown,
            limit_value=max_drawdown
        )
    
    def check_all_limits(
        self,
        position_value: Optional[float] = None,
        num_open_positions: int = 0
    ) -> dict:
        """
        Check all risk limits at once.
        
        Args:
            position_value: Value of position being considered
            num_open_positions: Current number of open positions
        
        Returns:
            Dictionary with results of all limit checks
        """
        results = {
            'daily_loss': self.check_daily_loss_limit(),
            'max_drawdown': self.check_max_drawdown(),
            'open_positions': self.check_open_positions_limit(num_open_positions)
        }
        
        if position_value is not None:
            results['position_size'] = self.check_position_size_limit(position_value)
        
        # Overall: allowed only if ALL checks pass
        results['overall_allowed'] = all(r.is_allowed for r in results.values())
        
        if not results['overall_allowed']:
            failed_checks = [name for name, result in results.items() 
                           if name != 'overall_allowed' and not result.is_allowed]
            self.logger.warning(f"Risk limits violated: {failed_checks}")
        
        return results
    
    def get_status(self) -> dict:
        """Get current status of all risk limits."""
        return {
            'current_balance': self.current_balance,
            'peak_balance': self.peak_balance,
            'daily_pnl': self.daily_pnl,
            'daily_loss_limit': self.daily_starting_balance * self.max_daily_loss_pct,
            'max_position_size': self.current_balance * self.max_position_pct,
            'max_open_positions': self.max_open_positions,
            'max_drawdown_limit': self.peak_balance * self.max_drawdown_pct,
            'current_drawdown': self.peak_balance - self.current_balance,
            'current_drawdown_pct': ((self.peak_balance - self.current_balance) / self.peak_balance * 100) if self.peak_balance > 0 else 0.0
        }
    
    def __str__(self) -> str:
        return (
            f"RiskLimits("
            f"daily_loss={self.max_daily_loss_pct*100:.1f}%, "
            f"max_position={self.max_position_pct*100:.1f}%, "
            f"max_positions={self.max_open_positions}, "
            f"max_drawdown={self.max_drawdown_pct*100:.1f}%"
            f")"
        )

