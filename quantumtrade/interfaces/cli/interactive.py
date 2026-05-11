#!/usr/bin/env python
"""
QuantumTrade Multi-Asset Trading System
Main entry point for the trading bot application

This script provides an interactive menu-driven interface for:
- Running backtests on historical data
- Paper trading (simulated trading)
- Live trading with real brokers
- Launching the web dashboard
- Managing strategies and configurations
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import questionary
from colorama import init, Fore, Style

from config.settings import settings
from config.assets import ASSETS_REGISTRY, AssetClass
from utils.logger import setup_logger
from data.loader import DataLoader
from data.validator import DataValidator
from strategy import (
    BaseStrategy,
    EMACrossoverStrategy,
    SMAStrategy,
    RSIStrategy,
    MACDStrategy,
    BollingerBandsStrategy,
)
from quantumtrade.backtesting.engine import BacktestEngine
from quantumtrade.backtesting.reporter import BacktestReporter
from risk.risk_manager import RiskManager

# Initialize colorama for Windows compatibility
init(autoreset=True)

# Setup logger
logger = setup_logger("TradingBot", level=settings.LOG_LEVEL)

# Available strategies
STRATEGIES = {
    "EMA Crossover": EMACrossoverStrategy,
    "SMA Crossover": SMAStrategy,
    "RSI Reversion": RSIStrategy,
    "MACD": MACDStrategy,
    "Bollinger Bands": BollingerBandsStrategy,
}


def print_header():
    """Print application header"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}╔════════════════════════════════════════════════════════════╗")
    print(f"║  {Fore.GREEN}QuantumTrade Multi-Asset Trading System{Fore.CYAN}         ║")
    print(f"║  {Fore.YELLOW}Production-Ready Trading Engine{Fore.CYAN}                      ║")
    print(f"╚════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")


def interactive_menu():
    """Main interactive menu"""
    while True:
        print_header()
        
        mode = questionary.select(
            "Select Operation Mode:",
            choices=[
                "Backtest Strategy",
                "Paper Trading (Simulated)",
                "Live Trading",
                "Dashboard",
                "Exit"
            ]
        ).ask()
        
        if mode == "Exit":
            logger.info("Application shutdown")
            sys.exit(0)
        elif mode == "Dashboard":
            run_dashboard()
        elif mode == "Backtest Strategy":
            run_backtest_menu()
        elif mode == "Paper Trading (Simulated)":
            run_paper_trading_menu()
        elif mode == "Live Trading":
            run_live_trading_menu()


def run_backtest_menu():
    """Interactive backtest menu"""
    logger.info("=" * 70)
    logger.info("BACKTEST MODE")
    logger.info("=" * 70)
    
    # Select asset class
    asset_class_choice = questionary.select(
        "Select Asset Class:",
        choices=[ac.value for ac in AssetClass]
    ).ask()
    
    asset_class = AssetClass(asset_class_choice)
    symbols = ASSETS_REGISTRY.get(asset_class, [])
    
    # Select symbol
    symbol = questionary.select(
        f"Select {asset_class_choice} Symbol:",
        choices=symbols
    ).ask()
    
    # Select strategy
    strategy_name = questionary.select(
        "Select Strategy:",
        choices=list(STRATEGIES.keys())
    ).ask()
    
    # Select timeframe
    timeframe = questionary.select(
        "Select Timeframe:",
        choices=["1m", "5m", "15m", "1h", "1d"]
    ).ask()
    
    # Get date range
    start_date = questionary.text(
        "Enter start date (YYYY-MM-DD) [default: 1 year ago]:",
        default=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    ).ask()
    
    end_date = questionary.text(
        "Enter end date (YYYY-MM-DD) [default: today]:",
        default=datetime.now().strftime("%Y-%m-%d")
    ).ask()
    
    initial_balance = questionary.text(
        "Enter initial balance [$]:",
        default="100000.0"
    ).ask()
    
    # Run backtest
    run_backtest(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
        initial_balance=float(initial_balance)
    )


