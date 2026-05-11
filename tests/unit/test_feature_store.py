"""Tests for feature store."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from quantumtrade.mlops.features.store import FeatureStore, FeatureDefinition, FeatureValues
from quantumtrade.mlops.features.online import OnlineFeatureStore, RedisFeatureBackend
from quantumtrade.mlops.features.registry import FeatureRegistry


class TestFeatureDefinition:
    """Test feature definition dataclass."""
    
    def test_feature_definition_creation(self):
        """Test creating feature definition."""
        fd = FeatureDefinition(
            name="rsi",
            description="Relative Strength Index",
            dtype="float",
            computation_logic="self._compute_rsi(prices)",
            dependencies=["close"],
            tags=["technical", "momentum"],
        )
        assert fd.name == "rsi"
        assert fd.dtype == "float"
        assert "technical" in fd.tags
    
    def test_feature_definition_to_dict(self):
        """Test serialization."""
        fd = FeatureDefinition(name="test", description="test feature")
        d = fd.to_dict()
        assert d["name"] == "test"
        assert "created_at" in d


class TestFeatureRegistry:
    """Test feature registry."""
    
    def test_registry_register(self):
        """Test registering features."""
        registry = FeatureRegistry()
        fd = FeatureDefinition(name="rsi", description="RSI")
        registry.register(fd)
        assert registry.get("rsi") is not None
        assert "rsi" in [f.name for f in registry.list()]
    
    def test_registry_dependencies(self):
        """Test dependency tracking."""
        registry = FeatureRegistry()
        registry.register(FeatureDefinition(name="sma", description="SMA", dependencies=["close"]))
        registry.register(FeatureDefinition(name="rsi", description="RSI", dependencies=["close", "sma"]))
        
        deps = registry.get_dependencies("rsi")
        assert "sma" in deps or "close" in deps
    
    def test_topological_sort(self):
        """Test topological sorting of features."""
        registry = FeatureRegistry()
        # A depends on B, B depends on C
        registry.register(FeatureDefinition(name="c", description="base"))
        registry.register(FeatureDefinition(name="b", description="SMA", dependencies=["c"]))
        registry.register(FeatureDefinition(name="a", description="RSI", dependencies=["b"]))
        
        ordered = registry.topological_sort()
        names = [f.name for f in ordered]
        # c should come before b, b before a
        assert names.index("c") < names.index("b")
        assert names.index("b") < names.index("a")


class TestFeatureStore:
    """Test feature store."""
    
    @pytest.fixture
    def feature_store(self):
        """Create feature store with mock backend."""
        backend = Mock()
        backend.get.return_value = None
        backend.set.return_value = None
        
        store = FeatureStore(backend=backend, ttl_seconds=3600)
        
        # Register some features
        store.register_feature(FeatureDefinition(name="rsi", description="RSI"))
        store.register_feature(FeatureDefinition(name="sma_20", description="SMA 20"))
        
        return store
    
    def test_feature_store_init(self, feature_store):
        """Test initialization."""
        assert feature_store is not None
        assert len(feature_store.list_features()) == 2
    
    def test_register_feature(self, feature_store):
        """Test feature registration."""
        feature_store.register_feature(FeatureDefinition(name="macd", description="MACD"))
        assert len(feature_store.list_features()) == 3
        assert feature_store.get_feature_def("macd") is not None
    
    def test_compute_features(self, feature_store):
        """Test feature computation."""
        df = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104],
            'High': [102, 103, 104, 105, 106],
            'Low': [98, 99, 100, 101, 102],
            'Close': [101, 102, 103, 104, 105],
            'Volume': [1000, 1100, 1200, 1300, 1400],
        })
        
        # Should not raise
        result = feature_store.compute_features(df, feature_names=["rsi", "sma_20"])
        assert isinstance(result, pd.DataFrame)
    
    def test_get_online_features(self, feature_store):
        """Test online feature retrieval."""
        feature_store.backend.get.return_value = {"rsi": 65.5, "sma_20": 102.3}
        
        features = feature_store.get_online_features("AAPL", ["rsi", "sma_20"])
        
        assert features is not None
        assert "rsi" in features.features
    
    def test_cache_features(self, feature_store):
        """Test feature caching."""
        feature_store.cache_features(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            features={"rsi": 70.0, "sma_20": 105.0},
        )
        
        # Verify backend.set called
        feature_store.backend.set.assert_called()
    
    def test_monitor_feature_quality(self, feature_store):
        """Test feature quality monitoring."""
        df = pd.DataFrame({
            "f1": [1, 2, 3, 4, 5],
            "f2": [1.0, 2.0, np.nan, 4.0, 5.0],
            "f3": [1, 1, 1, 1, 1],  # zero variance
        })
        
        report = feature_store.monitor_feature_quality(df)
        
        assert "missing_rates" in report
        assert "zero_variance" in report
        assert "f3" in report["zero_variance"]
        assert report["missing_rates"]["f2"] > 0


class TestOnlineFeatureStore:
    """Test online feature store."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = Mock()
        redis.get.return_value = None
        redis.setex.return_value = True
        redis.exists.return_value = False
        return redis
    
    @pytest.fixture
    def online_store(self, mock_redis):
        """Create online store with mock Redis."""
        return OnlineFeatureStore(mock_redis, ttl_seconds=60)
    
    def test_online_store_init(self, online_store):
        """Test initialization."""
        assert online_store.redis is not None
        assert online_store.ttl_seconds == 60
    
    def test_get_features_miss(self, online_store):
        """Test cache miss."""
        online_store.redis.get.return_value = None
        features = online_store.get_features("AAPL")
        assert features is None
    
    def test_get_features_hit(self, online_store):
        """Test cache hit."""
        online_store.redis.get.return_value = '{"rsi": 65.5}'
        features = online_store.get_features("AAPL")
        assert features == {"rsi": 65.5}
    
    def test_set_features(self, online_store):
        """Test setting features."""
        online_store.set_features("AAPL", {"rsi": 70.0})
        online_store.redis.setex.assert_called_once()
    
    def test_delete_features(self, online_store):
        """Test deleting features."""
        online_store.delete_features("AAPL")
        online_store.redis.delete.assert_called_once()


class TestFeatureValues:
    """Test FeatureValues container."""
    
    def test_creation(self):
        """Test creating feature values."""
        fv = FeatureValues(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            features={"rsi": 65.0, "sma": 100.0},
        )
        assert fv.symbol == "AAPL"
        assert len(fv.features) == 2
    
    def test_to_dict(self):
        """Test serialization."""
        fv = FeatureValues(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1),
            features={"f1": 1.0},
        )
        d = fv.to_dict()
        assert "symbol" in d
        assert "timestamp" in d
        assert "features" in d
