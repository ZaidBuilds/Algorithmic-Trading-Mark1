# 📈 Apex Algo Trader
Python AI trading system with multi-broker integrations, ML strategy modules, and Telegram dashboards.

Status: 80% complete — PACKAGE

## 🚀 Features
*   **10+ Active Strategies**: Implements Mean Reversion, Grid Trading, and Momentum algorithms.
*   **Risk ATR Management**: Dynamic position calculators managing risk per trade.
*   **Telegram Command Dashboard**: Query open positions and check profit statistics directly from Telegram.

## 🛠️ Tech Stack
*   **Language**: Python 3.10+
*   **Libraries**: Pandas, NumPy, TA, MLflow, Pytest
*   **APIs**: Alpaca, Binance, Telegram

## 🔮 What's Left to Ship
We need to connect the system to an authenticated, live-funded broker API account and write Docker deployment files. This will allow the trading bot to run continuously in a production environment.

## 📦 How to Run Locally
1.  Install requirements:
    ```bash
    pip install -r requirements.txt
    ```
2.  Run the bot driver:
    ```bash
    python run.py
    ```
