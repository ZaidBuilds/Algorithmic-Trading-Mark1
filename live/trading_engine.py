"""
Production Live Trading Engine.

This is the core system that ties everything together:
  Broker + Strategy + Risk + Notifications + Scheduler → Autonomous Trading

Usage:
    from live.trading_engine import LiveTradingEngine

    engine = LiveTradingEngine(
        broker_name="alpaca",
        strategy_name="EMA Crossover",
        symbols=["AAPL", "MSFT", "GOOG"],
    )
    engine.start()  # Starts scheduled live trading
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from brokers import get_broker
from brokers.base import BrokerOrder, OrderSide, OrderType, BaseBroker
from strategy import get_strategy, BaseStrategy
from risk.risk_manager import RiskManager
from config.settings import settings
from notifications import NotificationManager
from scheduler import TradingScheduler
from scheduler.market_hours import MarketType
from database import get_db
from database.trade_repository import TradeRepository

logger = logging.getLogger(__name__)


class LiveTradingEngine:
    """
    Production-grade live trading engine.

    Responsibilities:
      1. Connect to a real broker (Alpaca / Binance / Paper)
      2. Fetch real-time market data
      3. Run strategy signals
      4. Apply risk management checks
      5. Execute trades
      6. Send notifications for all trades
      7. Log everything for audit trail
    """

    def __init__(
        self,
        broker_name: str = "paper",
        strategy_name: str = "EMA Crossover",
        symbols: Optional[List[str]] = None,
        interval_seconds: int = 300,
        # Broker config
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
        # Notification config
        telegram_token: str = "",
        telegram_chat_id: str = "",
        discord_webhook_url: str = "",
        email_smtp_host: str = "",
        email_user: str = "",
        email_password: str = "",
        email_to: str = "",
    ):
        self.symbols = symbols or settings.SYMBOLS
        self.interval = interval_seconds
        self._trade_count = 0
        self._start_time: Optional[datetime] = None

        # ── Initialize components ─────────────────────────────────

        # 1. Broker
        self.broker: BaseBroker = get_broker(
            broker_name,
            api_key=api_key or settings.API_KEY or "",
            api_secret=api_secret or settings.API_SECRET or "",
            paper=paper,
            initial_capital=settings.INITIAL_CAPITAL,
        )

        # 2. Strategy
        self.strategy: BaseStrategy = get_strategy(strategy_name)

        # 3. Risk Manager
        self.risk_manager = RiskManager(
            max_position_pct=settings.MAX_POSITION_SIZE_PCT,
            stop_loss_pct=settings.STOP_LOSS_PCT,
            max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
        )

        # 4. Notifications
        self.notifier = NotificationManager(
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            discord_webhook_url=discord_webhook_url,
            email_smtp_host=email_smtp_host,
            email_user=email_user,
            email_password=email_password,
            email_to=email_to,
        )

        # 5. Scheduler
        market_type = MarketType.CRYPTO if "binance" in broker_name.lower() else MarketType.STOCKS
        self.scheduler = TradingScheduler(
            interval_seconds=interval_seconds,
            market_type=market_type,
            respect_market_hours=(market_type == MarketType.STOCKS),
        )

        # 6. Database
        self.db = get_db()
        self.trade_repo = TradeRepository(self.db)

        logger.info(
            f"⚡ LiveTradingEngine initialized\n"
            f"   Broker: {broker_name} ({'PAPER' if paper else 'LIVE'})\n"
            f"   Strategy: {strategy_name}\n"
            f"   Symbols: {self.symbols}\n"
            f"   Interval: {interval_seconds}s\n"
            f"   Notifications: {self.notifier.channel_count} channels"
        )

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        """Connect to broker and start the trading loop."""
        self._start_time = datetime.now()

        # Connect broker
        if not self.broker.connect():
            logger.error("Failed to connect broker. Aborting.")
            self.notifier.send("🚨 Broker connection FAILED. Engine not started.", level="error")
            return

        # Log account info
        account = self.broker.get_account()
        startup_msg = (
            f"🚀 **QuantumTrade Engine Started**\n"
            f"💰 Capital: ${account.cash:,.2f}\n"
            f"📊 Equity: ${account.equity:,.2f}\n"
            f"🎯 Strategy: {self.strategy.name}\n"
            f"📈 Symbols: {', '.join(self.symbols)}"
        )
        logger.info(startup_msg)
        self.notifier.send(startup_msg, level="info")

        # Register tick callback
        self.scheduler.on_tick(self._trading_tick)
        self.scheduler.on_market_open(self._on_market_open)
        self.scheduler.on_market_close(self._on_market_close)
        self.scheduler.on_error(lambda error: self.notifier.send(
            f"🚨 Engine error: {error}", level="error"
        ))

        # Start the scheduler (blocks until stop)
        try:
            self.scheduler.start()
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Gracefully stop the engine."""
        self.scheduler.stop()
        self.broker.disconnect()

        runtime = (datetime.now() - self._start_time).total_seconds() / 60 if self._start_time else 0
        stop_msg = (
            f"🛑 **Engine Stopped**\n"
            f"⏱️ Runtime: {runtime:.1f} minutes\n"
            f"📊 Trades executed: {self._trade_count}"
        )
        logger.info(stop_msg)
        self.notifier.send(stop_msg, level="info")

    # ── Core Trading Logic ────────────────────────────────────────

    def _trading_tick(self) -> None:
        """
        Core trading loop — runs once per tick.

        For each symbol:
          1. Fetch latest data
          2. Calculate indicators
          3. Generate signal
          4. Check risk limits
          5. Execute trade if signal is actionable
        """
        logger.info(f"📌 Trading tick — {len(self.symbols)} symbols")

        for symbol in self.symbols:
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

    def _process_symbol(self, symbol: str) -> None:
        """Process a single symbol — fetch data, signal, trade."""

        # 1. Fetch data
        data = self._fetch_data(symbol)
        if data is None or len(data) < self.strategy.get_required_periods():
            logger.warning(f"Insufficient data for {symbol}")
            return

        # 2. Calculate indicators
        data = self.strategy.calculate_indicators(data)

        # 3. Generate signal
        signal = self.strategy.generate_signal(data, len(data) - 1)

        if signal.is_hold():
            return  # No action needed

        # 4. Get current position
        position = self.broker.get_position(symbol)
        account = self.broker.get_account()

        # 5. Decision logic
        if signal.is_buy() and not position:
            # Calculate position size
            qty = self._calculate_position_size(
                symbol, signal.price, account.cash
            )
            if qty <= 0:
                return

            # Risk check
            if not self.risk_manager.check_trade(
                symbol=symbol,
                quantity=qty,
                price=signal.price,
                portfolio_value=account.portfolio_value,
            ):
                logger.info(f"⛔ Risk manager blocked BUY for {symbol}")
                return

            # Execute BUY
            order = BrokerOrder(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=qty,
                order_type=OrderType.MARKET,
                limit_price=signal.price,
            )
            result = self.broker.place_order(order)

            if result.is_filled:
                self._trade_count += 1
                fill_price = result.filled_price or signal.price

                # Log to database
                self.trade_repo.record_buy(
                    symbol=symbol,
                    quantity=qty,
                    price=fill_price,
                    strategy=self.strategy.name,
                    confidence=signal.confidence,
                    broker=self.broker.__class__.__name__,
                    order_id=result.order_id,
                )

                self.notifier.send_trade_alert(
                    symbol=symbol,
                    side="BUY",
                    quantity=qty,
                    price=fill_price,
                    strategy=self.strategy.name,
                )

        elif signal.is_sell() and position:
            # Sell entire position
            order = BrokerOrder(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=position.quantity,
                order_type=OrderType.MARKET,
                limit_price=signal.price,
            )
            result = self.broker.place_order(order)

            if result.is_filled:
                self._trade_count += 1
                fill_price = result.filled_price or signal.price
                pnl = (fill_price - position.avg_entry_price) * position.quantity

                # Log to database
                self.trade_repo.record_sell(
                    symbol=symbol,
                    quantity=position.quantity,
                    price=fill_price,
                    pnl=pnl,
                    strategy=self.strategy.name,
                    confidence=signal.confidence,
                    broker=self.broker.__class__.__name__,
                    order_id=result.order_id,
                )

                # Record P&L in risk manager
                self.risk_manager.record_pnl(pnl)

                self.notifier.send_trade_alert(
                    symbol=symbol,
                    side="SELL",
                    quantity=position.quantity,
                    price=fill_price,
                    strategy=self.strategy.name,
                    pnl=pnl,
                )

    # ── Helpers ────────────────────────────────────────────────────

    def _fetch_data(self, symbol: str, period: str = "60d") -> Optional[pd.DataFrame]:
        """Fetch historical data for a symbol using yfinance."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=settings.TIMEFRAME)

            if data is None or data.empty:
                return None

            # Standardise column names
            data.columns = [c.capitalize() for c in data.columns]
            return data

        except Exception as e:
            logger.error(f"Data fetch failed for {symbol}: {e}")
            return None

    def _calculate_position_size(
        self, symbol: str, price: float, cash: float
    ) -> float:
        """Calculate position size based on risk parameters."""
        max_allocation = cash * settings.MAX_POSITION_SIZE_PCT
        qty = max_allocation // price  # Whole shares for stocks

        if qty <= 0:
            logger.info(f"Position size 0 for {symbol} at ${price}")
            return 0

        return float(qty)

    def _on_market_open(self) -> None:
        """Called when market opens."""
        account = self.broker.get_account()
        self.notifier.send(
            f"🔔 **Market Open**\n"
            f"💰 Cash: ${account.cash:,.2f}\n"
            f"📊 Equity: ${account.equity:,.2f}\n"
            f"📈 Positions: {len(account.positions)}",
            level="info",
        )

    def _on_market_close(self) -> None:
        """Called when market closes."""
        account = self.broker.get_account()
        self.notifier.send(
            f"🔕 **Market Closed**\n"
            f"📊 Equity: ${account.equity:,.2f}\n"
            f"📈 Trades today: {self._trade_count}",
            level="info",
        )

    # ── Status ────────────────────────────────────────────────────

    def status(self) -> dict:
        """Get current engine status."""
        account = self.broker.get_account()
        return {
            "running": self.scheduler._running,
            "broker_connected": self.broker.is_connected,
            "strategy": self.strategy.name,
            "symbols": self.symbols,
            "trade_count": self._trade_count,
            "cash": account.cash,
            "equity": account.equity,
            "positions": len(account.positions),
            "uptime_minutes": (
                (datetime.now() - self._start_time).total_seconds() / 60
                if self._start_time else 0
            ),
        }
