"""
Simple test script to verify the data layer works correctly.

Run this to test:
    python test_data_layer.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from data.loader import DataLoader
from data.validator import DataValidator
import logging

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_yahoo_loader():
    """Test loading data from Yahoo Finance."""
    print("\n" + "="*60)
    print("TEST 1: Loading data from Yahoo Finance")
    print("="*60)
    
    loader = DataLoader()
    
    # Test 1: Load AAPL data
    print("\nLoading AAPL data (1 year, daily)...")
    df = loader.load_yahoo('AAPL', period='1y', interval='1d')
    
    if df is not None:
        print(f"[OK] Successfully loaded {len(df)} rows")
        print(f"  Date range: {df.index[0]} to {df.index[-1]}")
        print(f"  Columns: {list(df.columns)}")
        print(f"\nFirst few rows:")
        print(df.head())
        print(f"\nLast few rows:")
        print(df.tail())
        return df
    else:
        print("[FAIL] Failed to load data")
        return None

def test_validator(df):
    """Test data validation."""
    print("\n" + "="*60)
    print("TEST 2: Data Validation")
    print("="*60)
    
    validator = DataValidator()
    
    # Run full validation
    is_valid, cleaned_df, warnings = validator.validate(df, handle_missing=True)
    
    print(f"\nValidation result: {'[PASSED]' if is_valid else '[FAILED]'}")
    print(f"Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  - {warning}")
    
    # Check missing values
    missing = validator.check_missing_values(cleaned_df)
    print(f"\nMissing values: {missing}")
    
    # Check data ranges
    range_errors = validator.check_data_ranges(cleaned_df)
    print(f"Data range errors: {len(range_errors)}")
    for error in range_errors:
        print(f"  - {error}")
    
    return cleaned_df

def test_multiple_symbols():
    """Test loading multiple symbols."""
    print("\n" + "="*60)
    print("TEST 3: Loading Multiple Symbols")
    print("="*60)
    
    loader = DataLoader()
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    for symbol in symbols:
        print(f"\nLoading {symbol}...")
        df = loader.load_yahoo(symbol, period='3mo', interval='1d')
        if df is not None:
            print(f"[OK] {symbol}: {len(df)} rows, latest close: ${df['Close'].iloc[-1]:.2f}")
        else:
            print(f"[FAIL] {symbol}: Failed to load")

if __name__ == "__main__":
    print("="*60)
    print("DATA LAYER TEST SUITE")
    print("="*60)
    
    try:
        # Test 1: Load from Yahoo Finance
        df = test_yahoo_loader()
        
        if df is not None:
            # Test 2: Validate data
            cleaned_df = test_validator(df)
            
            # Test 3: Multiple symbols
            test_multiple_symbols()
            
            print("\n" + "="*60)
            print("[OK] ALL TESTS COMPLETED")
            print("="*60)
        else:
            print("\n[FAIL] Tests failed - could not load initial data")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

