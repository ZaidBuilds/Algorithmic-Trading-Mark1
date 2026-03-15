"""
Binance Broker Integration — Real Crypto Trading.

Binance is the world's largest cryptocurrency exchange by volume.
This adapter supports:
  - Spot trading (BUY / SELL)
  - Market, Limit, and Stop-Limit orders
  - Testnet (paper) and Production (live) modes
  - Account balance & position tracking
  - Real-time price quotes

Setup:
  1. Create account at https://www.binance.com
  2. Enable API access in the dashboard
  3. For testnet: https://testnet.binance.vision
  4. Set in .env:
     BINANCE_API_KEY=your_key
     BINANCE_API_SECRET=your_secret
     BINANCE_TESTNET=true
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from .base import (
    BaseBroker, BrokerOrder, OrderResult, Position, AccountInfo,
    OrderSide, OrderType, OrderStatus, TimeInForce,
)

logger = logging.getLogger(__name__)

# Binance testnet base URL
BINANCE_TESTNET_URL = "https://testnet.binance.vision/api"


class BinanceBroker(BaseBroker):
    """
    Production broker adapter for Binance exchange.

    Supports testnet (paper) and mainnet (live) trading.
    Uses python-binance SDK.
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
        self._client = None

    # ── Connection ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to Binance using python-binance SDK."""
        try:
            from binance.client import Client

            if self.paper:
                self._client = Client(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=True,
                )
                logger.info("🔗 Binance TESTNET connected")
            else:
                self._client = Client(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                )
                logger.info("🔗 Binance MAINNET connected")

            # Verify connection
            account = self._client.get_account()
            if account.get("canTrade"):
                self._connected = True
                logger.info("✅ Binance connection verified — trading enabled")
                return True
            else:
                logger.error("Binance account cannot trade")
                return False

        except ImportError:
            logger.error(
                "python-binance not installed. Run: pip install python-binance"
            )
            return False
        except Exception as e:
            logger.error(f"Binance connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Binance."""
        self._client = None
        self._connected = False
        logger.info("Binance disconnected")

    # ── Orders ────────────────────────────────────────────────────

    def place_order(self, order: BrokerOrder) -> OrderResult:
        """Place an order on Binance."""
        if not self._connected or not self._client:
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                status=OrderStatus.REJECTED, quantity=order.quantity,
                raw_response={"error": "Not connected"},
            )

        try:
            from binance.enums import (
                SIDE_BUY, SIDE_SELL,
                ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT, ORDER_TYPE_STOP_LOSS_LIMIT,
                TIME_IN_FORCE_GTC,
            )

            side = SIDE_BUY if order.side == OrderSide.BUY else SIDE_SELL

            # Normalise symbol (Binance uses BTCUSDT, not BTC/USDT)
            symbol = order.symbol.replace("/", "")

            if order.order_type == OrderType.MARKET:
                result = self._client.create_order(
                    symbol=symbol,
                    side=side,
                    type=ORDER_TYPE_MARKET,
                    quantity=order.quantity,
                )
            elif order.order_type == OrderType.LIMIT:
                result = self._client.create_order(
                    symbol=symbol,
                    side=side,
                    type=ORDER_TYPE_LIMIT,
                    timeInForce=TIME_IN_FORCE_GTC,
                    quantity=order.quantity,
                    price=str(order.limit_price),
                )
            elif order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
                result = self._client.create_order(
                    symbol=symbol,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS_LIMIT,
                    timeInForce=TIME_IN_FORCE_GTC,
                    quantity=order.quantity,
                    price=str(order.limit_price or order.stop_price),
                    stopPrice=str(order.stop_price),
                )
            else:
                raise ValueError(f"Unsupported order type: {order.order_type}")

            # Parse Binance response
            status_map = {
                "NEW": OrderStatus.SUBMITTED,
                "FILLED": OrderStatus.FILLED,
                "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
                "CANCELED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "EXPIRED": OrderStatus.EXPIRED,
            }

            # Calculate filled price from fills array
            fills = result.get("fills", [])
            filled_price = None
            if fills:
                total_qty = sum(float(f["qty"]) for f in fills)
                total_cost = sum(float(f["qty"]) * float(f["price"]) for f in fills)
                filled_price = total_cost / total_qty if total_qty > 0 else None

            total_commission = sum(float(f.get("commission", 0)) for f in fills)

            order_result = OrderResult(
                order_id=str(result["orderId"]),
                symbol=order.symbol,
                side=order.side,
                status=status_map.get(result["status"], OrderStatus.PENDING),
                quantity=float(result["origQty"]),
                filled_quantity=float(result["executedQty"]),
                filled_price=filled_price,
                commission=total_commission,
                timestamp=datetime.now(),
                raw_response=result,
            )

            logger.info(
                f"📝 Binance order placed: {order.side.value} "
                f"{order.quantity} {order.symbol} → {order_result.status.value}"
            )
            return order_result

        except Exception as e:
            logger.error(f"Binance order failed: {e}")
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                status=OrderStatus.REJECTED, quantity=order.quantity,
                raw_response={"error": str(e)},
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open Binance order."""
        try:
            # Binance requires symbol + orderId for cancellation
            # We store raw_response on place, but for a direct cancel we need symbol
            # This is a simplified version — production would track symbol→orderId mapping
            logger.warning(
                "Binance cancel requires symbol. Use cancel_order_by_symbol() instead."
            )
            return False
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    def cancel_order_by_symbol(self, symbol: str, order_id: str) -> bool:
        """Cancel a Binance order with both symbol and order ID."""
        try:
            symbol_clean = symbol.replace("/", "")
            self._client.cancel_order(
                symbol=symbol_clean, orderId=int(order_id)
            )
            logger.info(f"❌ Binance order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[OrderResult]:
        """Get order status — requires symbol for Binance."""
        logger.warning("Binance get_order requires symbol. Not implemented in base interface.")
        return None

    # ── Positions & Account ───────────────────────────────────────

    def get_positions(self) -> List[Position]:
        """Get all non-zero balances from Binance as positions."""
        try:
            account = self._client.get_account()
            positions = []

            for balance in account.get("balances", []):
                free = float(balance["free"])
                locked = float(balance["locked"])
                total = free + locked

                if total > 0.0 and balance["asset"] != "USDT":
                    # Try to get current price
                    symbol = f"{balance['asset']}USDT"
                    try:
                        ticker = self._client.get_symbol_ticker(symbol=symbol)
                        current_price = float(ticker["price"])
                    except Exception:
                        current_price = 0.0

                    positions.append(Position(
                        symbol=f"{balance['asset']}/USDT",
                        quantity=total,
                        avg_entry_price=0.0,  # Binance doesn't track this natively
                        current_price=current_price,
                        market_value=total * current_price,
                        side="long",
                    ))

            return positions
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []

    def get_account(self) -> AccountInfo:
        """Get account info from Binance."""
        try:
            account = self._client.get_account()
            balances = account.get("balances", [])

            # Find USDT balance as "cash"
            usdt_balance = 0.0
            for b in balances:
                if b["asset"] == "USDT":
                    usdt_balance = float(b["free"]) + float(b["locked"])

            positions = self.get_positions()
            portfolio_value = usdt_balance + sum(
                p.market_value for p in positions
            )

            return AccountInfo(
                cash=usdt_balance,
                portfolio_value=portfolio_value,
                buying_power=usdt_balance,
                equity=portfolio_value,
                currency="USDT",
                positions=positions,
            )
        except Exception as e:
            logger.error(f"Get account failed: {e}")
            return AccountInfo(
                cash=0, portfolio_value=0, buying_power=0, equity=0
            )

    # ── Market Data ───────────────────────────────────────────────

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Fetch latest price from Binance."""
        try:
            symbol_clean = symbol.replace("/", "")
            ticker = self._client.get_symbol_ticker(symbol=symbol_clean)
            return float(ticker["price"])
        except Exception as e:
            logger.error(f"Price fetch failed for {symbol}: {e}")
            return None

    def get_latest_bar(self, symbol: str) -> Optional[dict]:
        """Fetch latest kline (OHLCV) from Binance."""
        try:
            from binance.enums import KLINE_INTERVAL_1DAY

            symbol_clean = symbol.replace("/", "")
            klines = self._client.get_klines(
                symbol=symbol_clean,
                interval=KLINE_INTERVAL_1DAY,
                limit=1,
            )
            if klines:
                k = klines[0]
                return {
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "timestamp": datetime.fromtimestamp(k[0] / 1000),
                }
        except Exception as e:
            logger.error(f"Bar fetch failed for {symbol}: {e}")
        return None
