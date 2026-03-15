"""
Comprehensive test suite for QuantumTrade trading system.

Tests include:
- Data loading and validation
- Strategy signal generation
- Backtesting engine
- Risk management
- Trade execution
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import settings
from data.loader import DataLoader
from data.validator import DataValidator
from strategy import (
    EMACrossoverStrategy,
    SMAStrategy,
    RSIStrategy,
    MACDStrategy,
    BollingerBandsStrategy
)
from strategy.signals import Signal, SignalType
from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import BacktestMetrics, Trade
from execution.broker_client import PaperBroker
from risk.risk_manager import RiskManager


class TestDataLoading:
    """Test data loading from Yahoo Finance"""
    
    def test_load_yahoo_with_dates(self):
        """Test loading data from Yahoo Finance with date range"""
        loader = DataLoader()
        df = loader.load_yahoo(
            symbol="AAPL",
            start_date="2023-01-01",
            end_date="2023-12-31",
            interval="1d"
        )
        
        assert df is not None, "Failed to load data"
        assert not df.empty, "Loaded data is empty"
        assert len(df) > 0, "No data rows"
        assert all(col in df.columns for col in ['Open', 'High', 'Low', 'Close', 'Volume']), \
            "Missing OHLCV columns"
    
    def test_load_yahoo_with_period(self):
        """Test loading data from Yahoo Finance with period"""
        loader = DataLoader()
        df = loader.load_yahoo(
            symbol="AAPL",
            period="1mo",
            interval="1d"
        )
        
        assert df is not None, "Failed to load data"
        assert not df.empty, "Loaded data is empty"
    
    def test_load_csv(self):
        """Test loading CSVdata from file"""
        loader = DataLoader()
        # Create a test CSV file
        test_data = pd.DataFrame({
            'Date': pd.date_range('2023-01-01', periods=10),
            'Open': np.random.rand(10) * 100,
            'High': np.random.rand(10) * 100 + 100,
            'Low': np.random.rand(10) * 100,
            'Close': np.random.rand(10) * 100,
            'Volume': np.random.randint(1000000, 10000000, 10)
        })
        
        csv_path = "test_data.csv"
        test_data.to_csv(csv_path, index=False)
        
        try:
            df = loader.load_csv(csv_path)
            assert df is not None, "Failed to load CSV"
            assert not df.empty, "Loaded CSV is empty"
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestDataValidation:
    """Test data validation"""
    
    def test_validate_good_data(self):
        """Test validation of good OHLCV data"""
        validator = DataValidator()
        
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103],
            'High': [105, 106, 107, 108],
            'Low': [95, 96, 97, 98],
            'Close': [102, 103, 104, 105],
            'Volume': [1000000, 1000000, 1000000, 1000000]
        }, index=pd.date_range('2023-01-01', periods=4))
        
        is_valid, df_clean, warnings = validator.validate(df)
        
        assert is_valid, "Good data should pass validation"
        assert len(warnings) == 0, f"Good data should have no warnings: {warnings}"
    
    def test_validate_bad_ranges(self):
        """Test detection of invalid OHLCV ranges"""
        validator = DataValidator()
        
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103],
            'High': [90, 106, 107, 108],  # High < Low
            'Low': [95, 96, 97, 98],
            'Close': [102, 103, 104, 105],
            'Volume': [1000000, 1000000, 1000000, 1000000]
        }, index=pd.date_range('2023-01-01', periods=4))
        
        is_valid, df_clean, warnings = validator.validate(df)
        
        assert not is_valid, "Data with invalid ranges should fail"


class TestStrategies:
    """Test trading strategy implementations"""
    
    def create_sample_data(self, periods: int = 100) -> pd.DataFrame:
        """Create sample OHLCV data for testing"""
        np.random.seed(42)
        close = [100 + np.sum(np.random.randn(i+1)) for i in range(periods)]
        
        return pd.DataFrame({
            'Open': [c - 0.5 for c in close],
            'High': [c + 1 for c in close],
            'Low': [c - 1 for c in close],
            'Close': close,
            'Volume': [1000000] * periods
        }, index=pd.date_range('2023-01-01', periods=periods))
    
    def test_ema_crossover_strategy(self):
        """Test EMA Crossover strategy signal generation"""
        strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
        df = self.create_sample_data(50)
        
        # Calculate indicators
        df_with_indicators = strategy.calculate_indicators(df)
        
        # Check that indicators were added
        assert 'ema_fast' in df_with_indicators.columns, "Missing ema_fast indicator"
        assert 'ema_slow' in df_with_indicators.columns, "Missing ema_slow indicator"
        
        # Generate signal at valid index
        signal = strategy.generate_signal(df_with_indicators, 30)
        
        assert isinstance(signal, Signal), "Should return Signal object"
        assert signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD], \
            "Invalid signal type"
    
    def test_sma_strategy(self):
        """Test SMA Crossover strategy"""
        strategy = SMAStrategy(short_period=20, long_period=50)
        df = self.create_sample_data(60)
        
        df_with_indicators = strategy.calculate_indicators(df)
        
        assert 'sma_short' in df_with_indicators.columns, "Missing sma_short"
        assert 'sma_long' in df_with_indicators.columns, "Missing sma_long"
        
        signal = strategy.generate_signal(df_with_indicators, 55)
        assert isinstance(signal, Signal), "Should return Signal"
    
    def test_all_strategies(self):
        """Test all available strategies can generate signals"""
        strategies = [
            EMACrossoverStrategy(),
            SMAStrategy(),
            RSIStrategy(),
            MACDStrategy(),
            BollingerBandsStrategy()
        ]
        
        df = self.create_sample_data(100)
        
        for strategy in strategies:
            # Calculate indicators
            df_ind = strategy.calculate_indicators(df.copy())
            
            # Generate signal
            idx = min(50, len(df_ind) - 1)
            signal = strategy.generate_signal(df_ind, idx)
            
            assert isinstance(signal, Signal), f"{strategy.name} should return Signal"
            assert signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD], \
                f"{strategy.name} produced invalid signal"


class TestBacktestEngine:
    """Test backtesting engine"""
    
    def create_sample_data(self, periods: int = 100) -> pd.DataFrame:
        """Create sample OHLCV data"""
        np.random.seed(42)
        close = [100 + np.sum(np.random.randn(i+1)) for i in range(periods)]
        
        return pd.DataFrame({
            'Open': [c - 0.5 for c in close],
            'High': [c + 1 for c in close],
            'Low': [c - 1 for c in close],
            'Close': close,
            'Volume': [1000000] * periods
        }, index=pd.date_range('2023-01-01', periods=periods))
    
    def test_backtest_engine_basic(self):
        """Test basic backtest engine functionality"""
        engine = BacktestEngine(initial_balance=100000.0)
        strategy = EMACrossoverStrategy()
        df = self.create_sample_data(100)
        
        metrics = engine.run(strategy, df)
        
        assert isinstance(metrics, BacktestMetrics), "Should return BacktestMetrics"
        assert metrics.initial_balance == 100000.0, "Initial balance should be set"
        assert len(metrics.equity_curve) > 0, "Equity curve should have values"
        assert len(metrics.trades) >= 0, "Should have trade records"
    
    def test_backtest_results_calculation(self):
        """Test that backtest results are calculated correctly"""
        engine = BacktestEngine(initial_balance=10000.0)
        strategy = SMAStrategy()
        df = self.create_sample_data(100)
        
        metrics = engine.run(strategy, df)
        summary = metrics.get_summary()
        
        assert 'initial_balance' in summary, "Missing initial_balance"
        assert 'final_balance' in summary, "Missing final_balance"
        assert 'total_return' in summary, "Missing total_return info"
        assert 'sharpe_ratio' in summary, "Missing sharpe_ratio"


class TestRiskManagement:
    """Test risk management"""
    
    def test_risk_manager_initialization(self):
        """Test risk manager creation"""
        rm = RiskManager(initial_capital=100000.0)
        
        assert rm.initial_capital == 100000.0, "Initial capital not set"
        assert rm.current_capital == 100000.0, "Current capital not initialized"
    
    def test_risk_check_within_limits(self):
        """Test risk check for trade within limits"""
        rm = RiskManager(initial_capital=100000.0)
        
        # Should allow small trade
        is_ok = rm.check_trade("AAPL", 10, 150)
        assert is_ok, "Should allow trade within risk limits"
    
    def test_risk_check_exceeds_position_size(self):
        """Test risk check when position size is too large"""
        rm = RiskManager(initial_capital=10000.0)
        
        # Very large position that exceeds max_position_size_pct
        is_ok = rm.check_trade("AAPL", 10000, 150)
        assert not is_ok, "Should reject oversized position"


class TestExecution:
    """Test trade execution"""
    
    def test_paper_broker_buy(self):
        """Test paper broker BUY order"""
        broker = PaperBroker(initial_balance=100000.0)
        
        result = broker.place_order("AAPL", "BUY", 10, 150.0)
        
        assert result['status'] == 'SUCCESS', "Buy order should succeed"
        assert 'AAPL' in broker.positions, "Position should be recorded"
        assert broker.positions['AAPL'] == 10, "Position size should be correct"
    
    def test_paper_broker_sell(self):
        """Test paper broker SELL order"""
        broker = PaperBroker(initial_balance=100000.0)
        
        # Buy first
        broker.place_order("AAPL", "BUY", 10, 150.0)
        
        # Then sell
        result = broker.place_order("AAPL", "SELL", 10, 150.0)
        
        assert result['status'] == 'SUCCESS', "Sell order should succeed"
        assert broker.positions.get('AAPL', 0) == 0, "Position should be closed"
    
    def test_paper_broker_insufficient_funds(self):
        """Test paper broker rejects buy without sufficient funds"""
        broker = PaperBroker(initial_balance=1000.0)
        
        # Try to buy more than we can afford
        result = broker.place_order("AAPL", "BUY", 100, 150.0)
        
        assert result['status'] == 'FAILED', "Should reject insufficient funds"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