def run_backtest(
    symbol: str,
    timeframe: str,
    strategy_name: str,
    start_date: str,
    end_date: str,
    initial_balance: float = 100000.0
):
    """Execute backtest"""
    logger.info(f"\n{Fore.CYAN}Starting Backtest...")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeline: {timeframe}")
    logger.info(f"Strategy: {strategy_name}")
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info(f"Initial Capital: ${initial_balance:,.2f}")
    
    try:
        # Load data
        logger.info(f"\nLoading market data for {symbol}...")
        data_loader = DataLoader()
        df = data_loader.load_yahoo(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=timeframe
        )
        
        if df is None or df.empty:
            logger.error(f"✗ Failed to load data for {symbol}")
            return
        
        logger.info(f"✓ Loaded {len(df)} candles ({df.index[0]} to {df.index[-1]})")
        
        # Validate data
        logger.info("Validating data...")
        validator = DataValidator()
        is_valid, df_clean, warnings = validator.validate(df)
        
        if not is_valid:
            logger.error(f"✗ Data validation failed:")
            for warning in warnings:
                logger.error(f"  - {warning}")
            return
        
        logger.info(f"✓ Data validation passed")
        if warnings:
            for warning in warnings:
                logger.warning(f"  ⚠ {warning}")
        
        # Create and run backtest
        logger.info(f"\nInitializing {strategy_name} strategy...")
        strategy_class = STRATEGIES[strategy_name]
        
        if strategy_name == "EMA Crossover":
            strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
        elif strategy_name == "SMA Crossover":
            strategy = SMAStrategy(short_period=20, long_period=50)
        elif strategy_name == "RSI Reversion":
            strategy = RSIStrategy(period=14)
        elif strategy_name == "MACD":
            strategy = MACDStrategy()
        elif strategy_name == "Bollinger Bands":
            strategy = BollingerBandsStrategy()
        else:
            strategy = strategy_class()
        
        logger.info(f"✓ Strategy: {strategy.name}")
        
        # Run backtest engine
        logger.info("\nRunning backtest engine...")
        engine = BacktestEngine(initial_balance=initial_balance, commission=settings.COMMISSION_PCT)
        metrics = engine.run(strategy, df_clean)
        
        # Generate report
        logger.info("\nGenerating report...")
        reporter = BacktestReporter(metrics)
        reporter.print_summary()
        
        # Export results
        if questionary.confirm("\n✓ Export results to CSV?").ask():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trades_file = f"results/backtest_trades_{symbol}_{timestamp}.csv"
            equity_file = f"results/backtest_equity_{symbol}_{timestamp}.csv"
            
            Path("results").mkdir(exist_ok=True)
            reporter.export_trades_to_csv(trades_file)
            reporter.export_equity_curve_to_csv(equity_file)
            logger.info(f"✓ Results exported to results/ directory")
        
        # Generate visualization
        if questionary.confirm("Generate interactive HTML chart?").ask():
            chart_file = f"results/backtest_chart_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            Path("results").mkdir(exist_ok=True)
            # reporter.generate_html_report(chart_file)
            logger.info(f"✓ Chart would be saved to {chart_file}")
        
    except Exception as e:
        logger.error(f"✗ Backtest failed: {str(e)}")
        import traceback
        traceback.print_exc()


def run_paper_trading_menu():
    """Interactive paper trading menu"""
    logger.info("=" * 70)
    logger.info("PAPER TRADING MODE (Simulated)")
    logger.info("=" * 70)
    
    print(f"{Fore.YELLOW}Paper trading is currently under development.")
    print(f"For now, please use backtest mode to test strategies.{Style.RESET_ALL}\n")
    input("Press Enter to return to main menu...")


def run_live_trading_menu():
    """Interactive live trading menu"""
    logger.info("=" * 70)
    logger.info("LIVE TRADING MODE")
    logger.info("=" * 70)
    
    print(f"{Fore.RED}⚠ WARNING: Live trading with real money!{Style.RESET_ALL}")
    print(f"Live trading is currently under development and not ready for production.\n")
    
    confirmed = questionary.confirm(
        "I understand the risks and want to continue?"
    ).ask()
    
    if not confirmed:
        logger.info("Live trading cancelled")
        return
    
    print(f"{Fore.YELLOW}Live trading is not yet implemented.{Style.RESET_ALL}\n")
    input("Press Enter to return to main menu...")


def run_dashboard():
    """Launch web dashboard"""
    logger.info("=" * 70)
    logger.info("LAUNCHING DASHBOARD")
    logger.info("=" * 70)
    
    try:
        from monitoring.dashboard_server import start_dashboard
        start_dashboard()
    except Exception as e:
        logger.error(f"Failed to start dashboard: {str(e)}")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="QuantumTrade Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                              # Interactive mode
  python main.py backtest --symbol AAPL --strategy "EMA Crossover"
  python main.py dashboard                                   # Launch dashboard
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Backtest subcommand
    backtest_parser = subparsers.add_parser("backtest", help="Run backtest")
    backtest_parser.add_argument("--symbol", default="AAPL", help="Symbol to backtest")
    backtest_parser.add_argument("--strategy", default="EMA Crossover", help="Strategy name")
    backtest_parser.add_argument("--timeframe", default="1d", help="Timeframe (1m, 5m, 1h, 1d)")
    backtest_parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    backtest_parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    backtest_parser.add_argument("--capital", type=float, default=100000.0, help="Initial capital")
    
    # Dashboard subcommand
    subparsers.add_parser("dashboard", help="Launch web dashboard")
    
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    
    if args.command == "backtest":
        # CLI backtest mode
        start_date = args.start or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end_date = args.end or datetime.now().strftime("%Y-%m-%d")
        
        print_header()
        run_backtest(
            symbol=args.symbol,
            timeframe=args.timeframe,
            strategy_name=args.strategy,
            start_date=start_date,
            end_date=end_date,
            initial_balance=args.capital
        )
    
    elif args.command == "dashboard":
        # Dashboard mode
        run_dashboard()
    
    else:
        # Interactive menu mode
        interactive_menu()


if __name__ == "__main__":
    main()
