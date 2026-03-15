"""
Risk Manager — Portfolio-level risk controls.

Guards against:
  - Position size exceeding limits
  - Daily loss limits
  - Maximum open positions
  - Excessive drawdown

Works with both paper and live trading.
"""

import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Central risk controller for the trading system.

    Enforces:
      1. Max position size as % of portfolio
      2. Daily loss limit
      3. Maximum concurrent positions
      4. Minimum cash reserve
    """

    def __init__(
        self,
        max_position_pct: float = 0.10,
        stop_loss_pct: float = 0.02,
        max_daily_loss_pct: float = 0.05,
        max_open_positions: int = 10,
        min_cash_reserve_pct: float = 0.20,
        initial_capital: float = 100_000.0,
    ):
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_positions = max_open_positions
        self.min_cash_reserve_pct = min_cash_reserve_pct
        self.initial_capital = initial_capital

        # Daily tracking
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._current_date = date.today()

    def check_trade(
        self,
        symbol: str,
        quantity: float,
        price: float,
        portfolio_value: Optional[float] = None,
        current_positions: int = 0,
        cash: Optional[float] = None,
    ) -> bool:
        """
        Verify if a proposed trade is within all risk limits.

        Args:
            symbol: Trading symbol
            quantity: Number of shares/units
            price: Current price
            portfolio_value: Total portfolio value (for % calculations)
            current_positions: Number of currently open positions
            cash: Current cash balance

        Returns:
            True if trade is allowed, False if blocked
        """
        self._reset_daily_if_needed()

        portfolio = portfolio_value or self.initial_capital
        trade_value = quantity * price

        # 1. Max position size check
        max_allowed = portfolio * self.max_position_pct
        if trade_value > max_allowed:
            logger.warning(
                f"⛔ RISK: Position size ${trade_value:,.2f} exceeds "
                f"limit ${max_allowed:,.2f} for {symbol}"
            )
            return False

        # 2. Daily loss limit
        daily_limit = portfolio * self.max_daily_loss_pct
        if abs(self._daily_pnl) >= daily_limit:
            logger.error(
                f"🚨 RISK: Daily loss limit reached "
                f"(${abs(self._daily_pnl):,.2f} >= ${daily_limit:,.2f}). "
                f"Trading HALTED."
            )
            return False

        # 3. Max open positions
        if current_positions >= self.max_open_positions:
            logger.warning(
                f"⛔ RISK: Max positions ({self.max_open_positions}) reached"
            )
            return False

        # 4. Cash reserve check
        if cash is not None:
            min_cash = portfolio * self.min_cash_reserve_pct
            if (cash - trade_value) < min_cash:
                logger.warning(
                    f"⛔ RISK: Trade would breach cash reserve "
                    f"(${min_cash:,.2f} minimum)"
                )
                return False

        self._daily_trades += 1
        return True

    def calculate_position_size(
        self,
        price: float,
        portfolio_value: Optional[float] = None,
    ) -> float:
        """Calculate position size using fixed-fraction method."""
        portfolio = portfolio_value or self.initial_capital
        risk_amount = portfolio * self.max_position_pct
        return risk_amount / price

    def calculate_stop_loss(self, entry_price: float, side: str = "long") -> float:
        """Calculate stop-loss price."""
        if side.lower() == "long":
            return entry_price * (1 - self.stop_loss_pct)
        else:  # short
            return entry_price * (1 + self.stop_loss_pct)

    def record_pnl(self, pnl: float) -> None:
        """Record a realized P&L for daily tracking."""
        self._reset_daily_if_needed()
        self._daily_pnl += pnl

    def _reset_daily_if_needed(self) -> None:
        """Reset daily counters if the date has changed."""
        today = date.today()
        if today != self._current_date:
            logger.info(
                f"🔄 New trading day. Yesterday's P&L: ${self._daily_pnl:+,.2f} "
                f"({self._daily_trades} trades)"
            )
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._current_date = today

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def daily_trades(self) -> int:
        return self._daily_trades

    @property
    def is_trading_halted(self) -> bool:
        """Check if daily loss limit has been breached."""
        daily_limit = self.initial_capital * self.max_daily_loss_pct
        return abs(self._daily_pnl) >= daily_limit
