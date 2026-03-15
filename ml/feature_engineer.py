"""Feature engineering for machine learning predictions."""

import pandas as pd
import numpy as np
from typing import Tuple, List, Optional
import warnings

warnings.filterwarnings('ignore')


class FeatureEngineer:
    """
    Converts raw OHLCV data into ML-ready features.
    
    Features Created:
    - Trend: SMA, EMA, volatility, momentum
    - Volume: OBV, volume momentum
    - Price: RSI, MACD, Bollinger bands
    - Returns: lagged returns, rolling variance
    - Targets: future price direction (1=up, 0=down)
    """
    
    def __init__(self, lookback_window: int = 20, future_window: int = 5):
        """
        Initialize feature engineer.
        
        Args:
            lookback_window: Days to look back for features
            future_window: Days ahead to predict
        """
        self.lookback_window = lookback_window
        self.future_window = future_window
        self.scaler_mean = None
        self.scaler_std = None
        
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create all features from OHLCV data.
        
        Args:
            df: DataFrame with columns [Open, High, Low, Close, Volume]
            
        Returns:
            DataFrame with engineered features
        """
        df = df.copy()
        
        # Price-based features
        df['sma_20'] = df['Close'].rolling(20).mean()
        df['sma_50'] = df['Close'].rolling(50).mean()
        df['ema_12'] = df['Close'].ewm(span=12).mean()
        df['ema_26'] = df['Close'].ewm(span=26).mean()
        
        # Volatility features
        df['volatility'] = df['Close'].pct_change().rolling(20).std()
        df['high_low_ratio'] = (df['High'] - df['Low']) / df['Close']
        
        # Momentum features
        df['rsi'] = self._calculate_rsi(df['Close'], period=14)
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Volume features
        df['volume_sma'] = df['Volume'].rolling(20).mean()
        df['volume_ratio'] = df['Volume'] / df['volume_sma']
        
        # Price features
        df['returns'] = df['Close'].pct_change()
        df['log_returns'] = np.log(df['Close'] / df['Close'].shift(1))
        
        # Bollinger Bands
        sma = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        df['bb_upper'] = sma + (std * 2)
        df['bb_lower'] = sma - (std * 2)
        df['bb_position'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # Lagged features (history)
        for lag in [1, 2, 3, 5]:
            df[f'returns_lag_{lag}'] = df['returns'].shift(lag)
            df[f'rsi_lag_{lag}'] = df['rsi'].shift(lag)
        
        # Target: Future direction (1 if price up, 0 if down)
        df['future_return'] = df['Close'].shift(-self.future_window) / df['Close'] - 1
        df['target'] = (df['future_return'] > 0).astype(int)
        
        # Remove NaN rows
        df = df.dropna()
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def get_feature_matrix(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get feature matrix and target for ML models.
        
        Args:
            df: DataFrame with engineered features
            
        Returns:
            X: Feature matrix (shape: n_samples, n_features)
            y: Target array (shape: n_samples,)
        """
        feature_cols = [col for col in df.columns 
                       if col not in ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 
                                     'future_return', 'target'] and df[col].dtype != 'object']
        
        X = df[feature_cols].values
        y = df['target'].values
        
        return X, y
    
    def normalize_features(self, X: np.ndarray, fit: bool = True) -> np.ndarray:
        """
        Normalize features using z-score (mean=0, std=1).
        
        Args:
            X: Feature matrix
            fit: If True, fit scaler on this data
            
        Returns:
            Normalized feature matrix
        """
        if fit:
            self.scaler_mean = X.mean(axis=0)
            self.scaler_std = X.std(axis=0)
        
        X_normalized = (X - self.scaler_mean) / (self.scaler_std + 1e-8)
        return X_normalized
    
    def create_sequences(self, X: np.ndarray, y: np.ndarray, 
                        seq_length: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for time-series models (LSTM, etc).
        
        Args:
            X: Feature matrix
            y: Target array
            seq_length: Length of sequences
            
        Returns:
            X_seq: Sequences of features
            y_seq: Corresponding targets
        """
        X_seq, y_seq = [], []
        
        for i in range(len(X) - seq_length):
            X_seq.append(X[i:i + seq_length])
            y_seq.append(y[i + seq_length])
        
        return np.array(X_seq), np.array(y_seq)


# Example usage and testing
if __name__ == "__main__":
    # Create sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    df = pd.DataFrame({
        'Date': dates,
        'Open': 100 + np.cumsum(np.random.randn(100) * 2),
        'High': 102 + np.cumsum(np.random.randn(100) * 2),
        'Low': 98 + np.cumsum(np.random.randn(100) * 2),
        'Close': 100 + np.cumsum(np.random.randn(100) * 2),
        'Volume': np.random.randint(1000000, 5000000, 100)
    })
    
    # Engineer features
    engineer = FeatureEngineer()
    df_features = engineer.engineer_features(df)
    
    print("✓ Feature Engineering Complete")
    print(f"  Original shape: {df.shape}")
    print(f"  Features shape: {df_features.shape}")
    print(f"  Features created: {len(df_features.columns)}")
    print(f"\n  Feature columns:")
    for col in df_features.columns[:15]:
        print(f"    - {col}")
    
    # Get feature matrix
    X, y = engineer.get_feature_matrix(df_features)
    print(f"\n✓ Feature Matrix Created")
    print(f"  X shape: {X.shape}")
    print(f"  y shape: {y.shape}")
    print(f"  Class distribution: {np.bincount(y)}")
    
    # Normalize
    X_norm = engineer.normalize_features(X, fit=True)
    print(f"\n✓ Features Normalized")
    print(f"  Mean: {X_norm.mean():.6f}")
    print(f"  Std: {X_norm.std():.6f}")
    
    # Create sequences
    X_seq, y_seq = engineer.create_sequences(X_norm, y, seq_length=10)
    print(f"\n✓ Sequences Created")
    print(f"  X_seq shape: {X_seq.shape}")
    print(f"  y_seq shape: {y_seq.shape}")
