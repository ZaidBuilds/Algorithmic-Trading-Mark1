import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import List, Dict, Any
from monitoring.logger import logger

def plot_backtest_results(data: pd.DataFrame, trades: List[Dict[str, Any]] = None, indicators: List[str] = None):
    """
    Plots price chart with indicators and trade markers.
    data: DataFrame with OHLCV and indicator columns
    trades: List of trade dicts (symbol, entry_time, exit_time, entry_price, exit_price, side)
    indicators: List of column names in 'data' to plot on the price chart
    """
    logger.info("Generating interactive backtest chart...")
    
    # Create subplots: Price (top), RSI/Volume (bottom)
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        substrings=['Price', 'Equity'],
        row_heights=[0.7, 0.3]
    )

    # 1. Candlestick Chart
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['open'],
        high=data['high'],
        low=data['low'],
        close=data['close'],
        name='Price'
    ), row=1, col=1)

    # 2. Indicators
    if indicators:
        for ind in indicators:
            if ind in data.columns:
                fig.add_trace(go.Scatter(
                    x=data.index, y=data[ind],
                    name=ind, line=dict(width=1.5)
                ), row=1, col=1)

    # 3. Trade Markers
    if trades:
        buy_x = [t['entry_time'] for t in trades if t['side'] == 'BUY']
        buy_y = [t['entry_price'] for t in trades if t['side'] == 'BUY']
        sell_x = [t['entry_time'] for t in trades if t['side'] == 'SELL']
        sell_y = [t['entry_price'] for t in trades if t['side'] == 'SELL']

        fig.add_trace(go.Scatter(
            x=buy_x, y=buy_y,
            mode='markers',
            marker=dict(symbol='triangle-up', size=12, color='green'),
            name='Buy'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=sell_x, y=sell_y,
            mode='markers',
            marker=dict(symbol='triangle-down', size=12, color='red'),
            name='Sell'
        ), row=1, col=1)

    # 4. Equity Curve
    if 'equity_curve' in data.columns:
        fig.add_trace(go.Scatter(
            x=data.index, y=data['equity_curve'],
            name='Equity', line=dict(color='royalblue', width=2)
        ), row=2, col=1)

    fig.update_layout(
        title='Strategy Performance Visualization',
        yaxis_title='Price',
        yaxis2_title='Equity',
        template='plotly_dark',
        xaxis_rangeslider_visible=False,
        height=800
    )

    # Save to HTML and open
    output_path = "backtest_report.html"
    fig.write_html(output_path)
    logger.info(f"Backtest visualization saved to {output_path}")
    
    return output_path
