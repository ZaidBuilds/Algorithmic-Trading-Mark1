"""
Paper trading execution simulator.

This module simulates trading execution without using real money.
Perfect for testing strategies before going live.
"""

from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass
import logging

from .order import Order, OrderSide, OrderType, OrderStatus
from .fill import OrderFiller
from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossManager
from risk.limits import RiskLimits

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Open position information."""
    symbol: str
    quantity: float
    entry_price: float
    entry_date: datetime
    stop_loss_price: Optional[float] = None
    current_price: float = 0.0
    
    @property
    def value(self) -> float:
        """Current position value."""
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        """Total cost of position."""
        return self.quantity * self.entry_price
    
    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return self.value - self.cost_basis
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100


@dataclass
class Trade:
    """Completed trade information."""
    symbol: str
    side: OrderSide
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    commission: float
    duration_days: int


class PaperTrader:
    """
    Paper trading execution simulator.
    
    Features:
    - Simulated order execution
    - Position tracking
    - Trade history
    - Account balance management
    - Risk management integration
    - Commission and slippage simulation
    
    Paper Trading Benefits:
    ----------------------
    1. Test strategies without risking real money
    2. Understand execution costs
    3. Validate risk management
    4. Build confidence before going live
    5. Practice trading discipline
    """
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        commission: float = 0.001,  # 0.1%
        enable_slippage: bool = False
    ):
        """
        Initialize paper trader.
        
        Args:
            initial_balance: Starting account balance
            commission: Commission rate (0.001 = 0.1%)
            enable_slippage: Whether to simulate slippage
        """
        self.initial_balance = initial_balance
        self.cash_balance = initial_balance
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.trades: List[Trade] = []
        self.orders: List[Order] = []
        
        # Execution components
        self.order_filler = OrderFiller(commission=commission, enable_slippage=enable_slippage)
        
        # Risk management (optional, can be set externally)
        self.position_sizer: Optional[PositionSizer] = None
        self.stop_loss_manager: Optional[StopLossManager] = None
        self.risk_limits: Optional[RiskLimits] = None
        
        self.logger = logger
    
    def set_position_sizer(self, position_sizer: PositionSizer):
        """Set position sizer for automatic position sizing."""
        self.position_sizer = position_sizer
    
    def set_stop_loss_manager(self, stop_loss_manager: StopLossManager):
        """Set stop-loss manager."""
        self.stop_loss_manager = stop_loss_manager
    
    def set_risk_limits(self, risk_limits: RiskLimits):
        """Set risk limits."""
        self.risk_limits = risk_limits
    
    def get_balance(self) -> float:
        """Get current cash balance."""
        return self.cash_balance
    
    def get_total_equity(self) -> float:
        """Get total account equity (cash + positions)."""
        positions_value = sum(pos.value for pos in self.positions.values())
        return self.cash_balance + positions_value
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol."""
        return self.positions.get(symbol)
    
    def update_position_price(self, symbol: str, price: float):
        """Update current price for a position."""
        if symbol in self.positions:
            self.positions[symbol].current_price = price
    
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None
    ) -> Order:
        """
        Submit an order.
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Number of shares
            order_type: MARKET or LIMIT
            limit_price: Limit price (required for LIMIT orders)
        
        Returns:
            Created order
        """
        order_id = f"{symbol}_{side.value}_{datetime.now().timestamp()}"
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=limit_price
        )
        
        self.orders.append(order)
        self.logger.debug(f"Submitted order: {order}")
        
        return order
    
    def execute_order(
        self,
        order: Order,
        current_price: float,
        current_high: Optional[float] = None,
        current_low: Optional[float] = None,
        current_date: Optional[datetime] = None
    ) -> bool:
        """
        Execute an order (fill it).
        
        Args:
            order: Order to execute
            current_price: Current market price
            current_high: Current high price
            current_low: Current low price
        
        Returns:
            True if order was filled, False otherwise
        """
        # Fill the order
        filled_order = self.order_filler.fill_order(
            order,
            current_price,
            current_high,
            current_low
        )
        
        if not filled_order.is_filled():
            return False
            
        # Use provided date or now
        exec_date = current_date or datetime.now()
        
        # Process filled order
        symbol = filled_order.symbol
        quantity = filled_order.filled_quantity
        price = filled_order.filled_price
        commission = filled_order.commission
        
        if filled_order.is_buy():
            # BUY order - open or add to position
            cost = (quantity * price) + commission
            
            if self.cash_balance < cost:
                self.logger.warning(f"Insufficient funds for order: need ${cost:.2f}, have ${self.cash_balance:.2f}")
                filled_order.status = OrderStatus.REJECTED
                return False
            
            self.cash_balance -= cost
            
            if symbol in self.positions:
                # Add to existing position (average entry price)
                pos = self.positions[symbol]
                total_cost = pos.cost_basis + cost
                total_quantity = pos.quantity + quantity
                pos.entry_price = total_cost / total_quantity
                pos.quantity = total_quantity
            else:
                # Open new position
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=price,
                    entry_date=exec_date,
                    current_price=price
                )
            
            self.logger.info(f"Bought {quantity:.2f} {symbol} @ ${price:.2f}, Balance: ${self.cash_balance:.2f}")
        
        else:
            # SELL order - close position
            if symbol not in self.positions:
                self.logger.warning(f"No position to sell for {symbol}")
                filled_order.status = OrderStatus.REJECTED
                return False
            
            pos = self.positions[symbol]
            
            if quantity > pos.quantity:
                self.logger.warning(f"Trying to sell {quantity:.2f} but only have {pos.quantity:.2f}")
                quantity = pos.quantity
            
            proceeds = (quantity * price) - commission
            self.cash_balance += proceeds
            
            # Calculate trade P&L
            entry_price = pos.entry_price
            pnl = (price - entry_price) * quantity - commission
            pnl_pct = ((price - entry_price) / entry_price) * 100
            
            # Record trade
            trade = Trade(
                symbol=symbol,
                side=OrderSide.SELL,
                entry_date=pos.entry_date,
                exit_date=exec_date,
                entry_price=entry_price,
                exit_price=price,
                quantity=quantity,
                pnl=pnl,
                pnl_pct=pnl_pct,
                commission=commission,
                duration_days=(exec_date - pos.entry_date).days
            )
            self.trades.append(trade)
            
            # Update or close position
            pos.quantity -= quantity
            if pos.quantity <= 0.0001:  # Close position
                del self.positions[symbol]
                self.logger.info(f"Closed position {symbol}: P&L ${pnl:.2f} ({pnl_pct:.2f}%)")
            else:
                self.logger.info(f"Partially closed {symbol}: Sold {quantity:.2f}, P&L ${pnl:.2f}")
        
        return True
    
    def check_stop_losses(self, price_data: Dict[str, float], current_date: Optional[datetime] = None) -> List[str]:
        """
        Check and execute stop losses for open positions.
        
        Args:
            price_data: Dictionary mapping symbol to current price
        
        Returns:
            List of symbols that hit stop loss
        """
        if not self.stop_loss_manager:
            return []
        
        hit_symbols = []
        
        for symbol, position in list(self.positions.items()):
            if position.stop_loss_price is None:
                continue
            
            current_price = price_data.get(symbol)
            if current_price is None:
                continue
            
            if current_price <= position.stop_loss_price:
                # Stop loss hit - close position
                hit_symbols.append(symbol)
                
                order = self.submit_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=position.quantity,
                    order_type=OrderType.MARKET
                )
                
                self.execute_order(order, current_price, current_date=current_date)
                self.logger.info(f"Stop loss triggered for {symbol} at ${current_price:.2f}")
        
        return hit_symbols
    
    def get_summary(self) -> Dict:
        """Get trading summary."""
        total_equity = self.get_total_equity()
        positions_value = sum(pos.value for pos in self.positions.values())
        unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())
        realized_pnl = sum(t.pnl for t in self.trades)
        total_pnl = total_equity - self.initial_balance
        
        return {
            'initial_balance': self.initial_balance,
            'cash_balance': self.cash_balance,
            'positions_value': positions_value,
            'total_equity': total_equity,
            'unrealized_pnl': unrealized_pnl,
            'realized_pnl': realized_pnl,
            'total_pnl': total_pnl,
            'total_pnl_pct': (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0.0,
            'num_positions': len(self.positions),
            'num_trades': len(self.trades),
            'positions': {
                symbol: {
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'unrealized_pnl_pct': pos.unrealized_pnl_pct
                }
                for symbol, pos in self.positions.items()
            }
        }
    
    def __str__(self) -> str:
        """String representation."""
        return f"PaperTrader(balance=${self.cash_balance:,.2f}, positions={len(self.positions)}, trades={len(self.trades)})"

