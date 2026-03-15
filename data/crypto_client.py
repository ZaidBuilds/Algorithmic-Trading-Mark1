import pandas as pd
from typing import Optional
from monitoring.logger import logger
from .base_client import BaseDataClient

class CryptoDataClient(BaseDataClient):
    def __init__(self):
        try:
            import ccxt
            self.exchange = ccxt.binance()
        except ImportError:
            logger.error("CCXT not installed. Crypto features disabled.")
            self.exchange = None

    def fetch_ohlcv(self, symbol: str, timeframe: str, start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
        if not self.exchange:
            return pd.DataFrame()
            
        logger.info(f"Fetching Crypto {symbol} from Binance...")
        try:
            since = self.exchange.parse8601(f"{start_date}T00:00:00Z")
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error fetching Crypto data: {e}")
            return pd.DataFrame()
