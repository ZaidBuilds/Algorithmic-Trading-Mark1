"""
Data loader module for fetching market data from various sources.

This module handles:
- Loading CSV files with OHLCV data
- Fetching data from Yahoo Finance using yfinance
- Normalizing data to consistent pandas DataFrame format
"""

import pandas as pd
import yfinance as yf
from pathlib import Path
from typing import Optional, Union
import logging

# Set up logger
logger = logging.getLogger(__name__)


class DataLoader:
    """
    Load market data from CSV files or Yahoo Finance.
    
    Why Pandas?
    -----------
    Pandas DataFrames are the industry standard for financial data analysis because:
    1. Efficient handling of time-series data with datetime indices
    2. Built-in methods for financial calculations (rolling windows, shifts, etc.)
    3. Easy data manipulation (filtering, grouping, joining)
    4. Integration with other libraries (NumPy, Matplotlib, etc.)
    5. Memory-efficient for large datasets
    
    Data Flow:
    ----------
    CSV/Yahoo Finance → pandas DataFrame → Strategy/Backtest Engine
    The DataFrame format ensures all downstream components receive data in a
    consistent, predictable format.
    """
    
    # Expected column names for CSV files
    CSV_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    def __init__(self):
        """Initialize the DataLoader."""
        self.logger = logger
    
    def load_csv(
        self, 
        file_path: Union[str, Path],
        date_column: str = 'Date',
        index_date: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Load OHLCV data from a CSV file.
        
        Args:
            file_path: Path to CSV file
            date_column: Name of the date column (default: 'Date')
            index_date: If True, set date column as DataFrame index
            
        Returns:
            pandas DataFrame with columns: Open, High, Low, Close, Volume
            Index will be datetime if index_date=True, else RangeIndex
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If required columns are missing
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            self.logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            # Read CSV file
            df = pd.read_csv(file_path)
            self.logger.info(f"Loaded CSV file: {file_path} ({len(df)} rows)")
            
            # Convert date column to datetime if it exists
            if date_column in df.columns:
                df[date_column] = pd.to_datetime(df[date_column])
                
                # Set as index if requested
                if index_date:
                    df.set_index(date_column, inplace=True)
                    self.logger.debug(f"Set '{date_column}' as index")
            else:
                self.logger.warning(f"Date column '{date_column}' not found. Using default index.")
            
            # Normalize column names (handle case variations)
            df.columns = df.columns.str.strip()  # Remove whitespace
            df.columns = df.columns.str.title()  # Capitalize first letter
            
            # Validate required columns exist
            missing_cols = [col for col in self.CSV_COLUMNS if col not in df.columns]
            if missing_cols:
                raise ValueError(
                    f"Missing required columns: {missing_cols}. "
                    f"Found columns: {list(df.columns)}"
                )
            
            # Select only OHLCV columns (in case there are extra columns)
            df = df[self.CSV_COLUMNS].copy()
            
            # Ensure numeric types
            for col in self.CSV_COLUMNS:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Sort by index (date) if it's a datetime index
            if isinstance(df.index, pd.DatetimeIndex):
                df.sort_index(inplace=True)
            
            self.logger.info(f"Successfully loaded {len(df)} rows of OHLCV data")
            return df
            
        except Exception as e:
            self.logger.error(f"Error loading CSV file {file_path}: {e}")
            raise
    
    def load_yahoo(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = None,
        interval: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data from Yahoo Finance using yfinance.
        
        Args:
            symbol: Stock/crypto symbol (e.g., 'AAPL', 'BTC-USD')
            start_date: Start date in 'YYYY-MM-DD' format (optional)
            end_date: End date in 'YYYY-MM-DD' format (optional)
            period: Time period (e.g., '1mo', '3mo', '1y', 'max'). Used if dates not provided
            interval: Data interval ('1m', '5m', '15m', '1h', '1d', '1wk', '1mo')
        
        Returns:
            pandas DataFrame with columns: Open, High, Low, Close, Volume
            Index is DatetimeIndex
            
        Notes:
            - Either (start_date, end_date) OR period should be provided
            - If both provided, dates take precedence
            - yfinance returns data with DatetimeIndex automatically
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Fetch data based on parameters
            if start_date and end_date:
                self.logger.info(f"Fetching {symbol} from {start_date} to {end_date} (interval: {interval})")
                df = ticker.history(start=start_date, end=end_date, interval=interval)
            elif period:
                self.logger.info(f"Fetching {symbol} for period: {period} (interval: {interval})")
                df = ticker.history(period=period, interval=interval)
            else:
                # Default: 1 year of daily data
                self.logger.info(f"Fetching {symbol} for default period: 1y (interval: {interval})")
                df = ticker.history(period='1y', interval=interval)
            
            if df.empty:
                self.logger.warning(f"No data returned for symbol: {symbol}")
                return None
            
            # yfinance returns data with DatetimeIndex and OHLCV columns
            # Verify we have the expected columns
            expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in expected_cols):
                self.logger.error(f"Unexpected columns from yfinance: {df.columns}")
                return None
            
            # Select only OHLCV columns (remove Dividends, Stock Splits if present)
            df = df[expected_cols].copy()
            
            # Sort by date (should already be sorted, but ensure it)
            df.sort_index(inplace=True)
            
            self.logger.info(
                f"Successfully fetched {len(df)} rows for {symbol} "
                f"({df.index[0]} to {df.index[-1]})"
            )
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching data from Yahoo Finance for {symbol}: {e}")
            return None
    
    def load(
        self,
        source: Union[str, Path],
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """
        Load data from either CSV file or Yahoo Finance.
        
        Args:
            source: File path (str/Path) or symbol (str)
            **kwargs: Additional arguments passed to load_csv or load_yahoo
        
        Returns:
            pandas DataFrame with OHLCV data
            
        Examples:
            # Load from CSV
            loader.load('data/AAPL.csv')
            
            # Load from Yahoo Finance
            loader.load('AAPL', start_date='2023-01-01', end_date='2023-12-31')
            loader.load('BTC-USD', period='6mo')
        """
        source_str = str(source)
        
        # Check if it's a file path
        if Path(source_str).exists() or source_str.endswith('.csv'):
            return self.load_csv(source_str, **kwargs)
        else:
            # Assume it's a Yahoo Finance symbol
            return self.load_yahoo(source_str, **kwargs)


# Module-level convenience functions for easy importing
_loader_instance = None

def get_loader():
    """Get or create a DataLoader instance."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = DataLoader()
    return _loader_instance

def load_yahoo(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,
    interval: str = '1d'
) -> Optional[pd.DataFrame]:
    """Quick load Yahoo Finance data."""
    return get_loader().load_yahoo(symbol, start_date, end_date, period, interval)

def load_csv(file_path: Union[str, Path], **kwargs) -> Optional[pd.DataFrame]:
    """Quick load CSV data."""
    return get_loader().load_csv(file_path, **kwargs)

def load(source: Union[str, Path], **kwargs) -> Optional[pd.DataFrame]:
    """Quick universal loader - CSV or Yahoo."""
    return get_loader().load(source, **kwargs)
