import os
import sys
import time
import webbrowser
from threading import Thread, Timer
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from monitoring.logger import logger
from data.data_client import get_data_client
from strategy.sma_strategy import SMAStrategy
from strategy.rsi_strategy import RSIStrategy
from risk.risk_manager import RiskManager
from execution.broker_client import PaperBroker
from live.runner import TradingRunner
from quantumtrade.backtesting.engine import BacktestEngine

app = Flask(__name__, template_folder='../templates')

# Global state
bot_state = {
    'running': False,
    'status': 'Stopped',
    'runner': None,
    'broker': None,
    'strategy': None,
    'strategy_name': 'SMA Crossover',
    'symbol': 'AAPL',
    'initial_balance': settings.INITIAL_CAPITAL,
    'thread': None,
    'last_update': None,
    'logs': []
}

STRATEGIES = {
    'SMA Crossover': SMAStrategy,
    'RSI Reversion': RSIStrategy
}

def add_log(msg, log_type="info"):
    timestamp = datetime.now().strftime('%H:%M:%S')
    bot_state['logs'].append({
        'time': timestamp,
        'msg': msg,
        'type': log_type
    })
    if len(bot_state['logs']) > 50:
        bot_state['logs'].pop(0)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/status')
def status():
    # Construct portfolio data from broker if running
    portfolio = {
        'balance': bot_state['broker'].get_balance() if bot_state['broker'] else bot_state['initial_balance'],
        'equity': bot_state['broker'].get_balance() if bot_state['broker'] else bot_state['initial_balance'], # Placeholder for equity
        'pnl': (bot_state['broker'].get_balance() - bot_state['initial_balance']) if bot_state['broker'] else 0.0,
        'pnl_percent': ((bot_state['broker'].get_balance() / bot_state['initial_balance'] - 1) * 100) if bot_state['broker'] else 0.0
    }
    
    # Construct positions from broker
    positions = []
    if bot_state['broker']:
        for sym, qty in bot_state['broker'].positions.items():
            if qty > 0:
                positions.append({
                    'symbol': sym,
                    'quantity': qty,
                    'entry_price': 0.0, # Need to track this in broker eventually
                    'current_price': 0.0,
                    'pnl': 0.0,
                    'pnl_percent': 0.0
                })

    return jsonify({
        'bot_status': {
            'running': bot_state['running'],
            'status': bot_state['status'],
            'symbol': bot_state['symbol'],
            'strategy': bot_state['strategy_name'],
            'last_update': bot_state['last_update'].isoformat() if bot_state['last_update'] else None
        },
        'portfolio': portfolio,
        'positions': positions,
        'recent_trades': [], # To be implemented
        'performance': {'win_rate': 0.0, 'total_trades': 0},
        'logs': bot_state['logs'],
        'available_strategies': list(STRATEGIES.keys())
    })

@app.route('/api/start', methods=['POST'])
def start():
    if bot_state['running']:
        return jsonify({'success': False, 'message': 'Bot already running'})
    
    data = request.json
    bot_state['symbol'] = data.get('symbol', 'AAPL').upper()
    bot_state['strategy_name'] = data.get('strategy', 'SMA Crossover')
    bot_state['initial_balance'] = float(data.get('initial_balance', settings.INITIAL_CAPITAL))
    
    # Initialize Engine
    bot_state['strategy'] = STRATEGIES.get(bot_state['strategy_name'])
    if not bot_state['strategy']:
        # Fallback search
        for name, cls in STRATEGIES.items():
            if bot_state['strategy_name'].lower() in name.lower():
                bot_state['strategy'] = cls
                break
    
    if not bot_state['strategy']:
        return jsonify({'success': False, 'message': f"Strategy {bot_state['strategy_name']} not found"})
        
    bot_state['strategy'] = bot_state['strategy']()
    
    from execution.factory import get_broker_client
    bot_state['broker'] = get_broker_client(bot_state['symbol'], bot_state['initial_balance'])
    risk_manager = RiskManager(bot_state['initial_balance'])
    bot_state['runner'] = TradingRunner(bot_state['strategy'], bot_state['broker'], risk_manager)
    
    # Override settings for the runner
    settings.SYMBOLS = [bot_state['symbol']]
    settings.TIMEFRAME = '1d' # Ensure compatible timeframe for stocks
    
    bot_state['running'] = True
    bot_state['status'] = 'Running'
    
    def run_wrapper():
        try:
            bot_state['runner'].run(interval_minutes=1)
        except Exception as e:
            bot_state['status'] = f'Error: {str(e)}'
            bot_state['running'] = False

    bot_state['thread'] = Thread(target=run_wrapper, daemon=True)
    bot_state['thread'].start()
    
    add_log(f"Started {bot_state['strategy_name']} on {bot_state['symbol']}", "success")
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
def stop():
    bot_state['running'] = False
    bot_state['status'] = 'Stopped'
    add_log("Bot execution stopped manually", "warning")
    return jsonify({'success': True})

@app.route('/api/history')
def history():
    sym = request.args.get('symbol', 'AAPL')
    client = get_data_client(sym)
    df = client.fetch_ohlcv(sym, settings.TIMEFRAME, "30 days ago")
    if df.empty:
        return jsonify({'error': 'No data'}), 400
    
    history = []
    for t, r in df.iterrows():
        history.append({
            'time': int(t.timestamp()),
            'open': float(r['open']),
            'high': float(r['high']),
            'low': float(r['low']),
            'close': float(r['close'])
        })
    return jsonify({'symbol': sym, 'history': history})

@app.route('/api/backtest', methods=['POST'])
def backtest():
    data = request.json
    sym = data.get('symbol', 'AAPL').upper()
    strat_name = data.get('strategy', 'SMA Crossover')
    capital = float(data.get('initial_balance', settings.INITIAL_CAPITAL))
    
    client = get_data_client(sym)
    df = client.fetch_ohlcv(sym, settings.TIMEFRAME, data.get('start_date', '2023-01-01'), data.get('end_date', '2023-12-31'))
    
    if df.empty:
        return jsonify({'success': False, 'message': 'No data found for backtest'})
        
    engine = BacktestEngine(capital)
    strategy = STRATEGIES.get(strat_name)()
    metrics = engine.run(df, strategy)
    
    # Map engine metrics to dashboard expected format
    return jsonify({
        'success': True,
        'summary': {
            'final_balance': metrics['Final Capital'],
            'total_pnl': metrics['Total Return'],
            'total_pnl_pct': metrics['Total Return'],
            'win_rate': 0.0,
            'profit_factor': 0.0
        },
        'trades': [] # TODO: Extract from engine
    })

def start_dashboard():
    Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    start_dashboard()
