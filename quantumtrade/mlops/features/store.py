"""Feature store for online and offline feature management."""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
import pickle
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class FeatureDefinition:
    """Definition of a feature in the feature store."""
    name: str
    description: str
    dtype: str = "float"
    computation_logic: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "dtype": self.dtype,
            "computation_logic": self.computation_logic,
            "dependencies": self.dependencies,
            "version": self.version,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class FeatureValues:
    """Container for feature values with metadata."""
    symbol: str
    timestamp: datetime
    features: Dict[str, float]
    computed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "features": self.features,
            "computed_at": self.computed_at.isoformat(),
        }


class FeatureBackend(ABC):
    """Abstract backend for feature storage."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Dict[str, float]]:
        pass
    
    @abstractmethod
    def set(self, key: str, features: Dict[str, float], ttl: int = 3600):
        pass
    
    @abstractmethod
    def delete(self, key: str):
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def flush(self):
        pass


class RedisFeatureBackend(FeatureBackend):
    """Redis-backed feature store."""
    
    def __init__(self, redis_client, prefix: str = "features:"):
        """
        Initialize Redis backend.
        
        Args:
            redis_client: Redis client instance
            prefix: Key prefix
        """
        self.redis = redis_client
        self.prefix = prefix
    
    def _make_key(self, symbol: str, timestamp: datetime) -> str:
        """Create Redis key."""
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"{self.prefix}{symbol}:{ts_str}"
    
    def get(self, key: str) -> Optional[Dict[str, float]]:
        """Get features from Redis."""
        try:
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis get failed: {e}")
        return None
    
    def set(self, key: str, features: Dict[str, float], ttl: int = 3600):
        """Set features in Redis."""
        try:
            self.redis.setex(key, ttl, json.dumps(features))
        except Exception as e:
            logger.error(f"Redis set failed: {e}")
    
    def delete(self, key: str):
        """Delete features."""
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis delete failed: {e}")
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            return bool(self.redis.exists(key))
        except Exception:
            return False
    
    def flush(self):
        """Flush all feature keys."""
        try:
            keys = self.redis.keys(f"{self.prefix}*")
            if keys:
                self.redis.delete(*keys)
        except Exception as e:
            logger.error(f"Redis flush failed: {e}")


class PostgresFeatureBackend(FeatureBackend):
    """PostgreSQL-backed feature store for offline training."""
    
    def __init__(self, connection_string: str, table_name: str = "feature_store"):
        """
        Initialize PostgreSQL backend.
        
        Args:
            connection_string: SQLAlchemy connection string
            table_name: Feature table name
        """
        self.connection_string = connection_string
        self.table_name = table_name
        self._engine = None
    
    @property
    def engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(self.connection_string)
        return self._engine
    
    def get(self, key: str) -> Optional[Dict[str, float]]:
        """Not implemented for SQL backend (batch queries preferred)."""
        raise NotImplementedError("Use batch query for PostgreSQL backend")
    
    def set(self, key: str, features: Dict[str, float], ttl: int = 3600):
        """Not implemented for SQL backend."""
        raise NotImplementedError("Use batch insert for PostgreSQL backend")
    
    def delete(self, key: str):
        """Not implemented."""
        pass
    
    def exists(self, key: str) -> bool:
        """Not implemented."""
        return False
    
    def flush(self):
        """Not implemented."""
        pass
    
    def batch_query(
        self,
        symbols: List[str],
        start_time: datetime,
        end_time: datetime,
        features: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Batch query features for training.
        
        Returns DataFrame with symbol, timestamp, feature columns.
        """
        # Placeholder - implement actual SQL query
        raise NotImplementedError("Batch query not implemented")
    
    def batch_insert(self, df: pd.DataFrame):
        """Batch insert feature rows."""
        # Placeholder
        raise NotImplementedError("Batch insert not implemented")


