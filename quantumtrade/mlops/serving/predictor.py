"""Unified prediction API with caching and version management."""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PredictionRequest:
    """Request for model prediction."""
    features: Dict[str, float]
    model_name: str = "default"
    version: Optional[str] = None  # None = latest production


@dataclass
class BatchPredictionRequest:
    """Request for batch predictions."""
    features_list: List[Dict[str, float]]
    model_name: str = "default"
    version: Optional[str] = None


@dataclass
class PredictionResponse:
    """Prediction result."""
    prediction: int
    confidence: float
    model_version: str
    timestamp: datetime
    latency_ms: float


class Predictor:
    """
    Unified prediction API for QuantumTrade models.
    
    Features:
    - Loads models from MLflow registry
    - Smart caching (in-memory + optional Redis)
    - Low-latency inference (<10ms)
    - Version routing
    - A/B testing support (future)
    """
    
    def __init__(
        self,
        registry,
        cache_ttl: int = 60,
        cache_size: int = 10,
    ):
        """
        Initialize predictor.
        
        Args:
            registry: ModelRegistry instance
            cache_ttl: Cache TTL in seconds (0 = disabled)
            cache_size: Number of models to cache in memory
        """
        self.registry = registry
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        
        # Model cache
        self._model_cache: Dict[str, Tuple[Any, str]] = {}  # key -> (model, version)
        self._prediction_cache: Dict[str, Tuple[float, datetime]] = {}  # key -> (prediction, timestamp)
        
        # Metrics
        self.predictions_total = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.errors = 0
        
        logger.info("Predictor initialized")
    
    def _features_to_key(self, features: Dict[str, float], version: Optional[str]) -> str:
        """Create cache key from features."""
        feature_str = json.dumps(features, sort_keys=True)
        version_str = version or "latest"
        combined = f"{feature_str}:{version_str}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _load_model(self, model_name: str, version: Optional[str] = None) -> Tuple[Any, str]:
        """Load model from registry (with caching)."""
        cache_key = f"{model_name}:{version or 'latest'}"
        
        # Check in-memory cache
        if cache_key in self._model_cache:
            logger.debug(f"Cache hit for model {cache_key}")
            return self._model_cache[cache_key]
        
        # Get model version
        if version is None:
            model_version = self.registry.get_latest_model(model_name, stage="Production")
            if model_version is None:
                raise ValueError(f"No production model found for {model_name}")
            version = model_version.version
        else:
            model_version = self.registry.get_model_version(model_name, version)
        
        # Load model
        try:
            model = self.registry.load_model(model_name, stage=None)  # Load specific version
            # Note: load_model needs to support specific version
            # For now, use MLflow directly
            import mlflow
            model_uri = f"models:/{model_name}/{version}"
            model = mlflow.pyfunc.load_model(model_uri)
        except Exception as e:
            logger.error(f"Failed to load model {model_name} v{version}: {e}")
            raise
        
        # Cache model (LRU eviction if needed)
        if len(self._model_cache) >= self.cache_size:
            # Remove oldest entry
            oldest = next(iter(self._model_cache))
            del self._model_cache[oldest]
        
        self._model_cache[cache_key] = (model, version)
        logger.info(f"Loaded model {model_name} version {version}")
        
        return model, version
    
    async def predict(
        self,
        model_name: str,
        features: Dict[str, float],
        version: Optional[str] = None,
    ) -> PredictionResponse:
        """
        Make prediction.
        
        Args:
            model_name: Model identifier
            features: Feature dict
            version: Specific version (None = latest production)
            
        Returns:
            PredictionResponse
        """
        start_time = datetime.utcnow()
        
        # Check prediction cache
        pred_key = self._features_to_key(features, version)
        if self.cache_ttl > 0:
            cached = self._prediction_cache.get(pred_key)
            if cached:
                prediction, confidence, timestamp = cached
                if (datetime.utcnow() - timestamp).total_seconds() < self.cache_ttl:
                    self.cache_hits += 1
                    latency = (datetime.utcnow() - start_time).total_seconds() * 1000
                    return PredictionResponse(
                        prediction=prediction,
                        confidence=confidence,
                        model_version=version or "latest",
                        timestamp=timestamp,
                        latency_ms=latency,
                    )
            self.cache_misses += 1
        
        try:
            # Load model
            model, resolved_version = self._load_model(model_name, version)
            
            # Prepare feature vector (ensure correct order)
            # For sklearn model, need to pass as array
            # Assuming model has feature_names_in_ if fitted
            feature_names = list(features.keys())
            feature_vector = np.array([features[name] for name in feature_names]).reshape(1, -1)
            
            # Make prediction
            pred = model.predict(feature_vector)[0]
            proba = model.predict_proba(feature_vector)[0]
            
            # Get confidence (max probability)
            confidence = float(max(proba))
            prediction = int(pred)
            
            # Cache prediction
            if self.cache_ttl > 0:
                self._prediction_cache[pred_key] = (prediction, confidence, datetime.utcnow())
            
            self.predictions_total += 1
            
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            logger.debug(
                f"Prediction: {prediction} (conf={confidence:.3f}) "
                f"in {latency:.2f}ms"
            )
            
            return PredictionResponse(
                prediction=prediction,
                confidence=confidence,
                model_version=resolved_version,
                timestamp=datetime.utcnow(),
                latency_ms=latency,
            )
            
        except Exception as e:
            self.errors += 1
            logger.error(f"Prediction error: {e}")
            raise
    
    def predict_batch(
        self,
        model_name: str,
        features_list: List[Dict[str, float]],
        version: Optional[str] = None,
    ) -> List[PredictionResponse]:
        """Batch prediction."""
        results = []
        for features in features_list:
            result = self.predict(model_name, features, version)
            results.append(result)
        return results
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get predictor metrics."""
        total_requests = self.predictions_total + self.cache_hits + self.cache_misses
        cache_hit_rate = (
            self.cache_hits / (self.cache_hits + self.cache_misses)
            if (self.cache_hits + self.cache_misses) > 0 else 0
        )
        
        return {
            "predictions_total": self.predictions_total,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": cache_hit_rate,
            "errors": self.errors,
            "model_cache_size": len(self._model_cache),
            "prediction_cache_size": len(self._prediction_cache),
        }
    
    def clear_cache(self):
        """Clear all caches."""
        self._model_cache.clear()
        self._prediction_cache.clear()
        logger.info("Caches cleared")
    
    def warm_cache(
        self,
        model_name: str,
        sample_features: Optional[Dict[str, float]] = None,
    ):
        """Pre-load model into cache."""
        try:
            self._load_model(model_name)
            logger.info(f"Cache warmed for {model_name}")
        except Exception as e:
            logger.error(f"Cache warm failed: {e}")
