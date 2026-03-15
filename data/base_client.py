import pandas as pd
from abc import ABC, abstractmethod
from typing import Optional

class BaseDataClient(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
        pass
