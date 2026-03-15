"""
QuantumTrade — Main Launcher.

This is the ONE script that starts EVERYTHING:
  - Connects to your broker (Alpaca / Binance / Paper)
  - Starts the trading engine with your chosen strategy
  - Launches the Telegram bot controller
  - Logs all trades to SQLite database

Usage:
    python run.py                  # Start with defaults from .env
    python run.py --broker paper   # Paper trading
    python run.py --broker alpaca  # Live via Alpaca
    python run.py --strategy VWAP  # Use VWAP strategy
"""

import argparse
import logging
import sys
import os

# ── Setup logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/quantumtrade.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="⚡ QuantumTrade — AI-Powered Trading System"
    )
    parser.add_argument(
        "--broker", type=str, default=None,
        help="Broker: paper, alpaca, binance (default: from .env)"
    )
    parser.add_argument(
        "--strategy", type=str, default=None,
        help="Strategy name (default: from .env)"
    )
    parser.add_argument(
        "--symbols", type=str, nargs="+", default=None,
        help="Symbols to trade (default: from .env)"
    )
    parser.add_argument(
        "--no-telegram", action="store_true",
        help="Disable Telegram bot controller"
    )
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────
    from config.settings import settings

    broker_name = args.broker or settings.BROKER_NAME
    strategy_name = args.strategy or settings.STRATEGY_NAME
    symbols = args.symbols or settings.SYMBOLS

    print()
    print("═" * 50)
    print("  ⚡ QuantumTrade v2.0")
    print("  AI-Powered Algorithmic Trading System")
    print("═" * 50)
    print(f"  Broker:     {broker_name}")
    print(f"  Strategy:   {strategy_name}")
    print(f"  Symbols:    {', '.join(symbols)}")
    print(f"  Mode:       {'PAPER' if settings.PAPER_TRADING else '🔴 LIVE'}")
    print(f"  Interval:   {settings.TRADING_INTERVAL_SECONDS}s")
    print("═" * 50)
    print()

    # ── Initialize Database ───────────────────────────────────
    from database import get_db
    from database.trade_repository import TradeRepository

    db = get_db()
    trade_repo = TradeRepository(db)
    logger.info("📁 Database initialized")

    # ── Initialize Trading Engine ─────────────────────────────
    from live.trading_engine import LiveTradingEngine

    engine = LiveTradingEngine(
        broker_name=broker_name,
        strategy_name=strategy_name,
        symbols=symbols,
        interval_seconds=settings.TRADING_INTERVAL_SECONDS,
        api_key=settings.ALPACA_API_KEY or settings.BINANCE_API_KEY or settings.API_KEY or "",
        api_secret=settings.ALPACA_API_SECRET or settings.BINANCE_API_SECRET or settings.API_SECRET or "",
        paper=settings.PAPER_TRADING,
        telegram_token=settings.TELEGRAM_BOT_TOKEN or "",
        telegram_chat_id=settings.TELEGRAM_CHAT_ID or "",
        discord_webhook_url=settings.DISCORD_WEBHOOK_URL or "",
        email_smtp_host=settings.EMAIL_SMTP_HOST or "",
        email_user=settings.EMAIL_USER or "",
        email_password=settings.EMAIL_PASSWORD or "",
        email_to=settings.EMAIL_TO or "",
    )

    # ── Start Telegram Bot Controller ─────────────────────────
    if not args.no_telegram and settings.TELEGRAM_BOT_TOKEN:
        from telegram_controller import TelegramController

        telegram_bot = TelegramController(
            token=settings.TELEGRAM_BOT_TOKEN,
            allowed_chat_ids=[settings.TELEGRAM_CHAT_ID] if settings.TELEGRAM_CHAT_ID else [],
            broker=engine.broker,
            engine=engine,
            db=db,
            trade_repo=trade_repo,
        )
        telegram_bot.start()
        logger.info("🤖 Telegram bot controller started")
    else:
        logger.info("📵 Telegram bot disabled (no token configured)")

    # ── Connect broker ────────────────────────────────────────
    if not engine.broker.connect():
        logger.error("❌ Broker connection failed. Exiting.")
        sys.exit(1)

    # Log initial account info
    account = engine.broker.get_account()
    trade_repo.take_snapshot(
        cash=account.cash,
        equity=account.equity,
        portfolio_value=account.portfolio_value,
        positions_count=len(account.positions),
    )

    print()
    print(f"  💰 Cash:     ${account.cash:,.2f}")
    print(f"  📊 Equity:   ${account.equity:,.2f}")
    print(f"  📈 Positions: {len(account.positions)}")
    print()
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    print()

    # ── Start Trading Engine ──────────────────────────────────
    try:
        engine.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down...")
        engine.stop()

        # Final snapshot
        try:
            account = engine.broker.get_account()
            trade_repo.take_snapshot(
                cash=account.cash,
                equity=account.equity,
                portfolio_value=account.portfolio_value,
                positions_count=len(account.positions),
            )
        except Exception:
            pass

        # Print summary
        print()
        print(trade_repo.summary())
        print()

        db.close()
        logger.info("✅ Shutdown complete")


if __name__ == "__main__":
    main()
