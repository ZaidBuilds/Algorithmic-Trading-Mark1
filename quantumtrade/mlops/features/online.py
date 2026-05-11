"""Online feature retrieval for real-time inference."""

from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OnlineFeatureStore:
    """
    Online feature store optimized for low-latency inference.
    
    Features:
    - Pre-computed feature caching
    - Low-latency retrieval (<5ms)
    - TTL-based expiration
    
    This is a simplified version; in production, integrate with:
    - Feast
    - Tecton
    - Custom Redis implementation
    """
    
    def __init__(self, redis_client, ttl_seconds: int = 3600):
        """
        Initialize online feature store.
        
        Args:
            redis_client: Redis client
            ttl_seconds: Feature cache TTL
        """
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        self.prefix = "online_features:"
        logger.info("OnlineFeatureStore initialized")
    
    def _make_key(self, symbol: str, feature_set: str = "default") -> str:
        """Create cache key."""
        return f"{self.prefix}{symbol}:{feature_set}"
    
    def get_features(
        self,
        symbol: str,
        feature_set: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """
        Get online features for symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'AAPL')
            feature_set: Feature set name
            
        Returns:
            Dict of feature_name -> value
        """
        key = self._make_key(symbol, feature_set)
        try:
            data = self.redis.get(key)
            if data:
                import json
                return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get features: {e}")
        return None
    
    def set_features(
        self,
        symbol: str,
        features: Dict[str, Any],
        feature_set: str = "default",
        ttl: Optional[int] = None,
    ):
        """Cache features for symbol."""
        key = self._make_key(symbol, feature_set)
        try:
            import json
            self.redis.setex(
                key, 
                ttl or self.ttl_seconds, 
                json.dumps(features)
            )
        except Exception as e:
            logger.error(f"Failed to set features: {e}")
    
    def delete_features(self, symbol: str, feature_set: str = "default"):
        """Remove cached features."""
        key = self._make_key(symbol, feature_set)
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete features: {e}")


class RedisFeatureBackend:
    """Redis feature backend implementation."""
    
    def __init__(self, redis_client, prefix: str = "features:"):
        self.redis = redis_client
        self.prefix = prefix
    
    def get(self, key: str) -> Optional[Dict[str, float]]:
        try:
            import json
            data = self.redis.get(self.prefix + key)
            return json.loads(data) if data else None
        except Exception:
            return None
    
    def set(self, key: str, features: Dict[str, float], ttl: int = 3600):
        try:
            import json
            self.redis.setex(self.prefix + key, ttl, json.dumps(features))
        except Exception:
            pass
    
    def delete(self, key: str):
        try:
            self.redis.delete(self.prefix + key)
        except Exception:
            pass
    
    def exists(self, key: str) -> bool:
        try:
            return bool(self.redis.exists(self.prefix + key))
        except Exception:
            return False
    
    def flush(self):
        try:
            keys = self.redis.keys(f"{self.prefix}*")
            if keys:
                self.redis.delete(*keys)
        except Exception:
            pass


class FeatureRegistry:
    """
    Registry of all available features.
    
    Tracks:
    - Feature definitions
    - Versioning
    - Dependencies
    - Documentation
    """
    
    def __init__(self):
        self._features: Dict[str, Any] = {}
    
    def register(self, feature_def: Any):
        """Register feature definition."""
        self._features[feature_def.name] = feature_def
    
    def get(self, name: str) -> Optional[Any]:
        """Get feature definition."""
        return self._features.get(name)
    
    def list_features(self) -> List[str]:
        """List all feature names."""
        return list(self._features.keys())
    
    def get_dependencies(self, feature_name: str) -> List[str]:
        """Get feature dependencies."""
        fdef = self._features.get(feature_name)
        return fdef.dependencies if fdef else []
