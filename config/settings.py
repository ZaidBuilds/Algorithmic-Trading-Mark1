from typing import List, Optional, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    """
    Centralized configuration for QuantumTrade.
    Reads from .env file and environment variables.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ─────────────────────────────────────────
    # Trading Mode
    # ─────────────────────────────────────────
    MODE: Literal["BACKTEST", "PAPER", "LIVE"] = Field(
        default="PAPER",
        description="Operating mode: BACKTEST, PAPER, or LIVE"
    )

    # ─────────────────────────────────────────
    # Broker Configuration
    # ─────────────────────────────────────────
    BROKER_NAME: str = Field(
        default="paper",
        description="Broker to use: 'alpaca', 'binance', or 'paper'"
    )
    API_KEY: Optional[str] = Field(default=None, description="Broker API key")
    API_SECRET: Optional[str] = Field(default=None, description="Broker API secret")
    BASE_URL: Optional[str] = Field(default=None, description="Broker API base URL")
    PAPER_TRADING: bool = Field(
        default=True,
        description="Use paper/testnet mode (set False for real money)"
    )

    # ── Alpaca-specific
    ALPACA_API_KEY: Optional[str] = Field(default=None)
    ALPACA_API_SECRET: Optional[str] = Field(default=None)
    ALPACA_PAPER: bool = Field(default=True)

    # ── Binance-specific
    BINANCE_API_KEY: Optional[str] = Field(default=None)
    BINANCE_API_SECRET: Optional[str] = Field(default=None)
    BINANCE_TESTNET: bool = Field(default=True)

    # ─────────────────────────────────────────
    # Strategy
    # ─────────────────────────────────────────
    STRATEGY_NAME: str = Field(
        default="EMA Crossover",
        description="Active strategy name from the strategy registry"
    )

    # ─────────────────────────────────────────
    # Trading Parameters
    # ─────────────────────────────────────────
    SYMBOLS: List[str] = Field(
        default_factory=lambda: ["AAPL", "GOOG"],
        description="List of symbols to trade"
    )
    TIMEFRAME: str = Field(
        default="1d",
        description="Timeframe: '1m', '5m', '15m', '1h', '1d'"
    )
    INITIAL_CAPITAL: float = Field(
        default=100_000.0,
        description="Initial trading capital in USD"
    )
    DEFAULT_ORDER_SIZE: float = Field(
        default=1.0,
        description="Default number of shares/units per order"
    )

    # ─────────────────────────────────────────
    # Risk Management
    # ─────────────────────────────────────────
    MAX_POSITION_SIZE_PCT: float = Field(default=0.10, description="Max 10% per position")
    STOP_LOSS_PCT: float = Field(default=0.02, description="2% stop-loss")
    TAKE_PROFIT_PCT: float = Field(default=0.04, description="4% take-profit")
    MAX_DAILY_LOSS_PCT: float = Field(default=0.05, description="5% daily loss limit")
    MAX_OPEN_POSITIONS: int = Field(default=10, description="Max simultaneous positions")
    MIN_CASH_RESERVE_PCT: float = Field(default=0.20, description="Keep 20% cash reserve")

    # ─────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────
    TRADING_INTERVAL_SECONDS: int = Field(
        default=300,
        description="Seconds between trading ticks (300 = 5 min)"
    )
    RESPECT_MARKET_HOURS: bool = Field(
        default=True,
        description="Only trade during regular market hours"
    )

    # ─────────────────────────────────────────
    # Notifications
    # ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None)
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None)
    DISCORD_WEBHOOK_URL: Optional[str] = Field(default=None)
    EMAIL_SMTP_HOST: Optional[str] = Field(default=None)
    EMAIL_SMTP_PORT: int = Field(default=587)
    EMAIL_USER: Optional[str] = Field(default=None)
    EMAIL_PASSWORD: Optional[str] = Field(default=None)
    EMAIL_TO: Optional[str] = Field(default=None)

    # ─────────────────────────────────────────
    # Data & Logging
    # ─────────────────────────────────────────
    DATA_DIR: str = Field(default="data", description="Data directory")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FILE: str = Field(default="logs/trading_bot.log", description="Log file path")

    # ─────────────────────────────────────────
    # Backtesting
    # ─────────────────────────────────────────
    BACKTEST_START_DATE: str = "2023-01-01"
    BACKTEST_END_DATE: str = "2023-12-31"
    COMMISSION_PCT: float = Field(default=0.001, description="0.1% commission per trade")

    # ─────────────────────────────────────────
    # AI / ML
    # ─────────────────────────────────────────
    OLLAMA_HOST: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL: str = Field(default="qwen2.5-coder:1.5b")
    ML_MODEL_PATH: str = Field(default="models/")
    ML_RETRAIN_DAYS: int = Field(default=30, description="Retrain ML model every N days")

    def __init__(self, **values):
        super().__init__(**values)
        os.makedirs(self.DATA_DIR, exist_ok=True)
        log_dir = os.path.dirname(self.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)


settings = Settings()