"""
Alpaca Broker Integration — Real US Stocks & Crypto.

Alpaca Markets provides:
  - Commission-free stock trading
  - Paper trading (sandbox) with identical API
  - Crypto trading (BTC, ETH, etc.)
  - Real-time & historical market data
  - WebSocket streaming

Setup:
  1. Create account at https://alpaca.markets
  2. Get API keys from dashboard
  3. Set in .env:
     ALPACA_API_KEY=your_key
     ALPACA_API_SECRET=your_secret
     ALPACA_PAPER=true
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from .base import (
    BaseBroker, BrokerOrder, OrderResult, Position, AccountInfo,
    OrderSide, OrderType, OrderStatus, TimeInForce,
)

logger = logging.getLogger(__name__)


class AlpacaBroker(BaseBroker):
    """
    Production broker adapter for Alpaca Markets.

    Supports both paper and live trading through the same interface.
    Uses alpaca-py SDK for all interactions.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
        **kwargs,
    ):
        super().__init__(paper=paper)
        self.api_key = api_key
        self.api_secret = api_secret
        self._trading_client = None
        self._data_client = None

    # ── Connection ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to Alpaca using alpaca-py SDK."""
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient

            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.api_secret,
                paper=self.paper,
            )
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.api_secret,
            )

            # Verify connection by fetching account
            account = self._trading_client.get_account()
            self._connected = True
            mode = "PAPER" if self.paper else "LIVE"
            logger.info(
                f"✅ Alpaca connected [{mode}] — "
                f"Cash: ${float(account.cash):,.2f}  "
                f"Equity: ${float(account.equity):,.2f}"
            )
            return True

        except ImportError:
            logger.error(
                "alpaca-py not installed. Run: pip install alpaca-py"
            )
            return False
        except Exception as e:
            logger.error(f"Alpaca connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Alpaca."""
        self._trading_client = None
        self._data_client = None
        self._connected = False
        logger.info("Alpaca disconnected")

    # ── Orders ────────────────────────────────────────────────────

    def place_order(self, order: BrokerOrder) -> OrderResult:
        """Place an order through Alpaca."""
        if not self._connected or not self._trading_client:
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                status=OrderStatus.REJECTED, quantity=order.quantity,
                raw_response={"error": "Not connected"},
            )

        try:
            from alpaca.trading.requests import (
                MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
                StopLimitOrderRequest,
            )
            from alpaca.trading.enums import (
                OrderSide as AlpSide, TimeInForce as AlpTIF,
            )

            # Map our enums to Alpaca enums
            alp_side = AlpSide.BUY if order.side == OrderSide.BUY else AlpSide.SELL
            alp_tif = {
                TimeInForce.DAY: AlpTIF.DAY,
                TimeInForce.GTC: AlpTIF.GTC,
                TimeInForce.IOC: AlpTIF.IOC,
                TimeInForce.FOK: AlpTIF.FOK,
            }.get(order.time_in_force, AlpTIF.GTC)

            # Build the right request type
            if order.order_type == OrderType.MARKET:
                req = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alp_side,
                    time_in_force=alp_tif,
                )
            elif order.order_type == OrderType.LIMIT:
                req = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alp_side,
                    time_in_force=alp_tif,
                    limit_price=order.limit_price,
                )
            elif order.order_type == OrderType.STOP:
                req = StopOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alp_side,
                    time_in_force=alp_tif,
                    stop_price=order.stop_price,
                )
            elif order.order_type == OrderType.STOP_LIMIT:
                req = StopLimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alp_side,
                    time_in_force=alp_tif,
                    limit_price=order.limit_price,
                    stop_price=order.stop_price,
                )
            else:
                raise ValueError(f"Unsupported order type: {order.order_type}")

            # Submit
            result = self._trading_client.submit_order(req)

            status_map = {
                "new": OrderStatus.SUBMITTED,
                "accepted": OrderStatus.SUBMITTED,
                "filled": OrderStatus.FILLED,
                "partially_filled": OrderStatus.PARTIALLY_FILLED,
                "canceled": OrderStatus.CANCELLED,
                "rejected": OrderStatus.REJECTED,
                "expired": OrderStatus.EXPIRED,
                "pending_new": OrderStatus.PENDING,
            }

            order_result = OrderResult(
                order_id=str(result.id),
                symbol=result.symbol,
                side=OrderSide.BUY if str(result.side) == "buy" else OrderSide.SELL,
                status=status_map.get(str(result.status), OrderStatus.PENDING),
                quantity=float(result.qty),
                filled_quantity=float(result.filled_qty or 0),
                filled_price=float(result.filled_avg_price) if result.filled_avg_price else None,
                timestamp=datetime.now(),
                raw_response={"alpaca_id": str(result.id)},
            )

            logger.info(
                f"📝 Alpaca order placed: {order.side.value} "
                f"{order.quantity} {order.symbol} → {order_result.status.value}"
            )
            return order_result

        except Exception as e:
            logger.error(f"Alpaca order failed: {e}")
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                status=OrderStatus.REJECTED, quantity=order.quantity,
                raw_response={"error": str(e)},
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open Alpaca order."""
        try:
            self._trading_client.cancel_order_by_id(order_id)
            logger.info(f"❌ Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[OrderResult]:
        """Get order status from Alpaca."""
        try:
            result = self._trading_client.get_order_by_id(order_id)
            return OrderResult(
                order_id=str(result.id),
                symbol=result.symbol,
                side=OrderSide.BUY if str(result.side) == "buy" else OrderSide.SELL,
                status=OrderStatus.FILLED if str(result.status) == "filled" else OrderStatus.PENDING,
                quantity=float(result.qty),
                filled_quantity=float(result.filled_qty or 0),
                filled_price=float(result.filled_avg_price) if result.filled_avg_price else None,
            )
        except Exception as e:
            logger.error(f"Get order failed: {e}")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """List open orders from Alpaca."""
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self._trading_client.get_orders(filter=req)

            results = []
            for o in orders:
                if symbol and o.symbol != symbol:
                    continue
                results.append(OrderResult(
                    order_id=str(o.id),
                    symbol=o.symbol,
                    side=OrderSide.BUY if str(o.side) == "buy" else OrderSide.SELL,
                    status=OrderStatus.PENDING,
                    quantity=float(o.qty),
                    filled_quantity=float(o.filled_qty or 0),
                ))
            return results
        except Exception as e:
            logger.error(f"Get open orders failed: {e}")
            return []

    # ── Positions & Account ───────────────────────────────────────

    def get_positions(self) -> List[Position]:
        """Get all open positions from Alpaca."""
        try:
            positions = self._trading_client.get_all_positions()
            return [
                Position(
                    symbol=p.symbol,
                    quantity=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealised_pnl=float(p.unrealized_pl),
                    market_value=float(p.market_value),
                    side="long" if str(p.side) == "long" else "short",
                )
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []

    def get_account(self) -> AccountInfo:
        """Get account info from Alpaca."""
        try:
            acct = self._trading_client.get_account()
            return AccountInfo(
                cash=float(acct.cash),
                portfolio_value=float(acct.portfolio_value),
                buying_power=float(acct.buying_power),
                equity=float(acct.equity),
                currency="USD",
                positions=self.get_positions(),
                day_trade_count=int(acct.daytrade_count),
            )
        except Exception as e:
            logger.error(f"Get account failed: {e}")
            return AccountInfo(
                cash=0, portfolio_value=0, buying_power=0, equity=0
            )

    # ── Market Data ───────────────────────────────────────────────

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Fetch latest price via Alpaca data API."""
        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self._data_client.get_stock_latest_quote(req)
            quote = quotes.get(symbol)
            if quote:
                return float(quote.ask_price)
        except Exception as e:
            logger.error(f"Latest price failed for {symbol}: {e}")
        return None

    def get_latest_bar(self, symbol: str) -> Optional[dict]:
        """Fetch latest OHLCV bar via Alpaca data API."""
        try:
            from alpaca.data.requests import StockLatestBarRequest

            req = StockLatestBarRequest(symbol_or_symbols=symbol)
            bars = self._data_client.get_stock_latest_bar(req)
            bar = bars.get(symbol)
            if bar:
                return {
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                    "timestamp": bar.timestamp,
                }
        except Exception as e:
            logger.error(f"Latest bar failed for {symbol}: {e}")
        return None
