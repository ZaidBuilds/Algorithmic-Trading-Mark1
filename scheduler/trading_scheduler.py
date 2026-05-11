"""
Trading Scheduler — Automated Workflow Engine.

This is the heart of the automation system. It runs trading
strategies on a schedule, respects market hours, and coordinates
all components (broker, strategy, risk, notifications).

Usage:
    scheduler = TradingScheduler(config)
    scheduler.start()   # Runs until stopped
    scheduler.stop()

Workflow:
  1. Wait for market open (or run immediately for crypto)
  2. Fetch latest data for all configured symbols
  3. Run strategy → get signals
  4. Check risk limits
  5. Execute trades via broker
  6. Send notifications
  7. Repeat on schedule
"""

import logging
import signal
import time
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

# Import metrics (optional)
try:
    from monitoring.metrics import (
        SCHEDULER_TICKS_TOTAL,
        SCHEDULER_ERRORS_TOTAL,
        MARKET_SESSION_TRANSITIONS_TOTAL,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

from .market_hours import MarketHours, MarketSession, MarketType, is_market_open

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Production trading scheduler with market-hours awareness.

    Supports:
      - Interval-based execution (e.g., every 5 minutes)
      - Market-hours-only mode (stocks)
      - 24/7 mode (crypto)
      - Graceful shutdown on SIGINT/SIGTERM
      - Pre-market and after-hours hooks
    """

    def __init__(
        self,
        interval_seconds: int = 300,  # 5 minutes
        market_type: MarketType = MarketType.STOCKS,
        respect_market_hours: bool = True,
    ):
        self.interval = interval_seconds
        self.market_type = market_type
        self.respect_market_hours = respect_market_hours

        self._running = False
        self._callbacks: Dict[str, List[Callable]] = {
            "tick": [],
            "pre_market": [],
            "market_open": [],
            "market_close": [],
            "after_hours": [],
            "error": [],
        }
        self._tick_count = 0
        self._last_session = MarketSession.CLOSED

    # ── Event Registration ────────────────────────────────────────

    def on_tick(self, callback: Callable) -> None:
        """Register a callback for each trading tick."""
        self._callbacks["tick"].append(callback)

    def on_market_open(self, callback: Callable) -> None:
        """Fires once when market transitions to REGULAR."""
        self._callbacks["market_open"].append(callback)

    def on_market_close(self, callback: Callable) -> None:
        """Fires once when market transitions from REGULAR to non-REGULAR."""
        self._callbacks["market_close"].append(callback)

    def on_pre_market(self, callback: Callable) -> None:
        """Fires once when pre-market session starts."""
        self._callbacks["pre_market"].append(callback)

    def on_error(self, callback: Callable) -> None:
        """Fires when a tick callback raises an exception."""
        self._callbacks["error"].append(callback)

    # ── Execution ─────────────────────────────────────────────────

    def start(self) -> None:
        """Start the trading scheduler. Blocks until stop() is called."""
        self._running = True
        self._setup_signal_handlers()

        logger.info(
            f"🚀 Scheduler started — "
            f"Market: {self.market_type.value} | "
            f"Interval: {self.interval}s | "
            f"Market hours: {'ON' if self.respect_market_hours else 'OFF'}"
        )

        while self._running:
            try:
                current_session = MarketHours.get_session(self.market_type)

                # Detect session transitions
                self._check_session_transitions(current_session)
                self._last_session = current_session

                # Should we run this tick?
                should_run = (
                    not self.respect_market_hours or
                    current_session == MarketSession.REGULAR or
                    self.market_type == MarketType.CRYPTO
                )

                if should_run:
                    self._tick_count += 1
                    self._execute_tick()
                else:
                    wait_secs = MarketHours.seconds_until_open(self.market_type)
                    if wait_secs > 60:
                        mins = wait_secs // 60
                        logger.info(
                            f"⏳ Market closed. Next open in ~{mins} minutes. "
                            f"Session: {current_session.value}"
                        )
                        # Sleep longer when market is closed (check every 60s)
                        time.sleep(min(60, wait_secs))
                        continue

                time.sleep(self.interval)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                self._fire("error", error=e)
                time.sleep(10)  # Back off on errors

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._running = False
        logger.info(
            f"🛑 Scheduler stopped after {self._tick_count} ticks"
        )

    def start_async(self) -> threading.Thread:
        """Start the scheduler in a background thread."""
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        logger.info("Scheduler started in background thread")
        return thread

    # ── Internal ──────────────────────────────────────────────────

    def _execute_tick(self) -> None:
        """Execute all registered tick callbacks."""
        logger.debug(f"📌 Tick #{self._tick_count}")
        for callback in self._callbacks["tick"]:
            try:
                callback()
            except Exception as e:
                logger.error(f"Tick callback error: {e}")
                self._fire("error", error=e)

        # Record tick metric
        if METRICS_AVAILABLE:
            SCHEDULER_TICKS_TOTAL.inc()

    def _check_session_transitions(self, current: MarketSession) -> None:
        """Detect and fire session transition events."""
        prev = self._last_session

        if prev != current:
            if METRICS_AVAILABLE:
                MARKET_SESSION_TRANSITIONS_TOTAL.labels(
                    from_session=prev.value if prev else "none",
                    to_session=current.value
                ).inc()

            if current == MarketSession.REGULAR and prev != MarketSession.REGULAR:
                logger.info("🔔 Market OPEN")
                self._fire("market_open")
            elif prev == MarketSession.REGULAR and current != MarketSession.REGULAR:
                logger.info("🔕 Market CLOSED")
                self._fire("market_close")
            elif current == MarketSession.PRE_MARKET:
                logger.info("🌅 Pre-market session started")
                self._fire("pre_market")

    def _fire(self, event: str, **kwargs) -> None:
        """Fire all callbacks for an event."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(**kwargs) if kwargs else cb()
            except Exception as e:
                logger.error(f"Event '{event}' callback error: {e}")

    def _setup_signal_handlers(self) -> None:
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, OSError):
            # Can fail in non-main threads
            pass

    def _handle_signal(self, signum, frame) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
