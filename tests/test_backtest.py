"""
Test script for the Backtesting Engine.

Run this to verify the backtesting engine works correctly:
    python test_backtest.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from data.loader import DataLoader
from data.validator import DataValidator
from strategy.ema_crossover import EMACrossoverStrategy
from quantumtrade.backtesting.engine import BacktestEngine
from quantumtrade.backtesting.reporter import BacktestReporter
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_backtest_engine():
    """Test the backtesting engine with EMA crossover strategy."""
    print("\n" + "="*70)
    print("TEST: Backtesting Engine")
    print("="*70)
    
    # Load data
    print("\n1. Loading data...")
    loader = DataLoader()
    validator = DataValidator()
    
    df = loader.load_yahoo('AAPL', period='1y', interval='1d')
    if df is None:
        print("[FAIL] Could not load data")
        return False
    
    is_valid, df, warnings = validator.validate(df)
    if not is_valid:
        print(f"[FAIL] Data validation failed: {warnings}")
        return False
    
    print(f"[OK] Loaded {len(df)} rows of data")
    print(f"     Date range: {df.index[0].date()} to {df.index[-1].date()}")
    
    # Create strategy
    print("\n2. Creating strategy...")
    strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
    print(f"[OK] Strategy: {strategy.name}")
    print(f"     Fast EMA: {strategy.fast_period}, Slow EMA: {strategy.slow_period}")
    
    # Create backtest engine
    print("\n3. Creating backtest engine...")
    initial_balance = 10000.0
    engine = BacktestEngine(initial_balance=initial_balance, commission=0.001)
    print(f"[OK] Initial balance: ${initial_balance:,.2f}")
    print(f"     Commission: {engine.commission * 100:.2f}%")
    
    # Run backtest
    print("\n4. Running backtest...")
    metrics = engine.run(strategy, df)
    print(f"[OK] Backtest complete")
    
    # Display results
    print("\n5. Backtest Results:")
    print("-" * 70)
    
    summary = metrics.get_summary()
    total_return = summary['total_return']
    win_rate = summary['win_rate']
    
    print(f"Final Balance:       ${summary['final_balance']:,.2f}")
    print(f"Total Return:        ${total_return['absolute']:,.2f} ({total_return['percent']:.2f}%)")
    print(f"Total Trades:        {win_rate['total_trades']}")
    print(f"Win Rate:            {win_rate['win_rate']:.2f}%")
    print(f"Profit Factor:       {summary['profit_factor']:.2f}")
    print(f"Sharpe Ratio:        {summary['sharpe_ratio']:.2f}")
    
    max_dd = summary['max_drawdown']
    print(f"Max Drawdown:        ${max_dd['absolute']:,.2f} ({max_dd['percent']:.2f}%)")
    
    # Show trade details if we have trades
    if len(metrics.trades) > 0:
        print(f"\n6. Sample Trades (first 5):")
        print("-" * 70)
        for i, trade in enumerate(metrics.trades[:5], 1):
            result = "WIN" if trade.is_winning() else "LOSS"
            print(f"{i}. {result}: {trade.quantity:.2f} shares @ ${trade.entry_price:.2f} -> ${trade.exit_price:.2f}")
            print(f"   P&L: ${trade.pnl:.2f} ({trade.pnl_percent:.2f}%), Duration: {trade.duration} days")
    
    # Test reporter
    print("\n7. Testing reporter...")
    reporter = BacktestReporter(metrics)
    reporter.print_summary()
    
    # Test CSV export
    print("\n8. Testing CSV export...")
    try:
        reporter.export_trades_to_csv('test_trades.csv')
        reporter.export_equity_curve_to_csv('test_equity_curve.csv')
        print("[OK] CSV files exported successfully")
    except Exception as e:
        print(f"[WARN] CSV export failed: {e}")
    
    print("\n" + "="*70)
    print("[OK] Backtest engine tests completed successfully!")
    print("="*70)
    return True

if __name__ == "__main__":
    print("="*70)
    print("BACKTEST ENGINE TEST SUITE")
    print("="*70)
    
    try:
        success = test_backtest_engine()
        
        if success:
            print("\n[OK] All backtest tests passed!")
        else:
            print("\n[FAIL] Some tests failed")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

