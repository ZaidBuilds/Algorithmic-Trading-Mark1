from typing import List, Optional, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import os
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Centralized configuration for QuantumTrade.
    Reads from .env file, environment variables, and YAML config.

    Priority: env vars > YAML file > .env file > defaults
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="QT_",  # Optional prefix for QuantumTrade-specific vars
    )

    # ─────────────────────────────────────────────────────────────
    # Event Bus / Message Queue (NEW)
    # ─────────────────────────────────────────────────────────────
    MESSAGE_BUS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for event bus"
    )
    EVENT_STREAM_MAX_LEN: int = Field(
        default=10000,
        ge=100,
        le=1000000,
        description="Max Redis stream length"
    )
    CONSUMER_GROUP: str = Field(
        default="quantumtrade",
        description="Redis consumer group name prefix"
    )
    EVENT_RETENTION_MS: int = Field(
        default=604800000,  # 7 days in milliseconds
        ge=60000,
        description="Stream retention period (ms)"
    )
    DEAD_LETTER_QUEUE_ENABLED: bool = Field(
        default=True,
        description="Enable dead-letter queue for failed events"
    )
    CONFIG_YAML_PATH: str = Field(
        default="config/quantumtrade.yaml",
        description="Path to YAML config file"
    )

    # ─────────────────────────────────────────────────────────────
    # Trading Mode
    # ─────────────────────────────────────────────────────────────
    MODE: Literal["BACKTEST", "PAPER", "LIVE"] = Field(
        default="PAPER",
        description="Operating mode: BACKTEST, PAPER, or LIVE"
    )

    # ─────────────────────────────────────────────────────────────
    # Broker Configuration
    # ─────────────────────────────────────────────────────────────
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
    ALPACA_API_KEY: Optional[str] = Field(default=None, min_length=5)
    ALPACA_API_SECRET: Optional[str] = Field(default=None, min_length=5)
    ALPACA_PAPER: bool = Field(default=True)

    # ── Binance-specific
    BINANCE_API_KEY: Optional[str] = Field(default=None, min_length=5)
    BINANCE_API_SECRET: Optional[str] = Field(default=None, min_length=5)
    BINANCE_TESTNET: bool = Field(default=True)

    # ─────────────────────────────────────────────────────────────
    # Strategy
    # ─────────────────────────────────────────────────────────────
    STRATEGY_NAME: str = Field(
        default="EMA Crossover",
        description="Active strategy name from the strategy registry"
    )

    # ─────────────────────────────────────────────────────────────
    # Trading Parameters
    # ─────────────────────────────────────────────────────────────
    SYMBOLS: List[str] = Field(
        default_factory=lambda: ["AAPL", "GOOG"],
        description="List of symbols to trade"
    )

    @field_validator("SYMBOLS", mode="before")
    def _parse_symbols(cls, value):
        if isinstance(value, str):
            return [symbol.strip() for symbol in value.split(",") if symbol.strip()]
        return value

    TIMEFRAME: str = Field(
        default="1d",
        description="Timeframe: '1m', '5m', '15m', '1h', '1d'"
    )
    INITIAL_CAPITAL: float = Field(
        default=100_000.0,
        gt=0,
        description="Initial trading capital in USD"
    )
    DEFAULT_ORDER_SIZE: float = Field(
        default=1.0,
        gt=0,
        description="Default number of shares/units per order"
    )

    # ─────────────────────────────────────────────────────────────
    # Risk Management
    # ─────────────────────────────────────────────────────────────
    MAX_POSITION_SIZE_PCT: float = Field(default=0.10, ge=0.01, le=1.0, description="Max 10% per position")
    STOP_LOSS_PCT: float = Field(default=0.02, ge=0.001, le=0.5, description="2% stop-loss")
    TAKE_PROFIT_PCT: float = Field(default=0.04, ge=0.001, le=1.0, description="4% take-profit")
    MAX_DAILY_LOSS_PCT: float = Field(default=0.05, ge=0.001, le=0.5, description="5% daily loss limit")
    MAX_OPEN_POSITIONS: int = Field(default=10, ge=1, le=100, description="Max simultaneous positions")
    MIN_CASH_RESERVE_PCT: float = Field(default=0.20, ge=0.0, le=0.9, description="Keep 20% cash reserve")

    # ─────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────
    TRADING_INTERVAL_SECONDS: int = Field(
        default=300,
        ge=10,
        description="Seconds between trading ticks (300 = 5 min)"
    )
    RESPECT_MARKET_HOURS: bool = Field(
        default=True,
        description="Only trade during regular market hours"
    )

    # ─────────────────────────────────────────────────────────────
    # Notifications
    # ─────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None)
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None)
    DISCORD_WEBHOOK_URL: Optional[str] = Field(default=None)
    EMAIL_SMTP_HOST: Optional[str] = Field(default=None)
    EMAIL_SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    EMAIL_USER: Optional[str] = Field(default=None)
    EMAIL_PASSWORD: Optional[str] = Field(default=None)
    EMAIL_TO: Optional[str] = Field(default=None)

    # ─────────────────────────────────────────────────────────────
    # Data & Logging
    # ─────────────────────────────────────────────────────────────
    DATA_DIR: str = Field(default="data", description="Data directory")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FILE: str = Field(default="logs/trading_bot.log", description="Log file path")

    # ─────────────────────────────────────────────────────────────
    # Backtesting
    # ─────────────────────────────────────────────────────────────
    BACKTEST_START_DATE: str = "2023-01-01"
    BACKTEST_END_DATE: str = "2023-12-31"
    COMMISSION_PCT: float = Field(default=0.001, description="0.1% commission per trade")

    # ─────────────────────────────────────────────────────────────
    # AI / ML
    # ─────────────────────────────────────────────────────────────
    OLLAMA_HOST: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL: str = Field(default="qwen2.5-coder:1.5b")
    ML_MODEL_PATH: str = Field(default="models/")
    ML_RETRAIN_DAYS: int = Field(default=30, ge=1, description="Retrain ML model every N days")

    # ─────────────────────────────────────────────────────────────
    # MLOps / Model Lifecycle
    # ─────────────────────────────────────────────────────────────
    # MLflow
    MLFLOW_TRACKING_URI: str = Field(
        default="http://localhost:5000",
        description="MLflow tracking server URI"
    )
    MLFLOW_ARTIFACT_LOCATION: str = Field(
        default="./mlflow_artifacts",
        description="Model artifact storage location"
    )
    MLFLOW_EXPERIMENT_NAME: str = Field(
        default="quantumtrade_models",
        description="MLflow experiment name"
    )
    
    # Retraining
    RETRAINING_ENABLED: bool = Field(default=True, description="Enable automated retraining")
    RETRAINING_SCHEDULE: str = Field(
        default="0 2 * * *",
        description="Cron schedule for retraining"
    )
    RETRAINING_MIN_SAMPLES: int = Field(default=1000, ge=100)
    RETRAINING_PERFORMANCE_THRESHOLD: float = Field(
        default=0.55, ge=0.0, le=1.0
    )
    RETRAINING_IMPROVEMENT_THRESHOLD: float = Field(
        default=0.02, ge=0.0, le=0.5
    )
    RETRAINING_CANARY_CAPITAL_PCT: float = Field(default=0.01, ge=0.001, le=0.1)
    RETRAINING_CANARY_DURATION_HOURS: int = Field(default=24, ge=1, le=168)
    RETRAINING_PHASE2_CAPITAL_PCT: float = Field(default=0.05)
    RETRAINING_PHASE2_DURATION_DAYS: int = Field(default=3)
    RETRAINING_PHASE3_CAPITAL_PCT: float = Field(default=0.25)
    RETRAINING_PHASE3_DURATION_DAYS: int = Field(default=7)
    RETRAINING_LOOKBACK_DAYS: int = Field(default=90, ge=30)
    
    # Drift Detection
    DRIFT_ENABLED: bool = Field(default=True)
    DRIFT_CHECK_INTERVAL_MINUTES: int = Field(default=60, ge=5, le=1440)
    DRIFT_PSI_THRESHOLD: float = Field(default=0.2, ge=0.0, le=1.0)
    DRIFT_KS_ALPHA: float = Field(default=0.05, ge=0.001, le=0.1)
    DRIFT_ACCURACY_DROP_THRESHOLD: float = Field(default=0.05, ge=0.0, le=0.5)
    DRIFT_CONFIDENCE_DROP_THRESHOLD: float = Field(default=0.10, ge=0.0, le=0.5)
    DRIFT_WINDOW_SIZE: int = Field(default=1000, ge=100, le=10000)
    
    # Feature Store
    FEATURE_STORE_BACKEND: str = Field(
        default="redis",
        pattern=r"^(redis|postgres|hybrid)$"
    )
    FEATURE_STORE_TTL_SECONDS: int = Field(default=3600, ge=60, le=86400)
    FEATURE_STORE_PREFIX: str = Field(default="features:")
    
    # Model Serving
    SERVING_HOST: str = Field(default="0.0.0.0")
    SERVING_PORT: int = Field(default=8001, ge=1024, le=65535)
    SERVING_WORKERS: int = Field(default=2, ge=1, le=16)
    SERVING_MODEL_CACHE_SIZE: int = Field(default=10, ge=1, le=100)
    SERVING_PREDICTION_CACHE_TTL: int = Field(default=60, ge=1, le=3600)

    # ─────────────────────────────────────────────────────────────
    # YAML Config Loading
    # ─────────────────────────────────────────────────────────────
    def load_yaml_config(self, path: Optional[str] = None) -> None:
        """Load configuration from YAML file.

        Overlays YAML values over existing settings.
        Environment variables always take precedence.

        Args:
            path: Path to YAML file (default: CONFIG_YAML_PATH)
        """
        try:
            import yaml
            from pathlib import Path

            config_path = Path(path or self.CONFIG_YAML_PATH)
            if not config_path.exists():
                logger.warning(f"YAML config not found: {config_path}")
                return

            with open(config_path) as f:
                yaml_data = yaml.safe_load(f) or {}

            # Top-level flat fields (direct mapping)
            flat_fields = [
                "BROKER_NAME", "SYMBOLS", "TIMEFRAME", "INITIAL_CAPITAL",
                "TRADING_INTERVAL_SECONDS", "RESPECT_MARKET_HOURS",
                "DATA_DIR", "LOG_LEVEL", "LOG_FILE",
                "PAPER_TRADING", "ALPACA_PAPER", "BINANCE_TESTNET",
                "MESSAGE_BUS_URL", "EVENT_STREAM_MAX_LEN", "CONSUMER_GROUP",
                "EVENT_RETENTION_MS", "DEAD_LETTER_QUEUE_ENABLED",
                # MLOps flat fields
                "MLFLOW_TRACKING_URI", "MLFLOW_ARTIFACT_LOCATION", "MLFLOW_EXPERIMENT_NAME",
                "RETRAINING_ENABLED", "RETRAINING_SCHEDULE", "RETRAINING_MIN_SAMPLES",
                "RETRAINING_PERFORMANCE_THRESHOLD", "RETRAINING_IMPROVEMENT_THRESHOLD",
                "RETRAINING_CANARY_CAPITAL_PCT", "RETRAINING_CANARY_DURATION_HOURS",
                "RETRAINING_PHASE2_CAPITAL_PCT", "RETRAINING_PHASE2_DURATION_DAYS",
                "RETRAINING_PHASE3_CAPITAL_PCT", "RETRAINING_PHASE3_DURATION_DAYS",
                "RETRAINING_LOOKBACK_DAYS",
                "DRIFT_ENABLED", "DRIFT_CHECK_INTERVAL_MINUTES", "DRIFT_PSI_THRESHOLD",
                "DRIFT_KS_ALPHA", "DRIFT_ACCURACY_DROP_THRESHOLD",
                "DRIFT_CONFIDENCE_DROP_THRESHOLD", "DRIFT_WINDOW_SIZE",
                "FEATURE_STORE_BACKEND", "FEATURE_STORE_TTL_SECONDS", "FEATURE_STORE_PREFIX",
                "SERVING_HOST", "SERVING_PORT", "SERVING_WORKERS",
                "SERVING_MODEL_CACHE_SIZE", "SERVING_PREDICTION_CACHE_TTL",
            ]
            for field in flat_fields:
                if field in yaml_data:
                    setattr(self, field, yaml_data[field])

            # Section-based overrides
            sections = [
                ("database", self),
                ("redis", self),
                ("broker", self),
                ("strategy", self),
                ("risk", self),
                ("notifications", self),
                ("logging", self),
                ("api", self),
                ("event_bus", self),
            ]
            
            for section, target in sections:
                if section in yaml_data:
                    for key, value in yaml_data[section].items():
                        attr = key.upper()
                        if hasattr(target, attr):
                            setattr(target, attr, value)
            
            # Flat mlops config reader
            if "mlops" in yaml_data:
                ml_data = yaml_data["mlops"]
                ml_flat_map = {
                    "tracking_uri": "MLFLOW_TRACKING_URI",
                    "artifact_location": "MLFLOW_ARTIFACT_LOCATION",
                    "experiment_name": "MLFLOW_EXPERIMENT_NAME",
                    "retraining.enabled": "RETRAINING_ENABLED",
                    "retraining.schedule": "RETRAINING_SCHEDULE",
                    "retraining.min_samples": "RETRAINING_MIN_SAMPLES",
                    "retraining.performance_threshold": "RETRAINING_PERFORMANCE_THRESHOLD",
                    "retraining.improvement_threshold": "RETRAINING_IMPROVEMENT_THRESHOLD",
                    "retraining.canary_capital_pct": "RETRAINING_CANARY_CAPITAL_PCT",
                    "retraining.canary_duration_hours": "RETRAINING_CANARY_DURATION_HOURS",
                    "retraining.phase2_capital_pct": "RETRAINING_PHASE2_CAPITAL_PCT",
                    "retraining.phase2_duration_days": "RETRAINING_PHASE2_DURATION_DAYS",
                    "retraining.phase3_capital_pct": "RETRAINING_PHASE3_CAPITAL_PCT",
                    "retraining.phase3_duration_days": "RETRAINING_PHASE3_DURATION_DAYS",
                    "retraining.lookback_days": "RETRAINING_LOOKBACK_DAYS",
                    "drift.enabled": "DRIFT_ENABLED",
                    "drift.check_interval_minutes": "DRIFT_CHECK_INTERVAL_MINUTES",
                    "drift.psi_threshold": "DRIFT_PSI_THRESHOLD",
                    "drift.ks_alpha": "DRIFT_KS_ALPHA",
                    "drift.accuracy_drop_threshold": "DRIFT_ACCURACY_DROP_THRESHOLD",
                    "drift.confidence_drop_threshold": "DRIFT_CONFIDENCE_DROP_THRESHOLD",
                    "drift.window_size": "DRIFT_WINDOW_SIZE",
                    "feature_store.backend": "FEATURE_STORE_BACKEND",
                    "feature_store.ttl_seconds": "FEATURE_STORE_TTL_SECONDS",
                    "feature_store.prefix": "FEATURE_STORE_PREFIX",
                    "serving.host": "SERVING_HOST",
                    "serving.port": "SERVING_PORT",
                    "serving.workers": "SERVING_WORKERS",
                    "serving.model_cache_size": "SERVING_MODEL_CACHE_SIZE",
                    "serving.prediction_cache_ttl": "SERVING_PREDICTION_CACHE_TTL",
                }
                
                for dot_path, attr_name in ml_flat_map.items():
                    parts = dot_path.split(".")
                    if len(parts) == 2:
                        section_key, field = parts
                        if section_key in ml_data and field in ml_data[section_key]:
                            setattr(self, attr_name, ml_data[section_key][field])
                    elif dot_path in ml_data:
                        setattr(self, attr_name, ml_data[dot_path])

            logger.info(f"Loaded YAML config from {config_path}")

        except ImportError:
            logger.error("PyYAML not installed. Cannot load YAML config.")
        except Exception as e:
            logger.error(f"YAML config load failed: {e}")

    def __init__(self, **values):
        super().__init__(**values)
        # Ensure directories exist
        os.makedirs(self.DATA_DIR, exist_ok=True)
        log_dir = os.path.dirname(self.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Try to load YAML config (doesn't fail if missing)
        self.load_yaml_config()


settings = Settings()