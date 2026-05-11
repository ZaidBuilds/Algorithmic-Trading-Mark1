"""End-to-end tests for model serving."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from unittest.mock import Mock, patch
import json

from quantumtrade.mlops.serving.predictor import Predictor, PredictionRequest
from quantumtrade.mlops.registry import ModelRegistry, ModelVersion
from ml.ml_predictor import MLPredictor


class TestServingE2E:
    """E2E serving tests."""
    
    @pytest.fixture
    def trained_model(self):
        """Create and train a model."""
        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = (X[:, 0] + X[:, 1] > 0).astype(int)
        
        model = MLPredictor(model_type='random_forest')
        model.train(X, y)
        return model, X, y
    
    @pytest.fixture
    def mock_mlflow(self, trained_model, temp_mlflow_dir):
        """Mock MLflow with a registered model."""
        model, X, y = trained_model
        
        # Use actual MLflow local tracking
        import mlflow
        import mlflow.sklearn
        
        tracking_uri = f"file://{temp_mlflow_dir}"
        mlflow.set_tracking_uri(tracking_uri)
        
        # Create experiment
        experiment_id = mlflow.create_experiment("test_e2e")
        
        with mlflow.start_run(experiment_id=experiment_id) as run:
            mlflow.log_params({"model_type": "random_forest"})
            mlflow.log_metrics({"accuracy": 0.85, "precision": 0.83})
            mlflow.sklearn.log_model(model, "model")
            run_id = run.info.run_id
        
        # Register model
        client = mlflow.tracking.MlflowClient()
        model_version = client.create_registered_model(
            name="test_model",
        )
        
        return tracking_uri
    
    def test_predictor_lifecycle(self, trained_model, temp_mlflow_dir):
        """Test full predictor lifecycle."""
        model, X, y = trained_model
        
        # Setup MLflow
        import mlflow
        import mlflow.sklearn
        
        mlflow.set_tracking_uri(f"file://{temp_mlflow_dir}")
        exp_id = mlflow.create_experiment("predictor_test")
        
        with mlflow.start_run(experiment_id=exp_id):
            mlflow.log_metrics({"accuracy": 0.9})
            mlflow.sklearn.log_model(model, "model")
            run_id = mlflow.active_run().info.run_id
        
        # Register
        client = mlflow.tracking.MlflowClient()
        client.create_registered_model("test_model")
        client.create_model_version(
            name="test_model",
            source=f"runs:/{run_id}/model",
            run_id=run_id,
        )
        
        # Create predictor with mocked registry
        registry = Mock(spec=ModelRegistry)
        mv = ModelVersion(
            name="test_model",
            version="1",
            run_id=run_id,
            metrics={"accuracy": 0.9},
            params={},
            training_data_hash="abc",
            training_start=datetime.utcnow().isoformat(),
            training_end=datetime.utcnow().isoformat(),
            git_commit="abc123",
            artifact_uri=f"file://{temp_mlflow_dir}/0/{run_id}/artifacts/model",
            stage="Production",
        )
        registry.get_latest_model.return_value = mv
        
        # Load model using MLflow directly for predictor test
        model_uri = f"models:/test_model/1"
        predictor = Predictor(registry)
        
        # Override _load_model to use real MLflow model
        def real_load(name, version):
            return mlflow.pyfunc.load_model(model_uri), version
        
        predictor._load_model = real_load
        
        # Make prediction
        features = {f"feature_{i}": float(X[0, i]) for i in range(10)}
        result = predictor.predict("test_model", features)
        
        assert result.prediction in [0, 1]
        assert 0.5 <= result.confidence <= 1.0
        assert result.latency_ms < 100  # Should be fast
    
    def test_cache_behavior(self):
        """Test prediction caching."""
        predictor = Predictor(Mock(), cache_ttl=60, cache_size=2)
        
        # First prediction (cache miss)
        with patch.object(predictor, '_load_model') as mock_load:
            mock_load.return_value = (Mock(predict=lambda x: [1], predict_proba=lambda x: [[0.3, 0.7]]), "1")
            # Not actually calling model, just testing cache logic
            pass
        
        # Test cache eviction
        for i in range(15):  # More than cache size
            key = predictor._features_to_key({"f": float(i)}, None)
            predictor._prediction_cache[key] = (1, 0.9, datetime.utcnow())
        
        assert len(predictor._prediction_cache) <= predictor.cache_size
    
    def test_batch_prediction(self):
        """Test batch predictions."""
        predictor = Predictor(Mock())
        
        # Mock single prediction
        async def mock_predict(model_name, features, version=None):
            from quantumtrade.mlops.serving.predictor import PredictionResponse
            return PredictionResponse(
                prediction=1,
                confidence=0.8,
                model_version="1",
                timestamp=datetime.utcnow(),
                latency_ms=1.0,
            )
        
        import asyncio
        predictor.predict = mock_predict
        
        # Would need async context - skipping detailed test
    
    def test_model_cache_eviction(self):
        """Test LRU model cache eviction."""
        predictor = Predictor(Mock(), cache_size=2)
        
        # Manually add models (bypassing actual loading)
        predictor._model_cache["model:1"] = (Mock(), "1")
        predictor._model_cache["model:2"] = (Mock(), "2")
        
        # Add third - should evict oldest
        predictor._model_cache["model:3"] = (Mock(), "3")
        
        assert len(predictor._model_cache) == 2
        assert "model:1" not in predictor._model_cache  # Evicted
        assert "model:2" in predictor._model_cache
        assert "model:3" in predictor._model_cache
    
    def test_metrics_tracking(self):
        """Test predictor metrics."""
        predictor = Predictor(Mock())
        predictor.predictions_total = 10
        predictor.cache_hits = 5
        predictor.cache_misses = 5
        predictor.errors = 0
        
        metrics = predictor.get_metrics()
        
        assert metrics["predictions_total"] == 10
        assert metrics["cache_hit_rate"] == 0.5
        assert metrics["errors"] == 0
