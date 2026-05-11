"""Configuration schema validation with Pydantic v2.
 
Defines strongly-typed configuration models with validation:
- DatabaseConfig
- RedisConfig
- BrokerConfig (with API key validation)
- StrategyConfig
- RiskConfig
- NotificationConfig
- LoggingConfig
- APIConfig
- MultiExchangeConfig (arbitrage, risk limits, symbol mappings)
- ArbitrageConfig
- ExchangeMapping
- MultiExchangeRiskLimits
 
All settings inherit from pydantic.BaseSettings for env var support.
"""

from __future__ import annotations

from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


# ─────────────────────────────────────────────────────────────────────────────
# Sub-configs
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseConfig(BaseModel):
    """Database connection settings."""
    model_config = ConfigDict(extra="ignore")

    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL port")
    POSTGRES_USER: str = Field(default="quantum", description="Database user")
    POSTGRES_PASSWORD: str = Field(default="quantum", description="Database password")
    POSTGRES_DB: str = Field(default="quantumtrade", description="Database name")
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=50, description="Connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, description="Max overflow connections")

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL URL."""
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


class RedisConfig(BaseModel):
    """Redis connection settings."""
    model_config = ConfigDict(extra="ignore")

    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    REDIS_DB: int = Field(default=0, ge=0, le=15, description="Redis DB number")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")

    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


class BrokerConfig(BaseModel):
    """Broker API configuration."""
    model_config = ConfigDict(extra="ignore")

    BROKER_NAME: Literal["alpaca", "binance", "paper"] = Field(
        default="paper",
        description="Broker to use"
    )
    API_KEY: Optional[str] = Field(default=None, min_length=5, description="API key")
    API_SECRET: Optional[str] = Field(default=None, min_length=5, description="API secret")

    # Alpaca-specific
    ALPACA_API_KEY: Optional[str] = Field(default=None, min_length=5)
    ALPACA_API_SECRET: Optional[str] = Field(default=None, min_length=5)
    ALPACA_PAPER: bool = Field(default=True, description="Use Alpaca paper trading")

    # Binance-specific
    BINANCE_API_KEY: Optional[str] = Field(default=None, min_length=5)
    BINANCE_API_SECRET: Optional[str] = Field(default=None, min_length=5)
    BINANCE_TESTNET: bool = Field(default=True, description="Use Binance testnet")

    PAPER_TRADING: bool = Field(default=True, description="Enable paper trading mode")

    @field_validator("API_KEY", "API_SECRET", "ALPACA_API_KEY", "ALPACA_API_SECRET",
                     "BINANCE_API_KEY", "BINANCE_API_SECRET")
    @classmethod
    def validate_api_key_length(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) < 5:
            raise ValueError("API key too short (min 5 chars)")
        return v


class StrategyConfig(BaseModel):
    """Strategy configuration."""
    model_config = ConfigDict(extra="ignore")

    STRATEGY_NAME: str = Field(
        default="EMA Crossover",
        description="Name of active strategy"
    )
    TIMEFRAME: str = Field(
        default="5m",
        pattern=r"^\d+[mhdMHD]$",
        description="Candlestick timeframe (e.g., 1m, 5m, 1h, 1d)"
    )
    INITIAL_CAPITAL: float = Field(
        default=100_000.0,
        gt=0,
        description="Initial trading capital"
    )
    DEFAULT_ORDER_SIZE: float = Field(
        default=1.0,
        gt=0,
        description="Default shares per order"
    )
    # ML config
    ML_MODEL_PATH: str = Field(default="models/", description="ML model directory")
    ML_RETRAIN_DAYS: int = Field(default=30, ge=1, description="ML retrain interval (days)")
    # AI config
    OLLAMA_HOST: str = Field(default="http://localhost:11434", description="Ollama API URL")
    OLLAMA_MODEL: str = Field(default="qwen2.5-coder:1.5b", description="Ollama model name")


class RiskConfig(BaseModel):
    """Risk management parameters."""
    model_config = ConfigDict(extra="ignore")

    MAX_POSITION_SIZE_PCT: float = Field(
        default=0.10,
        ge=0.01,
        le=1.0,
        description="Max allocation per position (as fraction)"
    )
    STOP_LOSS_PCT: float = Field(
        default=0.02,
        ge=0.001,
        le=0.5,
        description="Stop-loss threshold"
    )
    TAKE_PROFIT_PCT: float = Field(
        default=0.04,
        ge=0.001,
        le=1.0,
        description="Take-profit threshold"
    )
    MAX_DAILY_LOSS_PCT: float = Field(
        default=0.05,
        ge=0.001,
        le=0.5,
        description="Max daily loss limit"
    )
    MAX_OPEN_POSITIONS: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Max concurrent positions"
    )
    MIN_CASH_RESERVE_PCT: float = Field(
        default=0.20,
        ge=0.0,
        le=0.9,
        description="Minimum cash reserve ratio"
    )
    MAX_DAILY_TRADES: int = Field(default=50, ge=1, description="Max trades per day")
    VAR_95_CONFIDENCE: float = Field(default=0.05, description="VaR 95% threshold")

    # Position Sizing Configuration
    POSITION_SIZING_STRATEGY: str = Field(
        default="fixed_fractional",
        pattern="^(fixed_fractional|kelly|volatility_adjusted|equal_risk|confidence_weighted|composite)$",
        description="Position sizing algorithm to use"
    )
    RISK_PER_TRADE_PCT: float = Field(
        default=0.02,
        ge=0.001,
        le=0.10,
        description="Risk per trade as % of portfolio"
    )
    KELLY_FRACTION_CAP: float = Field(
        default=0.05,
        ge=0.001,
        le=0.50,
        description="Maximum Kelly fraction (half-Kelly safety cap)"
    )
    TARGET_VOLATILITY: float = Field(
        default=0.20,
        ge=0.05,
        le=1.0,
        description="Target annual volatility for vol-adjusted sizing"
    )


class NotificationConfig(BaseModel):
    """Notification service configuration."""
    model_config = ConfigDict(extra="ignore")

    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, description="Telegram bot token")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None, description="Telegram chat ID")
    DISCORD_WEBHOOK_URL: Optional[str] = Field(default=None, description="Discord webhook URL")
    EMAIL_SMTP_HOST: Optional[str] = Field(default=None, description="SMTP host")
    EMAIL_SMTP_PORT: int = Field(default=587, ge=1, le=65535, description="SMTP port")
    EMAIL_USER: Optional[str] = Field(default=None, description="SMTP username")
    EMAIL_PASSWORD: Optional[str] = Field(default=None, description="SMTP password")
    EMAIL_TO: Optional[str] = Field(default=None, description="Notification recipient")
    NOTIFICATION_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Minimum notification level"
    )


class BacktestSimulationConfig(BaseModel):
    """Advanced backtesting simulation configuration."""
    model_config = ConfigDict(extra="ignore")

    # Slippage model
    SLIPPAGE_MODEL: str = Field(
        default="volume", 
        pattern="^(fixed|volume|sqrt|impact)$",
        description="Slippage model type"
    )
    FIXED_SLIPPAGE_BPS: float = Field(
        default=1.0, ge=0.0, le=100.0,
        description="Fixed slippage in basis points"
    )
    IMPACT_ETA: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="Permanent impact coefficient (Almgren-Chriss η)"
    )
    IMPACT_EPSILON: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Temporary impact coefficient (Almgren-Chriss ε)"
    )
    
    # Latency
    LATENCY_MS: float = Field(
        default=150.0, ge=0.0, le=10000.0,
        description="Mean execution latency in milliseconds"
    )
    
    # Spread
    SPREAD_BPS: float = Field(
        default=1.0, ge=0.0, le=100.0,
        description="Bid-ask spread in basis points"
    )
    
    # Liquidity
    PARTICIPATION_RATE: float = Field(
        default=0.10, ge=0.01, le=1.0,
        description="Max participation rate per bar (fraction of volume)"
    )
    ENABLE_LIQUIDITY_CONSTRAINTS: bool = Field(
        default=False,
        description="Enable partial fills and volume limits"
    )
    
    # Feature flags
    ENABLE_MARKET_IMPACT: bool = Field(
        default=True,
        description="Enable market impact modeling"
    )
    ENABLE_GAP_RISK: bool = Field(
        default=True,
        description="Enable overnight gap modeling"
    )
    ENABLE_CIRCUIT_BREAKERS: bool = Field(
        default=False,
        description="Enable exchange circuit breaker modeling"
    )
    
    # Walk-forward optimization
    WALK_FORWARD_ENABLED: bool = Field(
        default=False,
        description="Enable walk-forward optimization mode"
    )
    WF_TRAIN_WINDOW_DAYS: int = Field(
        default=252, ge=10, le=2520,
        description="Training window length in trading days"
    )
    WF_TEST_WINDOW_DAYS: int = Field(
        default=63, ge=5, le=252,
        description="Testing window length"
    )
    WF_ANCHORED: bool = Field(
        default=False,
        description="Use anchored (expanding) training windows"
    )
    
    # Monte Carlo
    MONTE_CARLO_ENABLED: bool = Field(
        default=False,
        description="Enable Monte Carlo robustness testing"
    )
    MC_SIMULATIONS: int = Field(
        default=10000, ge=1000, le=100000,
        description="Number of Monte Carlo simulations"
    )
    MC_BOOTSTRAP_METHOD: str = Field(
        default="iid",
        pattern="^(iid|block|randomize)$",
        description="Bootstrap method: iid, block, or randomize"
    )
    MC_BLOCK_SIZE: int = Field(
        default=10, ge=1, le=100,
        description="Block size for block bootstrap"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""
    model_config = ConfigDict(extra="ignore")

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Log level"
    )
    LOG_FILE: str = Field(default="logs/trading_bot.log", description="Log file path")
    JSON_LOGS: bool = Field(default=False, description="Use JSON log format")
    LOG_ROTATION: str = Field(default="daily", description="Log rotation policy")


# ─────────────────────────────────────────────────────────────────────────────
# MLOps / Model Lifecycle Configuration (NEW)
# ─────────────────────────────────────────────────────────────────────────────

class MLflowConfig(BaseModel):
    """MLflow tracking server configuration."""
    model_config = ConfigDict(extra="ignore")

    TRACKING_URI: str = Field(
        default="http://localhost:5000",
        description="MLflow tracking server URI"
    )
    ARTIFACT_LOCATION: str = Field(
        default="s3://quantumtrade-models/",
        description="Model artifact storage location"
    )
    EXPERIMENT_NAME: str = Field(
        default="quantumtrade_models",
        description="Default experiment name"
    )


class RetrainingConfig(BaseModel):
    """Automated retraining pipeline configuration."""
    model_config = ConfigDict(extra="ignore")

    ENABLED: bool = Field(default=True, description="Enable automated retraining")
    SCHEDULE: str = Field(
        default="0 2 * * *",
        description="Cron schedule for retraining (default: daily at 2am UTC)"
    )
    MIN_SAMPLES: int = Field(
        default=1000,
        ge=100,
        description="Minimum new samples required to trigger retraining"
    )
    PERFORMANCE_THRESHOLD: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="Minimum accuracy threshold for model acceptance"
    )
    IMPROVEMENT_THRESHOLD: float = Field(
        default=0.02,
        ge=0.0,
        le=0.5,
        description="Required improvement over current production (e.g., 2%)"
    )
    # Canary deployment
    CANARY_CAPITAL_PCT: float = Field(
        default=0.01,
        ge=0.001,
        le=0.1,
        description="% of capital allocated during canary phase"
    )
    CANARY_DURATION_HOURS: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Canary phase duration in hours"
    )
    # Phase rollout percentages (final total = 100%)
    PHASE2_CAPITAL_PCT: float = Field(default=0.05, description="Phase 2 capital allocation")
    PHASE3_CAPITAL_PCT: float = Field(default=0.25, description="Phase 3 capital allocation")
    PHASE2_DURATION_DAYS: int = Field(default=3, description="Phase 2 duration in days")
    PHASE3_DURATION_DAYS: int = Field(default=7, description="Phase 3 duration in days")


class DriftConfig(BaseModel):
    """Drift detection configuration."""
    model_config = ConfigDict(extra="ignore")

    ENABLED: bool = Field(default=True, description="Enable drift monitoring")
    CHECK_INTERVAL_MINUTES: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="How often to check for drift"
    )
    # Data drift thresholds
    PSI_THRESHOLD: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Population Stability Index threshold (>0.2 is significant)"
    )
    KS_ALPHA: float = Field(
        default=0.05,
        ge=0.001,
        le=0.1,
        description="Kolmogorov-Smirnov test alpha (p-value threshold)"
    )
    # Concept drift thresholds
    ACCURACY_DROP_THRESHOLD: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description="Accuracy drop percentage to trigger retrain"
    )
    CONFIDENCE_DROP_THRESHOLD: float = Field(
        default=0.10,
        ge=0.0,
        le=0.5,
        description="Average prediction confidence drop threshold"
    )
    WINRATE_DROP_THRESHOLD: float = Field(
        default=0.10,
        ge=0.0,
        le=0.5,
        description="Trading win rate drop threshold"
    )
    WINDOW_SIZE: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Number of recent predictions to evaluate"
    )


class FeatureStoreConfig(BaseModel):
    """Feature store configuration."""
    model_config = ConfigDict(extra="ignore")

    BACKEND: Literal["redis", "postgres", "hybrid"] = Field(
        default="redis",
        description="Feature store backend"
    )
    REDIS_KEYS_PREFIX: str = Field(
        default="features:",
        description="Redis key prefix for features"
    )
    TTL_SECONDS: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Default TTL for cached features"
    )
    BATCH_SIZE: int = Field(
        default=1000,
        ge=100,
        description="Batch size for feature computation"
    )


class ServingConfig(BaseModel):
    """Model serving configuration."""
    model_config = ConfigDict(extra="ignore")

    HOST: str = Field(default="0.0.0.0", description="Serving host")
    PORT: int = Field(default=8001, ge=1024, le=65535, description="Serving port")
    WORKERS: int = Field(default=2, ge=1, le=16, description="Number of worker processes")
    MODEL_CACHE_SIZE: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of models to keep in memory"
    )
    PREDICTION_CACHE_TTL: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Prediction cache TTL in seconds"
    )
    TIMEOUT_SECONDS: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Request timeout"
    )


class MLOpsConfig(BaseModel):
    """Complete MLOps system configuration."""
    model_config = ConfigDict(extra="ignore")

    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)
    retraining: RetrainingConfig = Field(default_factory=RetrainingConfig)
    drift: DriftConfig = Field(default_factory=DriftConfig)
    feature_store: FeatureStoreConfig = Field(default_factory=FeatureStoreConfig)
    serving: ServingConfig = Field(default_factory=ServingConfig)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Exchange / Arbitrage Configuration
# ─────────────────────────────────────────────────────────────────────────────

class ArbitrageConfig(BaseModel):
    """Arbitrage-specific settings for cross-exchange trading."""
    model_config = ConfigDict(extra="ignore")

    MIN_SPREAD_BPS: float = Field(
        default=5.0,
        ge=0.1,
        le=1000.0,
        description="Minimum spread in basis points to execute arbitrage"
    )
    MAX_POSITION_PER_EXCHANGE_PCT: float = Field(
        default=0.25,
        ge=0.01,
        le=0.50,
        description="Max position size per exchange as fraction of total"
    )
    TRIANGULAR_ARBITRAGE_ENABLED: bool = Field(
        default=False,
        description="Enable triangular arbitrage detection"
    )
    MAX_TRIANGULAR_HOPS: int = Field(
        default=3,
        ge=2,
        le=5,
        description="Maximum hops in triangular arbitrage"
    )
    ARBITRAGE_TIMEOUT_MS: int = Field(
        default=500,
        ge=10,
        le=10000,
        description="Max execution time for arbitrage in milliseconds"
    )
    MIN_TRADE_SIZE_USD: float = Field(
        default=100.0,
        ge=10.0,
        description="Minimum USD trade size for arbitrage"
    )


class ExchangeMapping(BaseModel):
    """Symbol mapping configuration across exchanges."""
    model_config = ConfigDict(extra="ignore")

    BASE_SYMBOL: str = Field(
        default="",
        description="Base trading symbol (e.g., BTC, AAPL)"
    )
    EXCHANGE_SYMBOLS: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of exchange names to their symbol format"
    )
    PRICE_PRECISION: int = Field(
        default=2,
        ge=0,
        le=8,
        description="Price precision for this symbol"
    )
    QUANTITY_PRECISION: int = Field(
        default=6,
        ge=0,
        le=8,
        description="Quantity precision for this symbol"
    )

    @field_validator("EXCHANGE_SYMBOLS")
    @classmethod
    def validate_exchange_symbols(cls, v: Dict[str, str]) -> Dict[str, str]:
        if v and not all(isinstance(k, str) and isinstance(vv, str) for k, vv in v.items()):
            raise ValueError("Exchange symbols must be string key-value pairs")
        return v


class MultiExchangeRiskLimits(BaseModel):
    """Risk limits specific to multi-exchange trading."""
    model_config = ConfigDict(extra="ignore")

    MAX_TOTAL_EXPOSURE_PCT: float = Field(
        default=1.0,
        ge=0.1,
        le=2.0,
        description="Max total portfolio exposure across all exchanges"
    )
    MAX_CORRELATION_RISK: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Max correlation threshold for position diversification"
    )
    EXCHANGE_FAILURE_BUFFER_PCT: float = Field(
        default=0.10,
        ge=0.0,
        le=0.50,
        description="Buffer percentage to maintain during exchange outages"
    )
    CROSS_EXCHANGE_FEE_BUFFER_BPS: float = Field(
        default=10.0,
        ge=0.0,
        le=100.0,
        description="Fee buffer in bps for cross-exchange transactions"
    )


class MultiExchangeConfig(BaseModel):
    """Multi-exchange trading configuration with arbitrage and risk settings."""
    model_config = ConfigDict(extra="ignore")

    ENABLED: bool = Field(
        default=False,
        description="Enable multi-exchange trading"
    )
    EXCHANGES: List[str] = Field(
        default_factory=lambda: ["primary"],
        description="List of enabled exchanges"
    )
    PRIMARY_EXCHANGE: str = Field(
        default="alpaca",
        description="Primary exchange for fallback"
    )
    arbitrage: ArbitrageConfig = Field(default_factory=ArbitrageConfig)
    risk_limits: MultiExchangeRiskLimits = Field(default_factory=MultiExchangeRiskLimits)
    symbol_mappings: List[ExchangeMapping] = Field(default_factory=list)

    @field_validator("EXCHANGES")
    @classmethod
    def validate_exchanges(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one exchange must be specified")
        return v


class APIConfig(BaseModel):
    """API server configuration (if bot exposes HTTP API)."""
    model_config = ConfigDict(extra="ignore")

    API_HOST: str = Field(default="0.0.0.0", description="API bind host")
    API_PORT: int = Field(default=8000, ge=1024, le=65535, description="API port")
    API_ENABLED: bool = Field(default=False, description="Enable API server")
    CORS_ORIGINS: List[str] = Field(default_factory=list, description="Allowed CORS origins")


# ─────────────────────────────────────────────────────────────────────────────
# Event Bus Config (new in Phase 1)
# ─────────────────────────────────────────────────────────────────────────────

class EventBusConfig(BaseModel):
    """Event-driven architecture settings."""
    model_config = ConfigDict(extra="ignore")

    MESSAGE_BUS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    EVENT_STREAM_MAX_LEN: int = Field(
        default=10000,
        ge=100,
        le=1000000,
        description="Max stream length (XTRIM)"
    )
    CONSUMER_GROUP: str = Field(
        default="quantumtrade",
        description="Redis consumer group prefix"
    )
    EVENT_RETENTION_MS: int = Field(
        default=604800000,  # 7 days in ms
        ge=60000,
        description="Stream retention (ms)"
    )
    DEAD_LETTER_QUEUE_ENABLED: bool = Field(
        default=True,
        description="Enable DLQ for failed events"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Master Settings
# ─────────────────────────────────────────────────────────────────────────────

class QuantumTradeSettings(BaseSettings):
    """Complete application settings with validation.

    Load priority (highest to lowest):
      1. Environment variables
      2. YAML config file (CONFIG_YAML_PATH)
      3. .env file
      4. Default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="QT_",  # QuantumTrade prefix for env vars
    )

    # ── Core Sub-configs ──
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    mlops: MLOpsConfig = Field(default_factory=MLOpsConfig)
    backtest_simulation: BacktestSimulationConfig = Field(default_factory=BacktestSimulationConfig)
    multi_exchange: MultiExchangeConfig = Field(default_factory=MultiExchangeConfig)

    # ── Additional ──
    CONFIG_YAML_PATH: str = Field(
        default="config/quantumtrade.yaml",
        description="Path to YAML config file"
    )
    SYMBOLS: List[str] = Field(
        default_factory=lambda: ["AAPL", "GOOG", "MSFT"],
        description="Trading symbols list"
    )
    TRADING_INTERVAL_SECONDS: int = Field(
        default=300,
        ge=10,
        description="Seconds between trading ticks"
    )
    RESPECT_MARKET_HOURS: bool = Field(
        default=True,
        description="Only trade during market hours (stocks)"
    )
    DATA_DIR: str = Field(default="data", description="Data storage directory")
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment"
    )

    # ── Computed ──
    @property
    def message_bus_url(self) -> str:
        """Get effective Redis URL."""
        return self.redis.redis_url

    @property
    def postgres_url(self) -> str:
        """Get effective PostgreSQL URL."""
        return self.database.database_url

    # ── YAML loading ──
    def load_yaml_config(self, path: Optional[str] = None) -> None:
        """Load configuration from YAML file.

        Overlays YAML values over existing settings (env vars take precedence).

        Args:
            path: Path to YAML file (default: CONFIG_YAML_PATH)
        """
        import yaml
        from pathlib import Path
        import logging

        config_path = Path(path or self.CONFIG_YAML_PATH)
        logger = logging.getLogger(__name__)
        if not config_path.exists():
            logger.warning(f"YAML config not found: {config_path}")
            return

        with open(config_path) as f:
            yaml_data = yaml.safe_load(f) or {}

        # Update nested configs
        for section, model in [
            ("database", self.database),
            ("redis", self.redis),
            ("broker", self.broker),
            ("strategy", self.strategy),
            ("risk", self.risk),
            ("notifications", self.notifications),
            ("logging", self.logging),
            ("api", self.api),
            ("event_bus", self.event_bus),
            ("mlops", self.mlops),
            ("backtest_simulation", self.backtest_simulation),
            ("multi_exchange", self.multi_exchange),
            # Backwards-compatible aliases
            ("ml", self.mlops),   # 'ml' section maps to mlops
            ("mlflow", self.mlops.mlflow),  # 'mlflow' section
            ("simulation", self.backtest_simulation),  # 'simulation' section
        ]:
            if section in yaml_data:
                section_data = yaml_data[section]
                if isinstance(section_data, dict):
                    # First handle nested config objects
                    for key, value in section_data.items():
                        # Check if this is a nested BaseModel field
                        if hasattr(model, key):
                            field_value = getattr(model, key)
                            if isinstance(field_value, BaseModel) and isinstance(value, dict):
                                self._update_nested_model(field_value, value)
                            elif isinstance(field_value, list) and isinstance(value, list):
                                # Handle List[BaseModel]
                                self._update_nested_model(model, {key: value})
                            else:
                                setattr(model, key, value)

        # Update top-level fields
        for key in ["SYMBOLS", "TRADING_INTERVAL_SECONDS", "RESPECT_MARKET_HOURS",
                    "DATA_DIR", "ENVIRONMENT"]:
            if key in yaml_data:
                setattr(self, key, yaml_data[key])

        logger.info(f"Loaded YAML config from {config_path}")

    def _update_nested_model(self, model: BaseModel, data: dict) -> None:
        """Recursively update a nested model from dict data."""
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if hasattr(model, key):
                field_value = getattr(model, key)
                if isinstance(field_value, BaseModel) and isinstance(value, dict):
                    self._update_nested_model(field_value, value)
                elif isinstance(field_value, list):
                    # Check if the pydantic field annotation indicates a list of BaseModel
                    field_info = model.model_fields.get(key)
                    if field_info and hasattr(field_info, 'annotation'):
                        annotation = field_info.annotation
                        origin = getattr(annotation, '__origin__', None)
                        if origin is list:
                            args = getattr(annotation, '__args__', ())
                            if args and issubclass(args[0], BaseModel):
                                model_type = args[0]
                                if isinstance(value, list):
                                    new_list = [model_type(**item) if isinstance(item, dict) else item for item in value]
                                    setattr(model, key, new_list)
                                    continue
                    setattr(model, key, value)
                else:
                    setattr(model, key, value)


# Create singleton instance
settings = QuantumTradeSettings()
