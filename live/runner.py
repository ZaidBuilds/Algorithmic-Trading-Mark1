"""
Live Trading Runner — deprecated in favor of trading_engine.py.

This module is kept for backward compatibility. Use LiveTradingEngine instead:

    from live.trading_engine import LiveTradingEngine
    engine = LiveTradingEngine(broker_name="alpaca", strategy_name="EMA Crossover")
    engine.start()
"""

import time
import logging
from config.settings import settings

logger = logging.getLogger(__name__)


class TradingRunner:
    """Legacy runner — use LiveTradingEngine for production."""

    def __init__(self, strategy, broker, risk_manager):
        self.strategy = strategy
        self.broker = broker
        self.risk_manager = risk_manager

    def tick(self):
        logger.info("Tick started (legacy runner)...")
        for symbol in settings.SYMBOLS:
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="5d", interval=settings.TIMEFRAME)

                if df.empty:
                    continue

                df.columns = [c.capitalize() for c in df.columns]
                df = self.strategy.calculate_indicators(df)
                signal = self.strategy.generate_signal(df, len(df) - 1)

                current_price = df["Close"].iloc[-1]

                if signal.is_buy():
                    qty = self.risk_manager.calculate_position_size(current_price)
                    if self.risk_manager.check_trade(symbol, qty, current_price):
                        self.broker.place_order(symbol, "BUY", qty, current_price)

                elif signal.is_sell():
                    self.broker.place_order(symbol, "SELL", 0, current_price)

            except Exception as e:
                logger.error(f"Error in runner tick for {symbol}: {e}")

    def run(self, interval_minutes: int = 60):
        try:
            import schedule
        except ImportError:
            logger.error("schedule library not found. pip install schedule")
            return

        logger.info(f"Starting Trading Runner in {settings.MODE} mode...")
        self.tick()

        schedule.every(interval_minutes).minutes.do(self.tick)
        while True:
            schedule.run_pending()
            time.sleep(1)
