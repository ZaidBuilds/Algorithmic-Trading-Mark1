"""
WebSocket Price Streamer — Real-time price feeds.

Instead of polling yfinance every 5 minutes, this streams
live prices directly from exchanges.

Supported sources:
  - Binance WebSocket (crypto)
  - Alpaca WebSocket (US stocks)
  - Fallback: yfinance polling

Usage:
    from data.price_stream import PriceStreamer
    streamer = PriceStreamer(source="binance")
    streamer.on_price(callback)
    streamer.subscribe(["BTCUSDT", "ETHUSDT"])
    streamer.start()
"""

import logging
import json
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PriceTick:
    """A single price update."""
    symbol: str
    price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class PriceStreamer:
    """
    Real-time price streaming from multiple sources.

    Automatically selects the best data source based on
    the symbols you subscribe to.
    """

    def __init__(self, source: str = "auto"):
        """
        Args:
            source: "binance", "alpaca", "polling", or "auto"
        """
        self.source = source
        self._callbacks: List[Callable] = []
        self._subscribed: List[str] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_prices: Dict[str, PriceTick] = {}

    # ── Subscription ──────────────────────────────────────────────

    def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to price updates for symbols."""
        self._subscribed.extend(symbols)
        logger.info(f"📡 Subscribed to: {symbols}")

    def on_price(self, callback: Callable[[PriceTick], None]) -> None:
        """Register a callback for price updates."""
        self._callbacks.append(callback)

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        """Start streaming prices in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
        logger.info(f"📡 Price streamer started (source: {self.source})")

    def stop(self) -> None:
        """Stop streaming."""
        self._running = False
        logger.info("📡 Price streamer stopped")

    # ── Data Access ───────────────────────────────────────────────

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get the last known price for a symbol."""
        tick = self._latest_prices.get(symbol)
        return tick.price if tick else None

    def get_all_prices(self) -> Dict[str, float]:
        """Get all latest prices as {symbol: price}."""
        return {s: t.price for s, t in self._latest_prices.items()}

    # ── Internal Streaming ────────────────────────────────────────

    def _stream_loop(self) -> None:
        """Main streaming loop — selects source and runs."""
        source = self._detect_source() if self.source == "auto" else self.source

        if source == "binance":
            self._stream_binance()
        elif source == "alpaca":
            self._stream_alpaca()
        else:
            self._stream_polling()

    def _detect_source(self) -> str:
        """Auto-detect the best source based on subscribed symbols."""
        crypto_suffixes = ("USDT", "BTC", "ETH", "BNB", "BUSD")
        is_crypto = any(
            s.upper().endswith(crypto_suffixes) for s in self._subscribed
        )
        return "binance" if is_crypto else "polling"

    # ── Binance WebSocket ─────────────────────────────────────────

    def _stream_binance(self) -> None:
        """Stream prices from Binance WebSocket."""
        try:
            import websocket
        except ImportError:
            logger.warning("websocket-client not installed, falling back to polling")
            self._stream_polling()
            return

        streams = [f"{s.lower()}@trade" for s in self._subscribed]
        url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if "data" in data:
                    trade = data["data"]
                    tick = PriceTick(
                        symbol=trade["s"],
                        price=float(trade["p"]),
                        volume=float(trade["q"]),
                    )
                    self._process_tick(tick)
            except Exception as e:
                logger.error(f"Binance WS parse error: {e}")

        def on_error(ws, error):
            logger.error(f"Binance WS error: {error}")

        def on_close(ws, close_status, close_msg):
            logger.info("Binance WS closed")
            if self._running:
                time.sleep(5)
                self._stream_binance()  # Reconnect

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        logger.info(f"📡 Connecting to Binance WebSocket ({len(streams)} streams)")
        ws.run_forever()

    # ── Alpaca WebSocket ──────────────────────────────────────────

    def _stream_alpaca(self) -> None:
        """Stream prices from Alpaca WebSocket."""
        try:
            from alpaca.data.live import StockDataStream
            from config.settings import settings

            stream = StockDataStream(
                settings.ALPACA_API_KEY or "",
                settings.ALPACA_API_SECRET or "",
            )

            async def on_trade(trade):
                tick = PriceTick(
                    symbol=trade.symbol,
                    price=float(trade.price),
                    volume=float(trade.size),
                )
                self._process_tick(tick)

            for symbol in self._subscribed:
                stream.subscribe_trades(on_trade, symbol)

            logger.info(f"📡 Connecting to Alpaca WebSocket")
            stream.run()

        except ImportError:
            logger.warning("alpaca-py not installed, falling back to polling")
            self._stream_polling()
        except Exception as e:
            logger.error(f"Alpaca WS error: {e}")
            self._stream_polling()

    # ── Polling Fallback ──────────────────────────────────────────

    def _stream_polling(self, interval: float = 30.0) -> None:
        """Fallback: Poll yfinance for prices every N seconds."""
        logger.info(f"📡 Polling mode (every {interval}s)")

        while self._running:
            try:
                import yfinance as yf

                for symbol in self._subscribed:
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.fast_info
                        price = info.get("lastPrice", 0) or info.get("regularMarketPrice", 0)

                        if price and price > 0:
                            tick = PriceTick(symbol=symbol, price=float(price))
                            self._process_tick(tick)
                    except Exception as e:
                        logger.debug(f"Poll error for {symbol}: {e}")

            except ImportError:
                logger.error("yfinance not installed")
                break
            except Exception as e:
                logger.error(f"Polling error: {e}")

            time.sleep(interval)

    # ── Tick Processing ───────────────────────────────────────────

    def _process_tick(self, tick: PriceTick) -> None:
        """Process an incoming price tick."""
        self._latest_prices[tick.symbol] = tick

        # Fire callbacks
        for cb in self._callbacks:
            try:
                cb(tick)
            except Exception as e:
                logger.error(f"Price callback error: {e}")
