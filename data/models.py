from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import pandas as pd

@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Trade:
    symbol: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 0.0
    entry_time: datetime = datetime.now()
    exit_time: Optional[datetime] = None
    pnl: float = 0.0
    status: str = "OPEN"  # 'OPEN', 'CLOSED'

def candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    df = pd.DataFrame([c.__dict__ for c in candles])
    if not df.empty:
        df.set_index('timestamp', inplace=True)
    return df
