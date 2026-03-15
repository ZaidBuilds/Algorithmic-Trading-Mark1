"""
Market Hours Utility — Know when markets are open.

Covers:
  - US Stock Market (NYSE / NASDAQ): 9:30 AM – 4:00 PM ET
  - Crypto: 24/7
  - Forex: Sun 5 PM – Fri 5 PM ET (continuous)
  - Pre-market / After-hours windows
"""

import logging
from datetime import datetime, time
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# US Eastern timezone
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


class MarketType(str, Enum):
    STOCKS = "STOCKS"
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"


class MarketSession(str, Enum):
    PRE_MARKET = "PRE_MARKET"       # 4:00 AM – 9:30 AM ET
    REGULAR = "REGULAR"             # 9:30 AM – 4:00 PM ET
    AFTER_HOURS = "AFTER_HOURS"     # 4:00 PM – 8:00 PM ET
    CLOSED = "CLOSED"               # Outside all sessions


# US market holidays (2026) — extend as needed
US_HOLIDAYS = [
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
]


class MarketHours:
    """Utility class for market hours lookup."""

    @staticmethod
    def get_session(
        market: MarketType = MarketType.STOCKS,
        dt: Optional[datetime] = None,
    ) -> MarketSession:
        """
        Determine the current market session.

        Args:
            market: Type of market
            dt: Datetime to check (default: now)

        Returns:
            Current MarketSession enum value
        """
        if market == MarketType.CRYPTO:
            return MarketSession.REGULAR  # 24/7

        now = dt or datetime.now(ET)
        if now.tzinfo is None:
            now = now.replace(tzinfo=ET)
        else:
            now = now.astimezone(ET)

        if market == MarketType.FOREX:
            # Forex: open Sun 5 PM – Fri 5 PM ET
            weekday = now.weekday()  # 0=Mon, 6=Sun
            if weekday == 5:  # Saturday – closed
                return MarketSession.CLOSED
            if weekday == 6 and now.time() < time(17, 0):
                return MarketSession.CLOSED
            if weekday == 4 and now.time() >= time(17, 0):
                return MarketSession.CLOSED
            return MarketSession.REGULAR

        # Stocks
        weekday = now.weekday()
        if weekday >= 5:  # Weekend
            return MarketSession.CLOSED

        date_str = now.strftime("%Y-%m-%d")
        if date_str in US_HOLIDAYS:
            return MarketSession.CLOSED

        current_time = now.time()

        if time(4, 0) <= current_time < time(9, 30):
            return MarketSession.PRE_MARKET
        elif time(9, 30) <= current_time < time(16, 0):
            return MarketSession.REGULAR
        elif time(16, 0) <= current_time < time(20, 0):
            return MarketSession.AFTER_HOURS
        else:
            return MarketSession.CLOSED

    @staticmethod
    def seconds_until_open(market: MarketType = MarketType.STOCKS) -> int:
        """Calculate seconds until the next regular session opens."""
        if market == MarketType.CRYPTO:
            return 0

        now = datetime.now(ET)
        session = MarketHours.get_session(market, now)

        if session == MarketSession.REGULAR:
            return 0

        # Find next weekday 9:30 AM ET
        target = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now.time() >= time(9, 30):
            # Already past open today, look at tomorrow
            from datetime import timedelta
            target += timedelta(days=1)

        # Skip weekends
        while target.weekday() >= 5:
            from datetime import timedelta
            target += timedelta(days=1)

        return max(0, int((target - now).total_seconds()))


def is_market_open(market: MarketType = MarketType.STOCKS) -> bool:
    """Quick check — is the market currently in regular session?"""
    return MarketHours.get_session(market) == MarketSession.REGULAR
