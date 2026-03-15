"""
Data validation module for checking data quality and handling missing values.

This module ensures data integrity by:
- Detecting missing values
- Identifying gaps in time series
- Validating data ranges (negative prices, etc.)
- Handling missing data safely (forward fill, interpolation, or removal)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validate and clean market data.
    
    Why validation matters:
    -----------------------
    1. Prevents trading on bad data (missing candles, incorrect prices)
    2. Identifies data quality issues early
    3. Ensures backtests reflect reality (gaps can affect results)
    4. Prevents crashes from NaN values in calculations
    """
    
    # Required columns for OHLCV data
    REQUIRED_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    def __init__(self):
        """Initialize the DataValidator."""
        self.logger = logger
    
    def validate_structure(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate that DataFrame has required structure.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check if DataFrame is empty
        if df.empty:
            errors.append("DataFrame is empty")
            return False, errors
        
        # Check required columns
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            errors.append(f"Missing required columns: {missing_cols}")
        
        # Check if index is DatetimeIndex (preferred for time series)
        if not isinstance(df.index, pd.DatetimeIndex):
            errors.append(f"Index is not DatetimeIndex (type: {type(df.index)})")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def check_missing_values(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        Count missing values in each column.
        
        Args:
            df: DataFrame to check
            
        Returns:
            Dictionary mapping column names to count of missing values
        """
        missing = df.isnull().sum().to_dict()
        
        if any(missing.values()):
            self.logger.warning(f"Missing values detected: {missing}")
        else:
            self.logger.debug("No missing values found")
        
        return missing
    
    def check_data_ranges(self, df: pd.DataFrame) -> List[str]:
        """
        Check for invalid data ranges (negative prices, high > low, etc.).
        
        Args:
            df: DataFrame to validate
            
        Returns:
            List of error messages (empty if no errors)
        """
        errors = []
        
        # Check for negative prices
        price_cols = ['Open', 'High', 'Low', 'Close']
        for col in price_cols:
            if col in df.columns:
                negative_count = (df[col] < 0).sum()
                if negative_count > 0:
                    errors.append(f"{col}: {negative_count} negative values found")
        
        # Check OHLC relationships: High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close
        if all(col in df.columns for col in ['Open', 'High', 'Low', 'Close']):
            invalid_high_low = (df['High'] < df['Low']).sum()
            if invalid_high_low > 0:
                errors.append(f"High < Low: {invalid_high_low} invalid rows")
            
            invalid_high_open = (df['High'] < df['Open']).sum()
            if invalid_high_open > 0:
                errors.append(f"High < Open: {invalid_high_open} invalid rows")
            
            invalid_high_close = (df['High'] < df['Close']).sum()
            if invalid_high_close > 0:
                errors.append(f"High < Close: {invalid_high_close} invalid rows")
            
            invalid_low_open = (df['Low'] > df['Open']).sum()
            if invalid_low_open > 0:
                errors.append(f"Low > Open: {invalid_low_open} invalid rows")
            
            invalid_low_close = (df['Low'] > df['Close']).sum()
            if invalid_low_close > 0:
                errors.append(f"Low > Close: {invalid_low_close} invalid rows")
        
        # Check for zero volume (might be valid for some assets, but worth flagging)
        if 'Volume' in df.columns:
            zero_volume = (df['Volume'] == 0).sum()
            if zero_volume > 0:
                self.logger.warning(f"Zero volume detected in {zero_volume} rows")
        
        if errors:
            self.logger.warning(f"Data range errors: {errors}")
        else:
            self.logger.debug("Data range validation passed")
        
        return errors
    
    def check_time_gaps(
        self, 
        df: pd.DataFrame, 
        expected_freq: Optional[str] = None
    ) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """
        Detect gaps in time series data.
        
        Args:
            df: DataFrame with DatetimeIndex
            expected_freq: Expected frequency (e.g., '1D' for daily, '1H' for hourly)
                          If None, tries to infer from data
        
        Returns:
            List of tuples (gap_start, gap_end) representing gaps
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            self.logger.warning("Cannot check time gaps: index is not DatetimeIndex")
            return []
        
        # Infer frequency if not provided
        if expected_freq is None:
            # Try to infer from first few intervals
            if len(df) > 1:
                intervals = df.index.to_series().diff().dropna()
                most_common_interval = intervals.mode()[0] if len(intervals.mode()) > 0 else None
                if most_common_interval is not None:
                    expected_freq = pd.infer_freq(df.index[:min(10, len(df))])
        
        if expected_freq:
            # Generate expected date range
            expected_dates = pd.date_range(
                start=df.index[0],
                end=df.index[-1],
                freq=expected_freq
            )
            # Find missing dates
            missing_dates = expected_dates.difference(df.index)
            
            if len(missing_dates) > 0:
                self.logger.warning(f"Found {len(missing_dates)} missing time periods")
                # Group consecutive missing dates
                gaps = []
                gap_start = None
                for date in missing_dates:
                    if gap_start is None:
                        gap_start = date
                    gap_end = date
                if gap_start is not None:
                    gaps.append((gap_start, gap_end))
                return gaps
        
        self.logger.debug("No significant time gaps detected")
        return []
    
    def handle_missing_values(
        self,
        df: pd.DataFrame,
        method: str = 'forward_fill',
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Handle missing values using various strategies.
        
        Args:
            df: DataFrame with potential missing values
            method: Method to use ('forward_fill', 'backward_fill', 'interpolate', 'drop')
            limit: Maximum number of consecutive missing values to fill (None = no limit)
        
        Returns:
            DataFrame with missing values handled
        
        Methods:
            - forward_fill: Use last valid value (good for price data)
            - backward_fill: Use next valid value
            - interpolate: Linear interpolation (use with caution for prices)
            - drop: Remove rows with any missing values
        
        Why forward_fill for prices?
        -----------------------------
        In trading, if a candle is missing, we typically use the last known price
        (forward fill) rather than interpolating, because interpolation creates
        "fake" prices that never existed. This prevents look-ahead bias.
        """
        df_cleaned = df.copy()
        
        missing_before = df_cleaned.isnull().sum().sum()
        
        if missing_before == 0:
            self.logger.debug("No missing values to handle")
            return df_cleaned
        
        if method == 'forward_fill':
            df_cleaned = df_cleaned.ffill(limit=limit)
            self.logger.info(f"Forward filled {missing_before} missing values")
        
        elif method == 'backward_fill':
            df_cleaned = df_cleaned.bfill(limit=limit)
            self.logger.info(f"Backward filled {missing_before} missing values")
        
        elif method == 'interpolate':
            df_cleaned = df_cleaned.interpolate(method='linear', limit=limit)
            self.logger.info(f"Interpolated {missing_before} missing values")
            self.logger.warning("Interpolation creates synthetic prices - use with caution")
        
        elif method == 'drop':
            df_cleaned = df_cleaned.dropna()
            self.logger.info(f"Dropped rows with missing values ({missing_before} missing values)")
        
        else:
            raise ValueError(f"Unknown method: {method}. Use 'forward_fill', 'backward_fill', 'interpolate', or 'drop'")
        
        missing_after = df_cleaned.isnull().sum().sum()
        if missing_after > 0:
            self.logger.warning(f"Still {missing_after} missing values after handling")
        
        return df_cleaned
    
    def validate(self, df: pd.DataFrame, handle_missing: bool = True) -> Tuple[bool, pd.DataFrame, List[str]]:
        """
        Complete validation pipeline: structure → missing values → data ranges → time gaps.
        
        Args:
            df: DataFrame to validate
            handle_missing: If True, automatically handle missing values with forward_fill
        
        Returns:
            Tuple of (is_valid, cleaned_dataframe, list_of_warnings)
        """
        warnings = []
        
        # 1. Validate structure
        is_valid, errors = self.validate_structure(df)
        if not is_valid:
            warnings.extend(errors)
            return False, df, warnings
        
        # 2. Check missing values
        missing = self.check_missing_values(df)
        if any(missing.values()):
            if handle_missing:
                df = self.handle_missing_values(df, method='forward_fill')
                warnings.append(f"Handled missing values using forward_fill")
            else:
                warnings.append(f"Missing values detected: {missing}")
        
        # 3. Check data ranges
        range_errors = self.check_data_ranges(df)
        warnings.extend(range_errors)
        
        # 4. Check time gaps (informational, not blocking)
        gaps = self.check_time_gaps(df)
        if gaps:
            warnings.append(f"Time gaps detected: {len(gaps)} gaps")
        
        # Data is valid if structure is correct (warnings are non-blocking)
        is_valid = len([w for w in warnings if 'Missing required columns' in w]) == 0
        
        if is_valid and not warnings:
            self.logger.info("Data validation passed with no warnings")
        elif is_valid:
            self.logger.info(f"Data validation passed with {len(warnings)} warnings")
        else:
            self.logger.error(f"Data validation failed: {warnings}")
        
        return is_valid, df, warnings

