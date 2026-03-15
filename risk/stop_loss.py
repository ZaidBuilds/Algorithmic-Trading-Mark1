"""
Stop-loss management module.

Stop losses are essential for:
1. Limiting losses on losing trades
2. Protecting capital
3. Removing emotion from exit decisions
4. Enforcing discipline
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StopLoss:
    """
    Stop-loss order information.
    
    Attributes:
        price: Stop loss price level
        percent: Stop loss as percentage of entry price
        type: Type of stop loss ('fixed', 'trailing', 'atr_based')
        entry_price: Price at which position was entered
        entry_date: Date position was entered
    """
    price: float
    percent: float
    type: str = 'fixed'
    entry_price: float = 0.0
    entry_date: Optional[datetime] = None


class StopLossManager:
    """
    Manage stop-loss orders for positions.
    
    Types of Stop Losses:
    --------------------
    1. **Fixed Stop Loss**: Fixed price level (e.g., 2% below entry)
    2. **Trailing Stop Loss**: Moves up with price, locks in profits
    3. **ATR-Based Stop Loss**: Based on Average True Range (volatility-adjusted)
    
    This implementation starts with fixed stop loss, which is:
    - Simple and effective
    - Easy to understand
    - Prevents large losses
    """
    
    def __init__(self, default_stop_pct: float = 0.02):
        """
        Initialize stop-loss manager.
        
        Args:
            default_stop_pct: Default stop loss as percentage (0.02 = 2%)
        """
        if default_stop_pct <= 0 or default_stop_pct > 1:
            raise ValueError(f"default_stop_pct must be between 0 and 1, got {default_stop_pct}")
        
        self.default_stop_pct = default_stop_pct
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        stop_pct: Optional[float] = None,
        stop_price: Optional[float] = None,
        entry_date: Optional[datetime] = None
    ) -> StopLoss:
        """
        Calculate stop-loss price.
        
        Args:
            entry_price: Price at which position was entered
            stop_pct: Stop loss as percentage (defaults to default_stop_pct)
            stop_price: Absolute stop loss price (overrides stop_pct)
            entry_date: Date position was entered
        
        Returns:
            StopLoss object with calculated stop price
        
        For Long Positions:
        -----------------
        - Stop loss should be BELOW entry price
        - Example: Entry $100, Stop 2% → Stop at $98
        """
        if entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {entry_price}")
        
        if stop_price is not None:
            # Use absolute stop price
            stop_loss_price = stop_price
            stop_loss_pct = abs((entry_price - stop_price) / entry_price)
        else:
            # Use percentage
            stop_pct = stop_pct or self.default_stop_pct
            stop_loss_price = entry_price * (1 - stop_pct)
            stop_loss_pct = stop_pct
        
        # Ensure stop loss is below entry for long positions
        if stop_loss_price >= entry_price:
            raise ValueError(
                f"Stop loss price ({stop_loss_price}) must be below entry price ({entry_price}) "
                "for long positions"
            )
        
        return StopLoss(
            price=stop_loss_price,
            percent=stop_loss_pct,
            type='fixed',
            entry_price=entry_price,
            entry_date=entry_date
        )
    
    def check_stop_loss_hit(
        self,
        stop_loss: StopLoss,
        current_price: float,
        current_low: Optional[float] = None
    ) -> bool:
        """
        Check if stop loss has been hit.
        
        Args:
            stop_loss: StopLoss object
            current_price: Current price (closing price)
            current_low: Current low price (use for intraday stop checks)
        
        Returns:
            True if stop loss was hit, False otherwise
        
        Note:
        ----
        For backtesting, we typically use closing price
        - If current_low is provided, we check if low touched stop level
        - If only current_price, we check if price closed below stop
        """
        if current_low is not None:
            # Check if low price touched stop level
            return current_low <= stop_loss.price
        else:
            # Check if closing price is below stop
            return current_price <= stop_loss.price
    
    def calculate_unrealized_pnl(
        self,
        entry_price: float,
        current_price: float,
        quantity: float,
        stop_loss: Optional[StopLoss] = None
    ) -> dict:
        """
        Calculate unrealized P&L and distance to stop loss.
        
        Args:
            entry_price: Entry price
            current_price: Current price
            quantity: Position quantity
            stop_loss: Optional stop loss object
        
        Returns:
            Dictionary with unrealized_pnl, unrealized_pnl_pct, distance_to_stop, etc.
        """
        unrealized_pnl = (current_price - entry_price) * quantity
        unrealized_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        result = {
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'current_price': current_price,
            'entry_price': entry_price,
            'quantity': quantity
        }
        
        if stop_loss:
            distance_to_stop = current_price - stop_loss.price
            distance_to_stop_pct = ((current_price - stop_loss.price) / entry_price) * 100
            risk_amount = (entry_price - stop_loss.price) * quantity
            
            result.update({
                'stop_loss_price': stop_loss.price,
                'distance_to_stop': distance_to_stop,
                'distance_to_stop_pct': distance_to_stop_pct,
                'risk_amount': risk_amount,
                'is_stop_hit': self.check_stop_loss_hit(stop_loss, current_price)
            })
        
        return result
    
    def __str__(self) -> str:
        return f"StopLossManager(default_stop_pct={self.default_stop_pct*100:.1f}%)"

