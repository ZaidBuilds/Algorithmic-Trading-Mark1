import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional
from monitoring.logger import logger
from .base_client import BaseDataClient

class StocksDataClient(BaseDataClient):
    def _parse_date(self, date_str: str) -> str:
        """Converts 'X days ago' to YYYY-MM-DD"""
        if "days ago" in date_str:
            days = int(date_str.split()[0])
            date = datetime.now() - timedelta(days=days)
            return date.strftime('%Y-%m-%d')
        return date_str

    def fetch_ohlcv(self, symbol: str, timeframe: str, start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
        start_date = self._parse_date(start_date)
        if end_date:
            end_date = self._parse_date(end_date)
            
        logger.info(f"Fetching {symbol} from YFinance ({start_date} to {end_date or 'now'})...")
        try:
            df = yf.download(symbol, start=start_date, end=end_date, interval=timeframe, progress=False)
            if df.empty:
                return pd.DataFrame()
            
            # Handle MultiIndex and standardize
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df.columns = [col.lower() for col in df.columns]
            df.index.name = 'timestamp'
            
            # Ensure columns are present and clean
            required = ['open', 'high', 'low', 'close', 'volume']
            df = df[required].copy()
            return df
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()