class FeatureStore:
    """
    Centralized feature management for training and inference.
    
    Features:
    - Feature definition registry
    - Online retrieval (Redis) for real-time inference
    - Offline storage (PostgreSQL/Parquet) for training
    - Feature computation consistency
    - Feature monitoring (missing rates, distributions)
    """
    
    def __init__(
        self,
        backend: FeatureBackend,
        feature_definitions: Optional[List[FeatureDefinition]] = None,
        ttl_seconds: int = 3600,
    ):
        """
        Initialize feature store.
        
        Args:
            backend: Storage backend (Redis, PostgreSQL, etc.)
            feature_definitions: List of registered features
            ttl_seconds: Default cache TTL
        """
        self.backend = backend
        self.ttl_seconds = ttl_seconds
        self.feature_registry: Dict[str, FeatureDefinition] = {}
        
        # Register default features
        if feature_definitions:
            for fd in feature_definitions:
                self.register_feature(fd)
        
        logger.info(f"FeatureStore initialized with {type(backend).__name__} backend")
    
    def register_feature(self, definition: FeatureDefinition):
        """Register a new feature definition."""
        self.feature_registry[definition.name] = definition
        logger.info(f"Registered feature: {definition.name}")
    
    def get_feature_def(self, name: str) -> Optional[FeatureDefinition]:
        """Get feature definition."""
        return self.feature_registry.get(name)
    
    def list_features(self) -> List[FeatureDefinition]:
        """List all registered features."""
        return list(self.feature_registry.values())
    
    def compute_features(
        self,
        df: pd.DataFrame,
        feature_names: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Compute features for a DataFrame.
        
        Args:
            df: OHLCV DataFrame
            feature_names: Features to compute (None = all registered)
            
        Returns:
            DataFrame with computed feature columns
        """
        df = df.copy()
        
        if feature_names is None:
            feature_names = list(self.feature_registry.keys())
        
        for name in feature_names:
            fdef = self.feature_registry.get(name)
            if fdef:
                df = self._compute_feature(df, fdef)
        
        return df
    
    def _compute_feature(
        self,
        df: pd.DataFrame,
        fdef: FeatureDefinition,
    ) -> pd.DataFrame:
        """Compute single feature based on definition."""
        # Built-in feature computations
        if fdef.name == "rsi":
            df[fdef.name] = self._compute_rsi(df['Close'])
        elif fdef.name == "macd":
            ema12 = df['Close'].ewm(span=12).mean()
            ema26 = df['Close'].ewm(span=26).mean()
            df[fdef.name] = ema12 - ema26
        elif fdef.name == "sma_20":
            df[fdef.name] = df['Close'].rolling(20).mean()
        elif fdef.name == "volatility":
            df[fdef.name] = df['Close'].pct_change().rolling(20).std()
        elif fdef.name == "returns":
            df[fdef.name] = df['Close'].pct_change()
        else:
            # Custom feature via computation_logic
            if fdef.computation_logic:
                # Evaluate expression (careful with eval!)
                # In production, use safer expression parser
                try:
                    df[fdef.name] = eval(fdef.computation_logic, {"df": df})
                except Exception as e:
                    logger.error(f"Failed to compute feature {fdef.name}: {e}")
        
        return df
    
    def _compute_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def cache_features(
        self,
        symbol: str,
        timestamp: datetime,
        features: Dict[str, float],
        ttl: Optional[int] = None,
    ):
        """Cache features for online serving."""
        key = f"features:{symbol}:{timestamp.strftime('%Y%m%d_%H%M%S')}"
        self.backend.set(key, features, ttl=ttl or self.ttl_seconds)
    
    def get_cached_features(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> Optional[Dict[str, float]]:
        """Retrieve cached features."""
        key = f"features:{symbol}:{timestamp.strftime('%Y%m%d_%H%M%S')}"
        return self.backend.get(key)
    
    def get_online_features(
        self,
        symbol: str,
        features: List[str],
        current_time: Optional[datetime] = None,
    ) -> FeatureValues:
        """
        Get real-time features for prediction.
        
        For online serving, this would:
        1. Fetch latest market data
        2. Compute features
        3. Cache for reuse
        4. Return feature vector
        """
        current_time = current_time or datetime.utcnow()
        
        # Try cache first
        cached = self.get_cached_features(symbol, current_time)
        if cached:
            return FeatureValues(symbol, current_time, cached)
        
        # Compute fresh features (integrate with data feed)
        # Placeholder - fetch data and compute
        features_dict = {f: 0.0 for f in features}
        
        # Cache for future
        self.cache_features(symbol, current_time, features_dict)
        
        return FeatureValues(symbol, current_time, features_dict)
    
    def batch_compute_offline(
        self,
        df: pd.DataFrame,
        symbol_col: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compute all features for offline training dataset.
        
        Args:
            df: OHLCV data
            symbol_col: Optional symbol column for multi-symbol data
            
        Returns:
            DataFrame with all feature columns
        """
        logger.info(f"Computing offline features for {len(df)} rows")
        
        # Compute all registered features
        df_features = self.compute_features(df)
        
        # Drop rows with NaN
        df_features = df_features.dropna()
        
        logger.info(f"Feature computation complete: {df_features.shape[1]} columns")
        return df_features
    
    def get_feature_importance(
        self,
        model,
        feature_names: List[str],
    ) -> Dict[str, float]:
        """
        Get feature importance from trained model.
        
        Args:
            model: Trained ML model with feature_importances_
            feature_names: List of feature names (ordered)
            
        Returns:
            Dict mapping feature name to importance score
        """
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            return dict(zip(feature_names, importances))
        return {}
    
    def monitor_feature_quality(
        self,
        features: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Monitor feature quality metrics.
        
        Returns:
            Dict with missing rates, distributions, etc.
        """
        report = {
            "total_features": len(features.columns),
            "total_rows": len(features),
            "missing_rates": {},
            "zero_variance": [],
            "correlations": {},
        }
        
        for col in features.columns:
            missing_pct = features[col].isna().mean()
            report["missing_rates"][col] = missing_pct
            
            # Check zero variance
            if features[col].std() == 0:
                report["zero_variance"].append(col)
        
        return report
