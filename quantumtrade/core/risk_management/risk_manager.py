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
from typing import Optional, Dict, Any, Tuple

from quantumtrade.domain.risk.position_sizer import PositionSizer

# Import metrics (optional)
try:
    from monitoring.metrics import (
        PORTFOLIO_VAR_95,
        PORTFOLIO_VAR_99,
        MAX_DRAWDOWN_PERCENT,
        CURRENT_DRAWDOWN_PERCENT,
        DAILY_PNL_USD,
        RISK_LIMIT_BREACHES_TOTAL,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

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
        position_sizing_strategy: str = "fixed_fractional",
        risk_per_trade_pct: float = 0.02,
    ):
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_open_positions = max_open_positions
        self.min_cash_reserve_pct = min_cash_reserve_pct
        self.initial_capital = initial_capital

        self.position_sizer = PositionSizer(
            portfolio_value=initial_capital,
            risk_per_trade_pct=risk_per_trade_pct,
            max_position_pct=max_position_pct,
            strategy=position_sizing_strategy,
        )

        self._peak_portfolio_value = initial_capital
        self._current_drawdown = 0.0

        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._current_date = date.today()

        self._historical_returns = []

        logger.info(
            f"RiskManager initialized: max_pos_pct={max_position_pct:.1%}, "
            f"max_daily_loss={max_daily_loss_pct:.1%}, max_positions={max_open_positions}, "
            f"sizing_strategy={position_sizing_strategy}"
        )

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

        # Update peak portfolio value for drawdown tracking
        if METRICS_AVAILABLE:
            if portfolio > self._peak_portfolio_value:
                self._peak_portfolio_value = portfolio
                # Recalculate drawdown
                self._current_drawdown = max(0.0, (self._peak_portfolio_value - portfolio) / self._peak_portfolio_value * 100)
                CURRENT_DRAWDOWN_PERCENT.set(self._current_drawdown)

        # 1. Max position size check
        max_allowed = portfolio * self.max_position_pct
        if trade_value > max_allowed:
            logger.warning(
                f"⛔ RISK: Position size ${trade_value:,.2f} exceeds "
                f"limit ${max_allowed:,.2f} for {symbol}"
            )
            if METRICS_AVAILABLE:
                RISK_LIMIT_BREACHES_TOTAL.labels(limit_type="position_size").inc()
            return False

        # 2. Daily loss limit
        daily_limit = portfolio * self.max_daily_loss_pct
        if abs(self._daily_pnl) >= daily_limit:
            logger.error(
                f"🚨 RISK: Daily loss limit reached "
                f"(${abs(self._daily_pnl):,.2f} >= ${daily_limit:,.2f}). "
                f"Trading HALTED."
            )
            if METRICS_AVAILABLE:
                RISK_LIMIT_BREACHES_TOTAL.labels(limit_type="daily_loss").inc()
            return False

        # 3. Max open positions
        if current_positions >= self.max_open_positions:
            logger.warning(
                f"⛔ RISK: Max positions ({self.max_open_positions}) reached"
            )
            if METRICS_AVAILABLE:
                RISK_LIMIT_BREACHES_TOTAL.labels(limit_type="max_positions").inc()
            return False

        # 4. Cash reserve check
        if cash is not None:
            min_cash = portfolio * self.min_cash_reserve_pct
            if (cash - trade_value) < min_cash:
                logger.warning(
                    f"⛔ RISK: Trade would breach cash reserve "
                    f"(${min_cash:,.2f} minimum)"
                )
                if METRICS_AVAILABLE:
                    RISK_LIMIT_BREACHES_TOTAL.labels(limit_type="cash_reserve").inc()
                return False

        self._daily_trades += 1
        return True

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        portfolio_value: Optional[float] = None,
        confidence: float = 0.5,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
        payoff_ratio: Optional[float] = None,
        current_positions: int = 0,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Calculate position size using the configured PositionSizer.

        Args:
            symbol: Trading symbol
            entry_price: Entry price for the position
            stop_loss_price: Stop loss price
            portfolio_value: Current portfolio value (updates position_sizer if provided)
            confidence: Strategy confidence [0-1]
            volatility: Annualized volatility
            win_rate: Historical win rate
            payoff_ratio: avg_win / avg_loss
            current_positions: Number of open positions

        Returns:
            Tuple of (quantity, metadata)
        """
        if portfolio_value is not None and portfolio_value != self.position_sizer.portfolio_value:
            self.position_sizer.portfolio_value = portfolio_value

        return self.position_sizer.calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            confidence=confidence,
            volatility=volatility,
            win_rate=win_rate,
            avg_win_loss_ratio=payoff_ratio,
            current_positions=current_positions,
        )

    def calculate_position_size_simple(
        self,
        price: float,
        portfolio_value: Optional[float] = None,
    ) -> float:
        """Calculate position size using fixed-fraction method (legacy)."""
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

        # Update metrics
        if METRICS_AVAILABLE:
            DAILY_PNL_USD.set(self._daily_pnl)

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

            # Reset max drawdown at start of new day
            if METRICS_AVAILABLE:
                MAX_DRAWDOWN_PERCENT.set(0.0)
                self._peak_portfolio_value = self.initial_capital
                self._current_drawdown = 0.0

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

    # ─── Metrics Update Methods ────────────────────────────────────

    def update_portfolio_metrics(
        self,
        portfolio_value: float,
        returns_history: Optional[list[float]] = None
    ) -> None:
        """Update risk metrics based on current portfolio value.

        Args:
            portfolio_value: Current total portfolio value (equity)
            returns_history: List of daily returns (for VaR calculation)
        """
        if not METRICS_AVAILABLE:
            return

        # Update peak and drawdown
        if portfolio_value > self._peak_portfolio_value:
            self._peak_portfolio_value = portfolio_value
            self._current_drawdown = 0.0
        else:
            self._current_drawdown = max(
                0.0,
                (self._peak_portfolio_value - portfolio_value) / self._peak_portfolio_value * 100
            )

        CURRENT_DRAWDOWN_PERCENT.set(self._current_drawdown)
        MAX_DRAWDOWN_PERCENT.set(self._current_drawdown)

        # Update daily P&L metric
        DAILY_PNL_USD.set(self._daily_pnl)

        # Calculate VaR if returns history provided
        if returns_history and len(returns_history) >= 20:
            import numpy as np
            returns = np.array(returns_history)
            # 95% VaR (negative number represents loss)
            var_95 = np.percentile(returns, 5) * portfolio_value
            var_99 = np.percentile(returns, 1) * portfolio_value
            # Convert to positive for display
            PORTFOLIO_VAR_95.set(max(0, -var_95))
            PORTFOLIO_VAR_99.set(max(0, -var_99))
