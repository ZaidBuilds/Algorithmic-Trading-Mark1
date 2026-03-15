"""
Position sizing module for calculating trade sizes based on risk management rules.

Position sizing is CRITICAL for trading success. Many traders focus on entry signals,
but position sizing often matters more for long-term profitability.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class PositionSizeResult:
    """
    Result of position sizing calculation.
    
    Attributes:
        quantity: Number of shares/units to trade
        risk_amount: Dollar amount at risk
        position_value: Total value of position
        is_valid: Whether the position size is valid
        reason: Explanation if position size is invalid
    """
    quantity: float
    risk_amount: float
    position_value: float
    is_valid: bool
    reason: str = ""


class PositionSizer:
    """
    Calculate position sizes based on risk management rules.
    
    Why Position Sizing Matters More Than Entries:
    ----------------------------------------------
    1. **Capital Preservation**: Small losses protect capital for future trades
    2. **Consistent Risk**: Each trade risks the same percentage of account
    3. **Compounding**: Consistent position sizing allows for steady growth
    4. **Emotional Control**: Fixed risk reduces emotional decision-making
    5. **Survivability**: Proper sizing prevents account blow-up from bad streaks
    
    Common Approaches:
    -----------------
    - **Fixed Risk %**: Risk X% of account per trade (recommended)
    - **Fixed Dollar**: Risk fixed dollar amount (less flexible)
    - **Kelly Criterion**: Optimal sizing based on win rate and payoff
    - **Volatility-Based**: Adjust size based on asset volatility
    
    This implementation uses Fixed Risk % approach, which is:
    - Simple and effective
    - Prevents over-leveraging
    - Easy to understand and implement
    """
    
    def __init__(
        self,
        risk_per_trade: float = 0.02,  # 2% risk per trade
        max_position_pct: float = 0.25,  # Max 25% of account in one position
        account_balance: float = 10000.0
    ):
        """
        Initialize position sizer.
        
        Args:
            risk_per_trade: Risk per trade as decimal (0.02 = 2% of account)
            max_position_pct: Maximum position size as % of account (0.25 = 25%)
            account_balance: Current account balance
        """
        if risk_per_trade <= 0 or risk_per_trade > 1:
            raise ValueError(f"risk_per_trade must be between 0 and 1, got {risk_per_trade}")
        if max_position_pct <= 0 or max_position_pct > 1:
            raise ValueError(f"max_position_pct must be between 0 and 1, got {max_position_pct}")
        
        self.risk_per_trade = risk_per_trade
        self.max_position_pct = max_position_pct
        self.account_balance = account_balance
    
    def update_balance(self, new_balance: float):
        """Update account balance."""
        if new_balance <= 0:
            raise ValueError(f"Account balance must be positive, got {new_balance}")
        self.account_balance = new_balance
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        stop_loss_pct: Optional[float] = None
    ) -> PositionSizeResult:
        """
        Calculate position size based on risk percentage.
        
        Args:
            entry_price: Price at which to enter the trade
            stop_loss_price: Stop loss price (absolute)
            stop_loss_pct: Stop loss as percentage (e.g., 0.02 = 2%)
        
        Returns:
            PositionSizeResult with calculated quantity and risk info
        
        Calculation:
        -----------
        1. Risk Amount = Account Balance * Risk Per Trade
        2. Risk Per Share = |Entry Price - Stop Loss Price|
        3. Quantity = Risk Amount / Risk Per Share
        4. Check against max position size limit
        
        Example:
        --------
        Account: $10,000
        Risk per trade: 2% = $200
        Entry: $100
        Stop Loss: $98 (2% below entry)
        Risk per share: $2
        Quantity: $200 / $2 = 100 shares
        Position value: 100 * $100 = $10,000 (100% of account!)
        But max position is 25%, so we limit to $2,500 = 25 shares
        """
        if entry_price <= 0:
            return PositionSizeResult(
                quantity=0.0,
                risk_amount=0.0,
                position_value=0.0,
                is_valid=False,
                reason="Entry price must be positive"
            )
        
        # Calculate risk per share
        if stop_loss_price is not None:
            risk_per_share = abs(entry_price - stop_loss_price)
        elif stop_loss_pct is not None:
            risk_per_share = entry_price * abs(stop_loss_pct)
        else:
            # Default: 2% stop loss
            risk_per_share = entry_price * 0.02
        
        if risk_per_share <= 0:
            return PositionSizeResult(
                quantity=0.0,
                risk_amount=0.0,
                position_value=0.0,
                is_valid=False,
                reason="Stop loss must be different from entry price"
            )
        
        # Calculate risk amount
        risk_amount = self.account_balance * self.risk_per_trade
        
        # Calculate quantity based on risk
        quantity = risk_amount / risk_per_share
        
        # Calculate position value
        position_value = quantity * entry_price
        
        # Check max position size limit
        max_position_value = self.account_balance * self.max_position_pct
        
        if position_value > max_position_value:
            # Limit to max position size
            quantity = max_position_value / entry_price
            position_value = max_position_value
            reason = f"Limited by max position size ({self.max_position_pct*100}%)"
        else:
            reason = "OK"
        
        # Recalculate actual risk (may be less than target if limited)
        actual_risk_amount = quantity * risk_per_share
        
        return PositionSizeResult(
            quantity=quantity,
            risk_amount=actual_risk_amount,
            position_value=position_value,
            is_valid=True,
            reason=reason
        )
    
    def calculate_fixed_quantity(
        self,
        entry_price: float,
        max_value: Optional[float] = None
    ) -> PositionSizeResult:
        """
        Calculate position size using fixed percentage of account.
        
        Args:
            entry_price: Price at which to enter
            max_value: Maximum position value (defaults to max_position_pct of account)
        
        Returns:
            PositionSizeResult
        """
        if entry_price <= 0:
            return PositionSizeResult(
                quantity=0.0,
                risk_amount=0.0,
                position_value=0.0,
                is_valid=False,
                reason="Entry price must be positive"
            )
        
        if max_value is None:
            max_value = self.account_balance * self.max_position_pct
        
        quantity = max_value / entry_price
        position_value = quantity * entry_price
        
        return PositionSizeResult(
            quantity=quantity,
            risk_amount=0.0,  # Not applicable for fixed sizing
            position_value=position_value,
            is_valid=True,
            reason="Fixed percentage sizing"
        )
    
    def __str__(self) -> str:
        return (
            f"PositionSizer(risk_per_trade={self.risk_per_trade*100:.1f}%, "
            f"max_position={self.max_position_pct*100:.1f}%, "
            f"balance=${self.account_balance:,.2f})"
        )

