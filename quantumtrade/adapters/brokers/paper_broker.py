"""
Paper Broker — Local simulated broker for risk-free testing.

No real money is involved. All orders are filled instantly at
the requested price. State is kept in memory.

This replaces the old execution/broker_client.PaperBroker with
the new standardised BaseBroker interface.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from .base import (
    BaseBroker, BrokerOrder, OrderResult, Position, AccountInfo,
    OrderSide, OrderType, OrderStatus,
)

# Metrics (optional)
try:
    from monitoring.metrics import (
        ORDERS_SUBMITTED_TOTAL,
        ORDERS_FILLED_TOTAL,
        ORDER_LATENCY_SECONDS,
        BROKER_CONNECTION_STATUS,
        BROKER_ORDERS_IN_FLIGHT,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)


class PaperBroker(BaseBroker):
    """
    Local paper trading — instant fill at requested price, no slippage.
    Ideal for backtesting, development, and strategy validation.
    """

    def __init__(self, initial_capital: float = 100_000.0, **kwargs):
        super().__init__(paper=True)
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, OrderResult] = {}
        self._trade_log: List[dict] = []

    # ── Connection ────────────────────────────────────────────────

    def connect(self) -> bool:
        self._connected = True
        logger.info(
            f"✅ Paper broker connected — Capital: ${self._cash:,.2f}"
        )
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("Paper broker disconnected")

    # ── Connection ────────────────────────────────────────────────

    def connect(self) -> bool:
        start = time.perf_counter()
        try:
            self._connected = True
            logger.info(
                f"✅ Paper broker connected — Capital: ${self._cash:,.2f}"
            )

            if METRICS_AVAILABLE:
                BROKER_CONNECTION_STATUS.labels(broker="paper").set(1)

            return True
        finally:
            if METRICS_AVAILABLE:
                ORDER_LATENCY_SECONDS.labels(broker="paper", stage="connect").observe(
                    time.perf_counter() - start
                )

    def disconnect(self) -> None:
        self._connected = False
        if METRICS_AVAILABLE:
            BROKER_CONNECTION_STATUS.labels(broker="paper").set(0)
        logger.info("Paper broker disconnected")

    # ── Orders ────────────────────────────────────────────────────

    def place_order(self, order: BrokerOrder) -> OrderResult:
        """Simulate order fill instantly."""
        start_time = time.perf_counter()
        order_id = str(uuid4())[:12]

        # Track in-flight orders
        if METRICS_AVAILABLE:
            BROKER_ORDERS_IN_FLIGHT.labels(broker="paper").inc()

        try:
            # Use limit_price when available, otherwise caller must provide
            fill_price = order.limit_price or order.stop_price
            if fill_price is None:
                # Market order — in paper trading, caller should supply a price
                fill_price = 0.0
                logger.warning(
                    f"Paper market order for {order.symbol} has no price. "
                    f"Use set_market_price() or provide limit_price."
                )

            cost = order.quantity * fill_price

            if order.side == OrderSide.BUY:
                if cost > self._cash:
                    result = OrderResult(
                        order_id=order_id, symbol=order.symbol, side=order.side,
                        status=OrderStatus.REJECTED, quantity=order.quantity,
                        raw_response={"error": "Insufficient funds"},
                    )
                    logger.warning(
                        f"⛔ Paper BUY rejected: need ${cost:,.2f}, "
                        f"have ${self._cash:,.2f}"
                    )
                    if METRICS_AVAILABLE:
                        ORDERS_SUBMITTED_TOTAL.labels(
                            side=order.side.value,
                            order_type=order.order_type.value,
                            broker="paper",
                            status="rejected"
                        ).inc()
                    return result

                self._cash -= cost
                pos = self._positions.get(order.symbol)
                if pos:
                    # Average up/down
                    total_qty = pos.quantity + order.quantity
                    total_cost = (pos.avg_entry_price * pos.quantity) + cost
                    pos.avg_entry_price = total_cost / total_qty
                    pos.quantity = total_qty
                    pos.current_price = fill_price
                    pos.market_value = total_qty * fill_price
                else:
                    self._positions[order.symbol] = Position(
                        symbol=order.symbol,
                        quantity=order.quantity,
                        avg_entry_price=fill_price,
                        current_price=fill_price,
                        market_value=order.quantity * fill_price,
                        side="long",
                    )

            elif order.side == OrderSide.SELL:
                pos = self._positions.get(order.symbol)
                if not pos or pos.quantity < order.quantity:
                    result = OrderResult(
                        order_id=order_id, symbol=order.symbol, side=order.side,
                        status=OrderStatus.REJECTED, quantity=order.quantity,
                        raw_response={"error": "Insufficient position"},
                    )
                    logger.warning(
                        f"⛔ Paper SELL rejected: insufficient position for "
                        f"{order.symbol}"
                    )
                    if METRICS_AVAILABLE:
                        ORDERS_SUBMITTED_TOTAL.labels(
                            side=order.side.value,
                            order_type=order.order_type.value,
                            broker="paper",
                            status="rejected"
                        ).inc()
                    return result

                self._cash += cost
                pos.quantity -= order.quantity
                pos.current_price = fill_price
                pos.market_value = pos.quantity * fill_price

                # Remove position if fully closed
                if pos.quantity <= 0:
                    pnl = cost - (order.quantity * pos.avg_entry_price)
                    del self._positions[order.symbol]
                    logger.info(
                        f"📊 Position closed: {order.symbol} P&L: ${pnl:+,.2f}"
                    )

            # Build result
            result = OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                status=OrderStatus.FILLED,
                quantity=order.quantity,
                filled_quantity=order.quantity,
                filled_price=fill_price,
                timestamp=datetime.now(),
            )

            self._orders[order_id] = result
            self._trade_log.append({
                "timestamp": datetime.now().isoformat(),
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": fill_price,
                "cash_after": self._cash,
            })

            logger.info(
                f"📝 Paper {order.side.value}: {order.quantity} "
                f"{order.symbol} @ ${fill_price:,.2f}  "
                f"[Cash: ${self._cash:,.2f}]"
            )

            # Record metrics
            if METRICS_AVAILABLE:
                latency = time.perf_counter() - start_time
                ORDERS_SUBMITTED_TOTAL.labels(
                    side=order.side.value,
                    order_type=order.order_type.value,
                    broker="paper",
                    status="filled"
                ).inc()
                ORDERS_FILLED_TOTAL.labels(
                    side=order.side.value,
                    broker="paper"
                ).inc()
                ORDER_LATENCY_SECONDS.labels(
                    broker="paper",
                    stage="total"
                ).observe(latency)
                BROKER_ORDERS_IN_FLIGHT.labels(broker="paper").dec()

            return result

        except Exception as e:
            if METRICS_AVAILABLE:
                BROKER_ORDERS_IN_FLIGHT.labels(broker="paper").dec()
                ORDERS_SUBMITTED_TOTAL.labels(
                    side=order.side.value,
                    order_type=order.order_type.value,
                    broker="paper",
                    status="error"
                ).inc()
            logger.error(f"Paper broker order error: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Paper orders fill instantly so nothing to cancel."""
        logger.info(f"Paper cancel: order {order_id} already filled")
        return False

    def get_order(self, order_id: str) -> Optional[OrderResult]:
        return self._orders.get(order_id)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Paper orders fill instantly — no open orders."""
        return []

    # ── Positions & Account ───────────────────────────────────────

    def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    def get_account(self) -> AccountInfo:
        positions = self.get_positions()
        portfolio_value = self._cash + sum(p.market_value for p in positions)
        return AccountInfo(
            cash=self._cash,
            portfolio_value=portfolio_value,
            buying_power=self._cash,
            equity=portfolio_value,
            currency="USD",
            positions=positions,
        )

    def get_latest_price(self, symbol: str) -> Optional[float]:
        pos = self._positions.get(symbol)
        return pos.current_price if pos else None

    # ── Paper-Specific Helpers ────────────────────────────────────

    def set_prices(self, prices: Dict[str, float]) -> None:
        """Update current prices for P&L calculations."""
        for symbol, price in prices.items():
            if symbol in self._positions:
                pos = self._positions[symbol]
                pos.current_price = price
                pos.market_value = pos.quantity * price
                pos.unrealised_pnl = (price - pos.avg_entry_price) * pos.quantity

    @property
    def trade_log(self) -> List[dict]:
        """Full trade history."""
        return self._trade_log

    @property
    def total_pnl(self) -> float:
        """Total P&L since start."""
        return self._cash + sum(
            p.market_value for p in self._positions.values()
        ) - self._initial_capital
