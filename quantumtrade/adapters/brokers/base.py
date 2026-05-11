"""
Abstract base class for all broker integrations.

Every broker (Alpaca, Binance, Paper) MUST implement this interface so the
rest of the system can swap brokers without changing any business logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

# Import metrics (optional)
try:
    from monitoring.metrics import (
        ORDERS_SUBMITTED_TOTAL,
        ORDERS_FILLED_TOTAL,
        ORDER_LATENCY_SECONDS,
        BROKER_CONNECTION_STATUS,
        BROKER_ORDERS_IN_FLIGHT,
        track_latency,
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


# ───────────────────────────── Enums ─────────────────────────────

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(str, Enum):
    DAY = "DAY"          # Cancel at end of trading day
    GTC = "GTC"          # Good 'til cancelled
    IOC = "IOC"          # Immediate or cancel
    FOK = "FOK"          # Fill or kill


# ───────────────────────────── Data Classes ──────────────────────

@dataclass
class BrokerOrder:
    """Standardised order request sent to any broker."""
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    client_order_id: Optional[str] = None


@dataclass
class OrderResult:
    """Standardised response from any broker after placing an order."""
    order_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    quantity: float
    filled_quantity: float = 0.0
    filled_price: Optional[float] = None
    commission: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    raw_response: Optional[dict] = None   # Broker-specific raw data

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def is_rejected(self) -> bool:
        return self.status == OrderStatus.REJECTED


@dataclass
class Position:
    """Current open position for a symbol."""
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float = 0.0
    unrealised_pnl: float = 0.0
    market_value: float = 0.0
    side: str = "long"

    @property
    def pnl_pct(self) -> float:
        if self.avg_entry_price == 0:
            return 0.0
        return ((self.current_price - self.avg_entry_price)
                / self.avg_entry_price) * 100


@dataclass
class AccountInfo:
    """Snapshot of the brokerage account."""
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float
    currency: str = "USD"
    positions: List[Position] = field(default_factory=list)
    day_trade_count: int = 0


# ───────────────────────────── Abstract Base ─────────────────────

class BaseBroker(ABC):
    """
    Interface that every broker adapter must implement.

    Methods marked @abstractmethod are **required**.
    Concrete brokers can override the optional helpers too.
    """

    def __init__(self, paper: bool = True):
        self.paper = paper
        self._connected = False

    # ── Connection ────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Authenticate and establish connection. Return True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly close connection."""
        ...

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Orders ────────────────────────────────────────────────────

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> OrderResult:
        """Submit an order to the exchange/broker."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Return True on success."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[OrderResult]:
        """Retrieve current state of an order by its ID."""
        ...

    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """List open (unfilled) orders, optionally filtered by symbol."""
        return []

    # ── Positions & Account ───────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all current open positions."""
        ...

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """Return current account info (balance, equity, etc.)."""
        ...

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol, or None."""
        for pos in self.get_positions():
            if pos.symbol == symbol:
                return pos
        return None

    # ── Market Data (optional — brokers that provide it) ──────────

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Fetch the latest price for a symbol. Not all brokers support this."""
        return None

    def get_latest_bar(self, symbol: str) -> Optional[dict]:
        """Fetch the latest OHLCV bar. Not all brokers support this."""
        return None

    # ── Helpers ───────────────────────────────────────────────────

    def __repr__(self) -> str:
        mode = "PAPER" if self.paper else "LIVE"
        connected = "connected" if self._connected else "disconnected"
        return f"<{self.__class__.__name__} mode={mode} {connected}>"
