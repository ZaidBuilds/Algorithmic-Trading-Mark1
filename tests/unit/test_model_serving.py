"""Tests for model serving module."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import pandas as pd
from datetime import datetime

from quantumtrade.mlops.serving.server import app, health_check, list_models
from quantumtrade.mlops.serving.predictor import Predictor, PredictionResponse
from quantumtrade.mlops.serving.versioning import ModelVersionManager, DeploymentStage
from quantumtrade.mlops.registry import ModelRegistry, ModelVersion


@pytest.fixture
def mock_registry():
    """Create mock model registry."""
    registry = Mock(spec=ModelRegistry)
    registry.list_models.return_value = []
    registry.list_versions.return_value = []
    registry.get_latest_model.return_value = None
    return registry


@pytest.fixture
def mock_predictor():
    """Create mock predictor."""
    predictor = Mock(spec=Predictor)
    predictor.predict.return_value = PredictionResponse(
        prediction=1,
        confidence=0.85,
        model_version="1",
        timestamp=datetime.utcnow(),
        latency_ms=5.2,
    )
    predictor.get_metrics.return_value = {
        "predictions_total": 100,
        "cache_hits": 50,
        "cache_hit_rate": 0.5,
    }
    predictor.cache_hits = 50
    predictor.cache_misses = 50
    predictor.clear_cache = Mock()
    return predictor


@pytest.fixture
def test_client(mock_registry, mock_predictor):
    """Create FastAPI test client with mocked dependencies."""
    # Patch module-level variables and startup event
    with patch('quantumtrade.mlops.serving.server.registry', mock_registry), \
         patch('quantumtrade.mlops.serving.server.predictor', mock_predictor), \
         patch('quantumtrade.mlops.serving.server.startup_event', lambda: None):
        from quantumtrade.mlops.serving.server import app as fastapi_app
        client = TestClient(fastapi_app)
        yield client


class TestServingServer:
    """Test FastAPI server endpoints."""
    
    def test_health_check(self, test_client):
        """Test health endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "ready" in data
    
    def test_list_models(self, test_client):
        """Test list models endpoint."""
        response = test_client.get("/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
    
    def test_list_versions(self, test_client, mock_registry):
        """Test list versions endpoint."""
        # Create mock version objects with expected attributes
        mock_versions = [
            ModelVersion(
                name="test_model",
                version="1",
                run_id="abc123",
                metrics={"accuracy": 0.85},
                params={},
                training_data_hash="h1",
                training_start="2024-01-01T00:00:00",
                training_end="2024-01-01T02:00:00",
                git_commit="abc",
                artifact_uri="s3://bucket/v1",
                stage="Production",
            ),
            ModelVersion(
                name="test_model",
                version="2",
                run_id="def456",
                metrics={"accuracy": 0.87},
                params={},
                training_data_hash="h2",
                training_start="2024-01-02T00:00:00",
                training_end="2024-01-02T02:00:00",
                git_commit="def",
                artifact_uri="s3://bucket/v2",
                stage="Staging",
            ),
        ]
        mock_registry.list_versions.return_value = mock_versions
        
        response = test_client.get("/models/test_model/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_model"
        assert len(data["versions"]) == 2
    
    def test_predict_endpoint(self, test_client, mock_predictor):
        """Test prediction endpoint."""
        request_data = {
            "features": {"rsi": 65.0, "sma": 100.0},
            "model_name": "test_model",
            "version": None,
        }
        
        response = test_client.post("/predict/test_model", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "prediction" in data
        assert "confidence" in data
        assert "model_version" in data
        assert "timestamp" in data
    
    def test_predict_endpoint_error(self, test_client, mock_predictor):
        """Test prediction error handling."""
        mock_predictor.predict.side_effect = ValueError("Model not found")
        request_data = {"features": {"f1": 1.0}, "model_name": "missing"}
        response = test_client.post("/predict/missing", json=request_data)
        assert response.status_code == 400
    
    def test_batch_predict(self, test_client, mock_predictor):
        """Test batch prediction endpoint."""
        request_data = {
            "features_list": [
                {"f1": 1.0},
                {"f1": 2.0},
            ],
            "model_name": "test",
        }
        
        response = test_client.post("/predict/batch/test", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "predictions" in data
        assert len(data["predictions"]) == 2
    
    def test_promote_model(self, test_client, mock_registry):
        """Test model promotion endpoint."""
        response = test_client.post(
            "/models/test_model/promote/1",
            json={"version": "1", "stage": "Production"},
        )
        assert response.status_code == 200
        mock_registry.promote_model.assert_called_once_with(
            "test_model", "1", "Production"
        )
    
    def test_get_latest_model(self, test_client, mock_registry):
        """Test get latest model endpoint."""
        mock_version = ModelVersion(
            name="test_model",
            version="1",
            run_id="abc123",
            metrics={"accuracy": 0.85},
            params={},
            training_data_hash="abc",
            training_start="2024-01-01T00:00:00",
            training_end="2024-01-01T02:00:00",
            git_commit="abc",
            artifact_uri="s3://bucket/v1",
            stage="Production",
        )
        mock_registry.get_latest_model.return_value = mock_version
        
        response = test_client.get("/models/test_model/latest/production")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1"
    
    def test_rollback_model(self, test_client, mock_registry):
        """Test rollback endpoint."""
        response = test_client.post("/models/test_model/rollback/1")
        assert response.status_code == 200
        assert response.json()["rolled_back_to"] == "1"
    
    def test_get_metrics(self, test_client, mock_predictor):
        """Test metrics endpoint."""
        response = test_client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "predictor" in data
        assert "cache_hits" in data
    
    def test_clear_cache(self, test_client, mock_predictor):
        """Test cache clear endpoint."""
        response = test_client.delete("/cache")
        assert response.status_code == 200
        assert response.json()["status"] == "cache_cleared"
        mock_predictor.clear_cache.assert_called_once()


class TestPredictor:
    """Test predictor class."""
    
    @pytest.fixture
    def mock_registry_with_model(self):
        """Create registry with a mock model."""
        registry = Mock(spec=ModelRegistry)
        
        # Mock model version
        mv = Mock()
        mv.version = "1"
        mv.run_id = "abc123"
        mv.artifact_uri = "s3://bucket/model"
        
        registry.get_latest_model.return_value = mv
        registry.get_model_version.return_value = mv
        
        # Mock model
        model = Mock()
        model.predict.return_value = np.array([1])
        model.predict_proba.return_value = np.array([[0.3, 0.7]])
        model.feature_names_in_ = ["f1", "f2"]
        
        return registry, model
    
    def test_predictor_init(self, mock_registry_with_model):
        """Test predictor initialization."""
        registry, model = mock_registry_with_model
        # Simply instantiate predictor with mock registry
        predictor = Predictor(registry=registry)
        assert predictor is not None
    
    def test_features_to_key(self):
        """Test cache key generation."""
        predictor = Predictor(Mock())
        key = predictor._features_to_key({"a": 1.0, "b": 2.0}, version="1")
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hex
    
    def test_prediction_caching(self):
        """Test prediction cache."""
        predictor = Predictor(Mock(), cache_ttl=60, cache_size=2)
        
        # Manually add to cache
        key = predictor._features_to_key({"f": 1.0}, None)
        predictor._prediction_cache[key] = (1, 0.9, datetime.utcnow())
        
        # Should hit cache
        cached = predictor._prediction_cache.get(key)
        assert cached is not None


class TestModelVersionManager:
    """Test version management."""
    
    def test_version_manager_init(self, mock_registry):
        """Test initialization."""
        manager = ModelVersionManager(mock_registry)
        assert manager is not None
    
    def test_get_current_production_none(self, mock_registry):
        """Test when no production model exists."""
        mock_registry.get_latest_model.return_value = None
        manager = ModelVersionManager(mock_registry)
        result = manager.get_current_production("test")
        assert result is None
    
    def test_get_current_production_exists(self, mock_registry):
        """Test when production model exists."""
        mv = Mock()
        mv.version = "1"
        mv.stage = "Production"
        mv.run_id = "abc"
        mv.metrics = {"accuracy": 0.85}
        mv.params = {}
        mv.artifact_uri = "s3://bucket"
        mock_registry.get_latest_model.return_value = mv
        
        manager = ModelVersionManager(mock_registry)
        result = manager.get_current_production("test")
        assert result.version == "1"
        assert result.stage == DeploymentStage.PRODUCTION
    
    def test_ab_test_configuration(self, mock_registry):
        """Test A/B test setup."""
        manager = ModelVersionManager(mock_registry)
        manager.configure_ab_test(
            model_name="test",
            control_version="1",
            treatment_version="2",
            traffic_split=0.3,
        )
        
        config = manager.get_ab_test_status("test")
        assert config is not None
        assert config["control"] == "1"
        assert config["treatment"] == "2"
        assert config["split"] == 0.3
    
    def test_version_routing_ab(self, mock_registry):
        """Test A/B routing."""
        manager = ModelVersionManager(mock_registry)
        manager.configure_ab_test("test", "1", "2", traffic_split=0.5)
        
        # Deterministic routing based on request_id
        versions = set()
        for i in range(100):
            v = manager.get_version_for_request("test", request_id=f"req_{i}")
            versions.add(v)
        
        # Should see both versions (with 50/50 split)
        assert len(versions) == 2
        assert "1" in versions
        assert "2" in versions
