"""
Multi-Strategy Runner — Run multiple strategies simultaneously.

Assign different strategies to different symbols, or run multiple
strategies on the same symbol and aggregate signals.

Modes:
  1. Symbol-Mapped: Each symbol gets its own strategy
     {"AAPL": "EMA Crossover", "BTCUSD": "Momentum", "ETHBTC": "Scalping"}

  2. Ensemble: Run ALL strategies on EVERY symbol, aggregate signals
     by majority vote or weighted confidence

Usage:
    from multi_strategy import MultiStrategyRunner
    runner = MultiStrategyRunner(broker, db)
    runner.add_assignment("AAPL", "EMA Crossover")
    runner.add_assignment("GOOG", "Momentum")
    runner.start()
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from strategy import get_strategy, list_strategies, BaseStrategy
from strategy.signals import Signal, SignalType
from brokers.base import BrokerOrder, OrderSide, OrderType
from config.settings import settings

logger = logging.getLogger(__name__)


class StrategyAssignment:
    """Maps a strategy to a list of symbols."""
    def __init__(self, strategy_name: str, symbols: List[str]):
        self.strategy_name = strategy_name
        self.strategy = get_strategy(strategy_name)
        self.symbols = symbols


class MultiStrategyRunner:
    """
    Run multiple strategies simultaneously on different symbols.

    Supports:
      - Per-symbol strategy assignment
      - Ensemble mode (multiple strategies per symbol)
      - Signal aggregation (majority vote / weighted)
      - Performance tracking per strategy
    """

    def __init__(self, broker=None, db=None, risk_manager=None):
        self.broker = broker
        self.db = db
        self.risk_manager = risk_manager

        # Strategy assignments: {symbol: [strategy_instances]}
        self._assignments: Dict[str, List[BaseStrategy]] = {}

        # Performance tracking
        self._strategy_signals: Dict[str, Dict[str, int]] = {}  # {strategy: {BUY: n, SELL: n, HOLD: n}}

    # ── Configuration ─────────────────────────────────────────────

    def add_assignment(self, symbol: str, strategy_name: str) -> None:
        """Assign a strategy to a symbol."""
        strategy = get_strategy(strategy_name)

        if symbol not in self._assignments:
            self._assignments[symbol] = []

        self._assignments[symbol].append(strategy)
        logger.info(f"📌 Assigned {strategy_name} → {symbol}")

    def add_ensemble(self, symbols: List[str], strategy_names: List[str] = None) -> None:
        """
        Run multiple strategies on multiple symbols (ensemble mode).

        Args:
            symbols: List of symbols
            strategy_names: List of strategy names (default: ALL strategies)
        """
        names = strategy_names or list_strategies()

        for symbol in symbols:
            for name in names:
                self.add_assignment(symbol, name)

        logger.info(
            f"🎯 Ensemble: {len(names)} strategies × {len(symbols)} symbols "
            f"= {len(names) * len(symbols)} combinations"
        )

    def load_from_config(self, config: Dict[str, str]) -> None:
        """
        Load assignments from a config dict.

        Example:
            {"AAPL": "EMA Crossover", "GOOG": "Momentum"}
        """
        for symbol, strategy_name in config.items():
            self.add_assignment(symbol, strategy_name)

    # ── Execution ─────────────────────────────────────────────────

    def process_all(self) -> List[dict]:
        """
        Process all symbol-strategy assignments.

        Returns a list of action dicts with signal info.
        """
        actions = []

        for symbol, strategies in self._assignments.items():
            try:
                # Fetch data once per symbol
                data = self._fetch_data(symbol)
                if data is None:
                    continue

                if len(strategies) == 1:
                    # Single strategy — direct signal
                    action = self._process_single(symbol, strategies[0], data)
                    if action:
                        actions.append(action)
                else:
                    # Multiple strategies — aggregate signals
                    action = self._process_ensemble(symbol, strategies, data)
                    if action:
                        actions.append(action)

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

        return actions

    def _process_single(
        self, symbol: str, strategy: BaseStrategy, data: pd.DataFrame
    ) -> Optional[dict]:
        """Process a single strategy for a symbol."""
        if len(data) < strategy.get_required_periods():
            return None

        data = strategy.calculate_indicators(data)
        signal = strategy.generate_signal(data, len(data) - 1)

        # Track signal
        self._track_signal(strategy.name, signal)

        if signal.is_hold():
            return None

        return {
            "symbol": symbol,
            "signal": signal,
            "strategy": strategy.name,
            "confidence": signal.confidence,
            "mode": "single",
        }

    def _process_ensemble(
        self, symbol: str, strategies: List[BaseStrategy], data: pd.DataFrame
    ) -> Optional[dict]:
        """
        Run multiple strategies and aggregate signals.

        Aggregation method: Weighted vote by confidence score.
        """
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0
        signals_detail = []

        for strategy in strategies:
            try:
                if len(data) < strategy.get_required_periods():
                    continue

                strategy_data = strategy.calculate_indicators(data.copy())
                signal = strategy.generate_signal(strategy_data, len(strategy_data) - 1)

                # Track signal
                self._track_signal(strategy.name, signal)

                weight = signal.confidence if signal.confidence > 0 else 0.5

                if signal.is_buy():
                    buy_score += weight
                elif signal.is_sell():
                    sell_score += weight

                total_weight += weight

                signals_detail.append({
                    "strategy": strategy.name,
                    "signal": signal.signal_type.value,
                    "confidence": signal.confidence,
                })

            except Exception as e:
                logger.error(f"Ensemble error ({strategy.name} on {symbol}): {e}")

        if total_weight == 0:
            return None

        # Determine aggregate signal
        buy_pct = buy_score / total_weight
        sell_pct = sell_score / total_weight

        # Need > 50% agreement to act
        if buy_pct > 0.5:
            aggregate_signal = SignalType.BUY
            confidence = buy_pct
        elif sell_pct > 0.5:
            aggregate_signal = SignalType.SELL
            confidence = sell_pct
        else:
            return None  # No consensus

        current_price = data["Close"].iloc[-1]

        return {
            "symbol": symbol,
            "signal": Signal(
                signal_type=aggregate_signal,
                price=current_price,
                confidence=confidence,
                timestamp=datetime.now(),
            ),
            "strategy": f"Ensemble ({len(strategies)} strategies)",
            "confidence": confidence,
            "mode": "ensemble",
            "votes": signals_detail,
            "buy_pct": buy_pct,
            "sell_pct": sell_pct,
        }

    # ── Execution via Broker ──────────────────────────────────────

    def execute_actions(self, actions: List[dict]) -> List[dict]:
        """Execute trade actions via the broker."""
        results = []

        for action in actions:
            try:
                symbol = action["symbol"]
                signal = action["signal"]

                if not self.broker or not self.broker.is_connected:
                    logger.warning("Broker not connected")
                    continue

                position = self.broker.get_position(symbol)
                account = self.broker.get_account()

                if signal.is_buy() and not position:
                    qty = self._calculate_qty(signal.price, account.cash)
                    if qty <= 0:
                        continue

                    if self.risk_manager and not self.risk_manager.check_trade(
                        symbol=symbol, quantity=qty, price=signal.price,
                        portfolio_value=account.portfolio_value,
                    ):
                        continue

                    order = BrokerOrder(
                        symbol=symbol, side=OrderSide.BUY,
                        quantity=qty, order_type=OrderType.MARKET,
                        limit_price=signal.price,
                    )
                    result = self.broker.place_order(order)

                    results.append({
                        **action,
                        "order_result": "FILLED" if result.is_filled else "FAILED",
                        "filled_price": result.filled_price,
                        "quantity": qty,
                    })

                elif signal.is_sell() and position:
                    order = BrokerOrder(
                        symbol=symbol, side=OrderSide.SELL,
                        quantity=position.quantity, order_type=OrderType.MARKET,
                        limit_price=signal.price,
                    )
                    result = self.broker.place_order(order)

                    pnl = 0.0
                    if result.is_filled and result.filled_price:
                        pnl = (result.filled_price - position.avg_entry_price) * position.quantity

                    results.append({
                        **action,
                        "order_result": "FILLED" if result.is_filled else "FAILED",
                        "filled_price": result.filled_price,
                        "quantity": position.quantity,
                        "pnl": pnl,
                    })

            except Exception as e:
                logger.error(f"Execute error: {e}")

        return results

    # ── Helpers ────────────────────────────────────────────────────

    def _fetch_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch data for a symbol."""
        try:
            import yfinance as yf
            data = yf.Ticker(symbol).history(period="60d", interval=settings.TIMEFRAME)
            if data is None or data.empty:
                return None
            data.columns = [c.capitalize() for c in data.columns]
            return data
        except Exception as e:
            logger.error(f"Data fetch failed for {symbol}: {e}")
            return None

    def _calculate_qty(self, price: float, cash: float) -> float:
        """Calculate position size."""
        max_alloc = cash * settings.MAX_POSITION_SIZE_PCT
        qty = max_alloc // price
        return float(qty) if qty > 0 else 0

    def _track_signal(self, strategy_name: str, signal: Signal) -> None:
        """Track signal counts per strategy."""
        if strategy_name not in self._strategy_signals:
            self._strategy_signals[strategy_name] = {"BUY": 0, "SELL": 0, "HOLD": 0}
        self._strategy_signals[strategy_name][signal.signal_type.value] += 1

    # ── Reports ───────────────────────────────────────────────────

    def get_assignments_report(self) -> str:
        """Get a formatted report of all strategy assignments."""
        lines = ["📋 *Strategy Assignments*\n"]

        for symbol, strategies in self._assignments.items():
            names = [s.name for s in strategies]
            if len(names) == 1:
                lines.append(f"  📊 {symbol} → {names[0]}")
            else:
                lines.append(f"  🎯 {symbol} → Ensemble ({len(names)} strategies)")
                for n in names:
                    lines.append(f"      • {n}")

        lines.append(f"\nTotal: {sum(len(s) for s in self._assignments.values())} assignments")
        return "\n".join(lines)

    def get_signal_stats(self) -> str:
        """Get signal generation statistics per strategy."""
        lines = ["📊 *Signal Stats*\n"]

        for strategy, counts in sorted(self._strategy_signals.items()):
            total = sum(counts.values())
            buy_pct = counts["BUY"] / total * 100 if total else 0
            sell_pct = counts["SELL"] / total * 100 if total else 0
            lines.append(
                f"  {strategy}:\n"
                f"    BUY: {counts['BUY']} ({buy_pct:.0f}%) | "
                f"SELL: {counts['SELL']} ({sell_pct:.0f}%) | "
                f"HOLD: {counts['HOLD']}"
            )

        return "\n".join(lines)

    @property
    def total_assignments(self) -> int:
        return sum(len(s) for s in self._assignments.values())

    @property
    def symbols(self) -> List[str]:
        return list(self._assignments.keys())
