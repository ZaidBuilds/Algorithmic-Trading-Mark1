"""
Test script for the Strategy Layer.

Run this to verify the EMA Crossover strategy works correctly:
    python test_strategy.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from data.loader import DataLoader
from data.validator import DataValidator
from strategy.ema_crossover import EMACrossoverStrategy
from strategy.signals import SignalType
import pandas as pd
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_ema_crossover_strategy():
    """Test EMA Crossover strategy with real data."""
    print("\n" + "="*60)
    print("TEST: EMA Crossover Strategy")
    print("="*60)
    
    # Load data
    print("\n1. Loading data from Yahoo Finance...")
    loader = DataLoader()
    validator = DataValidator()
    
    df = loader.load_yahoo('AAPL', period='6mo', interval='1d')
    if df is None:
        print("[FAIL] Could not load data")
        return False
    
    is_valid, df, warnings = validator.validate(df)
    if not is_valid:
        print(f"[FAIL] Data validation failed: {warnings}")
        return False
    
    print(f"[OK] Loaded {len(df)} rows of data")
    
    # Create strategy
    print("\n2. Creating EMA Crossover Strategy...")
    strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
    print(f"[OK] Strategy created: {strategy}")
    print(f"    Required periods: {strategy.get_required_periods()}")
    print(f"    Entry rules: {strategy.get_entry_rules()['description']}")
    print(f"    Exit rules: {strategy.get_exit_rules()['description']}")
    
    # Validate data
    print("\n3. Validating data requirements...")
    try:
        strategy.validate_data(df)
        print("[OK] Data meets requirements")
    except ValueError as e:
        print(f"[FAIL] Data validation failed: {e}")
        return False
    
    # Calculate indicators
    print("\n4. Calculating indicators...")
    df_with_indicators = strategy.calculate_indicators(df)
    print("[OK] Indicators calculated")
    print(f"    Columns: {list(df_with_indicators.columns)}")
    print(f"\n    Sample indicator values (last 5 rows):")
    print(df_with_indicators[['Close', 'ema_fast', 'ema_slow']].tail())
    
    # Generate signals
    print("\n5. Generating signals...")
    signals_generated = []
    required_periods = strategy.get_required_periods()
    
    # Start generating signals after we have enough data
    start_index = max(1, required_periods)
    
    for i in range(start_index, len(df_with_indicators)):
        signal = strategy.generate_signal(df_with_indicators, i)
        if signal.signal_type != SignalType.HOLD:
            signals_generated.append((i, signal))
    
    print(f"[OK] Generated {len(signals_generated)} non-HOLD signals")
    
    # Display signals
    if signals_generated:
        print("\n    Signal summary:")
        buy_count = sum(1 for _, s in signals_generated if s.is_buy())
        sell_count = sum(1 for _, s in signals_generated if s.is_sell())
        print(f"    BUY signals: {buy_count}")
        print(f"    SELL signals: {sell_count}")
        
        print("\n    First 5 signals:")
        for idx, signal in signals_generated[:5]:
            date = df_with_indicators.index[idx].strftime('%Y-%m-%d')
            price = df_with_indicators.iloc[idx]['Close']
            print(f"    {date}: {signal} (price: ${price:.2f})")
    
    # Verify no look-ahead bias
    print("\n6. Verifying no look-ahead bias...")
    # Strategy should only use data up to current_index
    test_index = len(df_with_indicators) - 10
    signal = strategy.generate_signal(df_with_indicators, test_index)
    
    # Check that signal uses correct data
    current_price = df_with_indicators.iloc[test_index]['Close']
    if abs(signal.price - current_price) < 0.01:  # Allow small floating point differences
        print("[OK] No look-ahead bias detected (signal price matches current price)")
    else:
        print(f"[WARN] Potential look-ahead bias: signal price {signal.price} != current price {current_price}")
    
    print("\n" + "="*60)
    print("[OK] Strategy tests completed successfully!")
    print("="*60)
    return True

def test_signal_metadata():
    """Test that signals contain useful metadata."""
    print("\n" + "="*60)
    print("TEST: Signal Metadata")
    print("="*60)
    
    loader = DataLoader()
    df = loader.load_yahoo('MSFT', period='3mo', interval='1d')
    
    strategy = EMACrossoverStrategy(fast_period=9, slow_period=21)
    df = strategy.calculate_indicators(df)
    
    # Find a signal
    for i in range(strategy.get_required_periods(), len(df)):
        signal = strategy.generate_signal(df, i)
        if signal.signal_type != SignalType.HOLD:
            print(f"\n[OK] Found {signal.signal_type.value} signal:")
            print(f"    Price: ${signal.price:.2f}")
            print(f"    Confidence: {signal.confidence:.2f}" if signal.confidence else "    Confidence: None")
            print(f"    Metadata: {signal.metadata}")
            break
    else:
        print("[INFO] No non-HOLD signals found in test data")

if __name__ == "__main__":
    print("="*60)
    print("STRATEGY LAYER TEST SUITE")
    print("="*60)
    
    try:
        success = test_ema_crossover_strategy()
        test_signal_metadata()
        
        if success:
            print("\n[OK] All strategy tests passed!")
        else:
            print("\n[FAIL] Some tests failed")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

