"""
Telegram Bot Controller — Control your entire trading system from your phone.

This is a FULL INTERACTIVE BOT, not just notifications.
You can start/stop trading, execute orders, check portfolio,
view P&L, and manage everything from Telegram.

Commands:
  /start       — Welcome message & help
  /help        — Show all commands
  /status      — Engine status (running, equity, positions)
  /balance     — Account balance & buying power
  /positions   — List all open positions
  /buy         — Manual buy: /buy AAPL 10
  /sell        — Manual sell: /sell AAPL 10
  /pnl         — P&L report (today + total)
  /history     — Recent trade history
  /strategy    — View/change active strategy
  /strategies  — List all available strategies
  /startbot    — Start the trading engine
  /stopbot     — Stop the trading engine
  /snapshot    — Take portfolio snapshot

Setup:
  1. Message @BotFather on Telegram → /newbot → get token
  2. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
  3. Run: python telegram_controller.py
"""

import logging
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramController:
    """
    Interactive Telegram bot for controlling QuantumTrade.

    Uses python-telegram-bot library (async) to handle commands.
    The bot runs in a background thread alongside the trading engine.
    """

    def __init__(
        self,
        token: str,
        allowed_chat_ids: list = None,
        broker=None,
        engine=None,
        db=None,
        trade_repo=None,
    ):
        """
        Args:
            token: Telegram Bot API token from @BotFather
            allowed_chat_ids: List of chat IDs allowed to control the bot
                              (security — only YOUR Telegram account)
            broker: BaseBroker instance for executing orders
            engine: LiveTradingEngine instance for start/stop
            db: Database instance for queries
            trade_repo: TradeRepository for trade operations
        """
        self.token = token
        self.allowed_chat_ids = [str(cid) for cid in (allowed_chat_ids or [])]
        self.broker = broker
        self.engine = engine
        self.db = db
        self.trade_repo = trade_repo
        self._app = None
        self._thread: Optional[threading.Thread] = None

        # Portfolio tracker & performance analyzer
        self._portfolio_tracker = None
        self._performance_analyzer = None
        try:
            from portfolio import PortfolioTracker, PerformanceAnalyzer
            if broker and db:
                self._portfolio_tracker = PortfolioTracker(broker=broker, db=db)
                self._performance_analyzer = PerformanceAnalyzer(db=db)
        except ImportError:
            pass

    def start(self) -> None:
        """Start the Telegram bot in a background thread."""
        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()
        logger.info("🤖 Telegram Controller started")

    def _run_bot(self) -> None:
        """Internal: set up and run the bot."""
        try:
            from telegram import Update, BotCommand
            from telegram.ext import (
                ApplicationBuilder, CommandHandler, ContextTypes,
                MessageHandler, filters,
            )
        except ImportError:
            logger.error(
                "python-telegram-bot not installed. "
                "Run: pip install python-telegram-bot"
            )
            return

        import asyncio

        async def _setup_and_run():
            app = ApplicationBuilder().token(self.token).build()
            self._app = app

            # Register commands
            app.add_handler(CommandHandler("start", self._cmd_start))
            app.add_handler(CommandHandler("help", self._cmd_help))
            app.add_handler(CommandHandler("status", self._cmd_status))
            app.add_handler(CommandHandler("balance", self._cmd_balance))
            app.add_handler(CommandHandler("positions", self._cmd_positions))
            app.add_handler(CommandHandler("buy", self._cmd_buy))
            app.add_handler(CommandHandler("sell", self._cmd_sell))
            app.add_handler(CommandHandler("pnl", self._cmd_pnl))
            app.add_handler(CommandHandler("history", self._cmd_history))
            app.add_handler(CommandHandler("strategy", self._cmd_strategy))
            app.add_handler(CommandHandler("strategies", self._cmd_strategies))
            app.add_handler(CommandHandler("startbot", self._cmd_startbot))
            app.add_handler(CommandHandler("stopbot", self._cmd_stopbot))
            app.add_handler(CommandHandler("snapshot", self._cmd_snapshot))
            app.add_handler(CommandHandler("stats", self._cmd_stats))
            app.add_handler(CommandHandler("portfolio", self._cmd_portfolio))
            app.add_handler(CommandHandler("performance", self._cmd_performance))
            app.add_handler(CommandHandler("compare", self._cmd_compare))
            app.add_handler(CommandHandler("sentiment", self._cmd_sentiment))

            # Set bot commands menu
            commands = [
                BotCommand("status", "Engine status & portfolio"),
                BotCommand("balance", "Account balance"),
                BotCommand("positions", "Open positions"),
                BotCommand("buy", "Buy: /buy AAPL 10"),
                BotCommand("sell", "Sell: /sell AAPL 10"),
                BotCommand("pnl", "P&L report"),
                BotCommand("history", "Recent trades"),
                BotCommand("strategy", "Active strategy"),
                BotCommand("strategies", "List all strategies"),
                BotCommand("startbot", "Start trading engine"),
                BotCommand("stopbot", "Stop trading engine"),
                BotCommand("stats", "Overall statistics"),
                BotCommand("portfolio", "Full portfolio report"),
                BotCommand("performance", "Risk metrics & Sharpe"),
                BotCommand("compare", "Strategy comparison"),
                BotCommand("sentiment", "News sentiment analysis"),
                BotCommand("help", "Show all commands"),
            ]
            await app.bot.set_my_commands(commands)

            # Start polling
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)

            logger.info("✅ Telegram bot is polling for commands...")

            # Keep running
            stop_event = asyncio.Event()
            await stop_event.wait()

        # Run the async bot
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_setup_and_run())
        except Exception as e:
            logger.error(f"Telegram bot error: {e}")

    # ─── Security ─────────────────────────────────────────────────

    def _is_authorized(self, chat_id) -> bool:
        """Check if the chat ID is authorized to use the bot."""
        if not self.allowed_chat_ids:
            return True  # No restriction if no IDs configured
        return str(chat_id) in self.allowed_chat_ids

    async def _check_auth(self, update, context) -> bool:
        """Check authorization and send denial if unauthorized."""
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text(
                "⛔ Unauthorized. Your chat ID is not allowed.\n"
                f"Your ID: `{update.effective_chat.id}`",
                parse_mode="Markdown",
            )
            logger.warning(
                f"Unauthorized access attempt from chat_id: {update.effective_chat.id}"
            )
            return False
        return True

    # ─── Command Handlers ─────────────────────────────────────────

    async def _cmd_start(self, update, context) -> None:
        """Welcome message."""
        msg = (
            "⚡ *QuantumTrade Bot Controller*\n\n"
            "Control your trading system from Telegram!\n\n"
            "🔹 /status — Engine status\n"
            "🔹 /balance — Account balance\n"
            "🔹 /positions — Open positions\n"
            "🔹 /buy AAPL 10 — Buy shares\n"
            "🔹 /sell AAPL 10 — Sell shares\n"
            "🔹 /pnl — P&L report\n"
            "🔹 /history — Recent trades\n"
            "🔹 /startbot — Start trading\n"
            "🔹 /stopbot — Stop trading\n\n"
            f"Your Chat ID: `{update.effective_chat.id}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_help(self, update, context) -> None:
        """Show all available commands."""
        msg = (
            "📋 *All Commands:*\n\n"
            "*Trading:*\n"
            "  /buy `SYMBOL QTY` — Buy shares\n"
            "  /sell `SYMBOL QTY` — Sell shares\n\n"
            "*Portfolio:*\n"
            "  /status — Engine status\n"
            "  /balance — Cash & equity\n"
            "  /positions — Open positions\n"
            "  /pnl — Profit & Loss report\n"
            "  /history — Recent trades\n"
            "  /stats — Overall statistics\n"
            "  /snapshot — Save portfolio snapshot\n\n"
            "*Strategy:*\n"
            "  /strategy — Active strategy\n"
            "  /strategies — List all strategies\n\n"
            "*Engine:*\n"
            "  /startbot — Start trading engine\n"
            "  /stopbot — Stop trading engine\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_status(self, update, context) -> None:
        """Show engine status & portfolio overview."""
        if not await self._check_auth(update, context):
            return

        try:
            parts = ["⚡ *QuantumTrade Status*\n"]

            # Engine status
            if self.engine:
                status = self.engine.status()
                running = "🟢 Running" if status.get("running") else "🔴 Stopped"
                parts.append(f"Engine: {running}")
                parts.append(f"Strategy: {status.get('strategy', 'N/A')}")
                parts.append(f"Symbols: {', '.join(status.get('symbols', []))}")
                parts.append(f"Trades: {status.get('trade_count', 0)}")
                parts.append(f"Uptime: {status.get('uptime_minutes', 0):.1f} min\n")

            # Account info
            if self.broker and self.broker.is_connected:
                account = self.broker.get_account()
                parts.append(f"💰 Cash: ${account.cash:,.2f}")
                parts.append(f"📊 Equity: ${account.equity:,.2f}")
                parts.append(f"🛒 Buying Power: ${account.buying_power:,.2f}")
                parts.append(f"📈 Positions: {len(account.positions)}")
            else:
                parts.append("🔌 Broker: Not connected")

            # DB stats
            if self.db:
                stats = self.db.get_stats()
                parts.append(f"\n📊 Total P&L: ${stats['total_pnl']:+,.2f}")
                parts.append(f"📅 Today's P&L: ${stats['daily_pnl']:+,.2f}")

            await update.message.reply_text("\n".join(parts), parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_balance(self, update, context) -> None:
        """Show account balance."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.broker or not self.broker.is_connected:
                await update.message.reply_text("🔌 Broker not connected")
                return

            account = self.broker.get_account()
            msg = (
                "💰 *Account Balance*\n\n"
                f"Cash:         ${account.cash:,.2f}\n"
                f"Equity:       ${account.equity:,.2f}\n"
                f"Portfolio:    ${account.portfolio_value:,.2f}\n"
                f"Buying Power: ${account.buying_power:,.2f}\n"
                f"Positions:    {len(account.positions)}\n"
                f"Currency:     {account.currency}"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_positions(self, update, context) -> None:
        """List all open positions."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.broker or not self.broker.is_connected:
                await update.message.reply_text("🔌 Broker not connected")
                return

            positions = self.broker.get_positions()
            if not positions:
                await update.message.reply_text("📭 No open positions")
                return

            lines = ["📈 *Open Positions*\n"]
            for p in positions:
                emoji = "🟢" if p.unrealised_pnl >= 0 else "🔴"
                lines.append(
                    f"{emoji} *{p.symbol}*\n"
                    f"   Qty: {p.quantity} | Avg: ${p.avg_entry_price:,.2f}\n"
                    f"   Now: ${p.current_price:,.2f} | P&L: ${p.unrealised_pnl:+,.2f}"
                )

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_buy(self, update, context) -> None:
        """Manual buy order: /buy AAPL 10"""
        if not await self._check_auth(update, context):
            return

        try:
            args = context.args
            if not args or len(args) < 2:
                await update.message.reply_text(
                    "Usage: /buy `SYMBOL` `QUANTITY`\n"
                    "Example: /buy AAPL 10",
                    parse_mode="Markdown",
                )
                return

            symbol = args[0].upper()
            quantity = float(args[1])

            if not self.broker or not self.broker.is_connected:
                await update.message.reply_text("🔌 Broker not connected")
                return

            from brokers.base import BrokerOrder, OrderSide, OrderType

            # Get price
            price = self.broker.get_latest_price(symbol) or 0

            order = BrokerOrder(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=OrderType.MARKET,
                limit_price=price,
            )

            await update.message.reply_text(
                f"⏳ Placing BUY order: {quantity} {symbol}..."
            )

            result = self.broker.place_order(order)

            if result.is_filled:
                fill_price = result.filled_price or price
                msg = (
                    f"✅ *BUY Filled*\n\n"
                    f"Symbol: {symbol}\n"
                    f"Qty: {quantity}\n"
                    f"Price: ${fill_price:,.2f}\n"
                    f"Total: ${quantity * fill_price:,.2f}"
                )

                # Log to DB
                if self.trade_repo:
                    self.trade_repo.record_buy(
                        symbol=symbol,
                        quantity=quantity,
                        price=fill_price,
                        broker=self.broker.__class__.__name__,
                        order_id=result.order_id,
                    )
            else:
                msg = (
                    f"❌ *BUY Failed*\n\n"
                    f"Status: {result.status.value}\n"
                    f"Error: {result.raw_response}"
                )

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_sell(self, update, context) -> None:
        """Manual sell order: /sell AAPL 10"""
        if not await self._check_auth(update, context):
            return

        try:
            args = context.args
            if not args or len(args) < 2:
                await update.message.reply_text(
                    "Usage: /sell `SYMBOL` `QUANTITY`\n"
                    "Example: /sell AAPL 10",
                    parse_mode="Markdown",
                )
                return

            symbol = args[0].upper()
            quantity = float(args[1])

            if not self.broker or not self.broker.is_connected:
                await update.message.reply_text("🔌 Broker not connected")
                return

            from brokers.base import BrokerOrder, OrderSide, OrderType

            price = self.broker.get_latest_price(symbol) or 0

            # Check position for P&L calculation
            position = self.broker.get_position(symbol)
            entry_price = position.avg_entry_price if position else 0

            order = BrokerOrder(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                order_type=OrderType.MARKET,
                limit_price=price,
            )

            await update.message.reply_text(
                f"⏳ Placing SELL order: {quantity} {symbol}..."
            )

            result = self.broker.place_order(order)

            if result.is_filled:
                fill_price = result.filled_price or price
                pnl = (fill_price - entry_price) * quantity if entry_price else 0
                pnl_emoji = "📈" if pnl >= 0 else "📉"

                msg = (
                    f"✅ *SELL Filled*\n\n"
                    f"Symbol: {symbol}\n"
                    f"Qty: {quantity}\n"
                    f"Price: ${fill_price:,.2f}\n"
                    f"Total: ${quantity * fill_price:,.2f}\n"
                    f"{pnl_emoji} P&L: ${pnl:+,.2f}"
                )

                # Log to DB
                if self.trade_repo:
                    self.trade_repo.record_sell(
                        symbol=symbol,
                        quantity=quantity,
                        price=fill_price,
                        pnl=pnl,
                        broker=self.broker.__class__.__name__,
                        order_id=result.order_id,
                    )
            else:
                msg = (
                    f"❌ *SELL Failed*\n\n"
                    f"Status: {result.status.value}\n"
                    f"Error: {result.raw_response}"
                )

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_pnl(self, update, context) -> None:
        """Show P&L report."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.db:
                await update.message.reply_text("📁 Database not connected")
                return

            stats = self.db.get_stats()
            by_symbol = self.db.get_pnl_by_symbol()

            lines = [
                "📊 *P&L Report*\n",
                f"Total P&L:   ${stats['total_pnl']:+,.2f}",
                f"Today's P&L: ${stats['daily_pnl']:+,.2f}",
                f"Win Rate:    {stats['win_rate']:.1f}%",
                f"Total Trades: {stats['total_trades']}\n",
            ]

            if by_symbol:
                lines.append("*By Symbol:*")
                for s in by_symbol[:10]:
                    emoji = "🟢" if s["total_pnl"] >= 0 else "🔴"
                    lines.append(
                        f"  {emoji} {s['symbol']}: ${s['total_pnl']:+,.2f} "
                        f"({s['trade_count']} trades)"
                    )

            await update.message.reply_text(
                "\n".join(lines), parse_mode="Markdown"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_history(self, update, context) -> None:
        """Show recent trade history."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.db:
                await update.message.reply_text("📁 Database not connected")
                return

            trades = self.db.get_trades(limit=10)

            if not trades:
                await update.message.reply_text("📭 No trade history yet")
                return

            lines = ["📜 *Recent Trades*\n"]
            for t in trades:
                side_emoji = "🟢" if t["side"] == "BUY" else "🔴"
                pnl_str = f" P&L: ${t['pnl']:+,.2f}" if t["pnl"] else ""
                time_str = t["timestamp"][:16]  # Trim seconds
                lines.append(
                    f"{side_emoji} {t['side']} {t['quantity']} {t['symbol']} "
                    f"@ ${t['price']:,.2f}{pnl_str}\n"
                    f"   ⏰ {time_str} | 🎯 {t['strategy'] or 'Manual'}"
                )

            await update.message.reply_text(
                "\n".join(lines), parse_mode="Markdown"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_strategy(self, update, context) -> None:
        """Show or change active strategy."""
        if not await self._check_auth(update, context):
            return

        try:
            if self.engine:
                current = self.engine.strategy.name
                msg = f"🎯 Active Strategy: *{current}*"
            else:
                msg = "🔌 Engine not initialized"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_strategies(self, update, context) -> None:
        """List all available strategies."""
        try:
            from strategy import list_strategies
            strategies = list_strategies()

            lines = ["📈 *Available Strategies:*\n"]
            for i, name in enumerate(strategies, 1):
                lines.append(f"  {i}. {name}")

            await update.message.reply_text(
                "\n".join(lines), parse_mode="Markdown"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_startbot(self, update, context) -> None:
        """Start the trading engine."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.engine:
                await update.message.reply_text("🔌 Engine not initialized")
                return

            await update.message.reply_text("⏳ Starting trading engine...")

            # Start engine in background
            thread = threading.Thread(target=self.engine.start, daemon=True)
            thread.start()

            await update.message.reply_text(
                "🚀 *Trading engine started!*\n\n"
                "Use /status to check progress.\n"
                "Use /stopbot to stop.",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error starting engine: {e}")

    async def _cmd_stopbot(self, update, context) -> None:
        """Stop the trading engine."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.engine:
                await update.message.reply_text("🔌 Engine not initialized")
                return

            self.engine.stop()
            await update.message.reply_text(
                "🛑 *Trading engine stopped.*",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error stopping engine: {e}")

    async def _cmd_snapshot(self, update, context) -> None:
        """Take a portfolio snapshot."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.broker or not self.broker.is_connected:
                await update.message.reply_text("🔌 Broker not connected")
                return

            if not self.trade_repo:
                await update.message.reply_text("📁 Database not connected")
                return

            account = self.broker.get_account()
            self.trade_repo.take_snapshot(
                cash=account.cash,
                equity=account.equity,
                portfolio_value=account.portfolio_value,
                positions_count=len(account.positions),
            )

            await update.message.reply_text(
                "📸 *Snapshot saved!*\n\n"
                f"Cash: ${account.cash:,.2f}\n"
                f"Equity: ${account.equity:,.2f}\n"
                f"Positions: {len(account.positions)}",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_stats(self, update, context) -> None:
        """Show overall trading statistics."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self.db:
                await update.message.reply_text("📁 Database not connected")
                return

            stats = self.db.get_stats()

            msg = (
                "📊 *Trading Statistics*\n\n"
                f"Total Trades:  {stats['total_trades']}\n"
                f"Total P&L:     ${stats['total_pnl']:+,.2f}\n"
                f"Today's P&L:   ${stats['daily_pnl']:+,.2f}\n"
                f"Win Rate:      {stats['win_rate']:.1f}%\n"
                f"Wins/Losses:   {stats['wins']}/{stats['losses']}\n"
                f"Best Trade:    ${stats['best_trade']:+,.2f}\n"
                f"Worst Trade:   ${stats['worst_trade']:+,.2f}"
            )

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_portfolio(self, update, context) -> None:
        """Full portfolio report with positions & allocation."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self._portfolio_tracker:
                await update.message.reply_text("📊 Portfolio tracker not available")
                return

            self._portfolio_tracker.update()
            msg = self._portfolio_tracker.telegram_report()
            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_performance(self, update, context) -> None:
        """Show Sharpe ratio, drawdown, and risk metrics."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self._performance_analyzer:
                await update.message.reply_text("📊 Performance analyzer not available")
                return

            msg = self._performance_analyzer.telegram_report()
            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_compare(self, update, context) -> None:
        """Compare strategy performance."""
        if not await self._check_auth(update, context):
            return

        try:
            if not self._performance_analyzer:
                await update.message.reply_text("📊 Performance analyzer not available")
                return

            msg = self._performance_analyzer.strategy_comparison()
            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_sentiment(self, update, context) -> None:
        """Analyze news sentiment for symbols."""
        if not await self._check_auth(update, context):
            return

        try:
            from ai.sentiment import SentimentAnalyzer

            # Use provided symbols or engine symbols
            symbols = []
            if context.args:
                symbols = [s.upper() for s in context.args]
            elif self.engine:
                symbols = self.engine.symbols[:5]
            else:
                await update.message.reply_text(
                    "Usage: /sentiment AAPL GOOG MSFT",
                )
                return

            await update.message.reply_text(
                f"📰 Analyzing sentiment for {', '.join(symbols)}..."
            )

            analyzer = SentimentAnalyzer()
            msg = analyzer.telegram_report(symbols)
            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
