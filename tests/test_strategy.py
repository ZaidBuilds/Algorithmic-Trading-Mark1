import pandas as pd
import numpy as np
from strategies.base_strategy import SMAStrategy

def test_sma_strategy():
    # Create fake data
    dates = pd.date_range(start="2023-01-01", periods=300, freq="D")
    data = pd.DataFrame({
        "close": np.linspace(100, 200, 300) + np.random.normal(0, 5, 300)
    }, index=dates)
    
    strategy = SMAStrategy(short_window=10, long_window=50)
    signals = strategy.generate_signals(data)
    
    assert len(signals) == len(data)
    assert set(signals.unique()).issubset({-1, 0, 1})
    print("SMA Strategy signal test passed!")

if __name__ == "__main__":
    test_sma_strategy()
