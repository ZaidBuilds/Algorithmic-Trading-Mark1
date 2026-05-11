"""Tests for MLOps registry module (mocked MLflow)."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from unittest.mock import Mock, patch

from quantumtrade.mlops.registry import ModelRegistry, ModelVersion, ModelInfo
# Use sklearn directly for test model
from sklearn.ensemble import RandomForestClassifier


@pytest.fixture
def mock_mlflow_client():
    """Create a fully mocked MLflow client."""
    client = Mock(spec=MlflowClient)
    
    # Mock experiment
    exp = Mock()
    exp.experiment_id = "0"
    exp.artifact_location = "/tmp/mlflow"
    client.get_experiment_by_name.return_value = exp
    client.create_experiment.return_value = "0"
    
    # Empty model versions initially
    client.search_model_versions.return_value = []
    
    return client


@pytest.fixture
def registry(mock_mlflow_client):
    """Create registry with mocked MLflow client."""
    with patch('quantumtrade.mlops.registry.MlflowClient', return_value=mock_mlflow_client), \
         patch('quantumtrade.mlops.registry.mlflow.set_tracking_uri'), \
         patch('quantumtrade.mlops.registry.mlflow.start_run'):
        reg = ModelRegistry(
            tracking_uri="http://localhost:5000",
            experiment_name="test_models",
        )
        reg.client = mock_mlflow_client
        return reg


class MockRun:
    """Mock MLflow run."""
    def __init__(self, run_id, data):
        self.info = Mock()
        self.info.run_id = run_id
        self.info.start_time = 1704576000000  # 2024-01-08
        self.data = data


class MockModelVersion:
    """Mock MLflow model version."""
    def __init__(self, name, version, stage, run_id, source, current_stage=None):
        self.name = name
        self.version = version
        self.current_stage = current_stage or stage
        self.run_id = run_id
        self.source = source
        self.creation_timestamp = 1704576000000


class TestModelRegistry:
    """Test ModelRegistry functionality."""
    
    def test_registry_initialization(self, registry):
        """Test registry can be initialized."""
        assert registry is not None
        assert registry.experiment_name == "test_models"
    
    def test_register_model(self, registry, mock_mlflow_client):
        """Test model registration."""
        # Setup mocks
        mock_run = MockRun(
            run_id="test_run_123",
            data=Mock(
                metrics={"accuracy": 0.85},
                params={"model_type": "random_forest"},
            )
        )
        
        mock_model_version = MockModelVersion(
            name="test_model",
            version="1",
            stage="None",
            run_id="test_run_123",
            source="runs:/test_run_123/model",
            current_stage="None",
        )
        
        # Create a context manager for start_run
        mock_cm = Mock()
        mock_cm.__enter__ = Mock(return_value=mock_run)
        mock_cm.__exit__ = Mock(return_value=None)
        
        # Patch all mlflow interactions
        with patch('quantumtrade.mlops.registry.mlflow.start_run', return_value=mock_cm), \
             patch.object(mock_mlflow_client, 'create_model_version', return_value=mock_model_version), \
             patch('quantumtrade.mlops.registry.mlflow.log_metric'), \
             patch('quantumtrade.mlops.registry.mlflow.log_metrics'), \
             patch('quantumtrade.mlops.registry.mlflow.log_param'), \
             patch('quantumtrade.mlops.registry.mlflow.log_params'), \
             patch('quantumtrade.mlops.registry.mlflow.sklearn.log_model'):
            
            # Train a simple sklearn model
            X = np.random.randn(50, 5)
            y = (X[:, 0] > 0).astype(int)
            model = RandomForestClassifier(n_estimators=10, random_state=42)
            model.fit(X, y)
            
            version = registry.register_model(
                model=model,
                name="test_model",
                metrics={"accuracy": 0.85},
                params={"n_estimators": 10},
                training_data=pd.DataFrame(X),
            )
            
            assert version == "1"
    
    def test_get_latest_model_no_models(self, registry):
        """Test getting latest model when none exist."""
        result = registry.get_latest_model("nonexistent", stage="Production")
        assert result is None
    
    def test_list_models_empty(self, registry, mock_mlflow_client):
        """Test listing models when empty."""
        mock_mlflow_client.search_model_versions.return_value = []
        models = registry.list_models()
        assert isinstance(models, list)
    
    def test_promote_model(self, registry, mock_mlflow_client):
        """Test model promotion."""
        mock_version = MockModelVersion("test", "1", "Staging", "run123", "uri")
        mock_mlflow_client.search_model_versions.return_value = [mock_version]
        
        registry.promote_model("test_model", "1", "Production")
        
        # Verify transition called
        mock_mlflow_client.transition_model_version_stage.assert_called_once_with(
            name="test_model",
            version="1",
            stage="Production",
        )
    
    def test_compare_versions(self, registry):
        """Test version comparison."""
        v1 = ModelVersion(
            name="test", version="1", run_id="r1",
            metrics={"accuracy": 0.80, "precision": 0.75},
            params={}, training_data_hash="h1",
            training_start="2024-01-01", training_end="2024-01-02",
            git_commit="abc", artifact_uri="s3://bucket/v1", stage="Production",
        )
        v2 = ModelVersion(
            name="test", version="2", run_id="r2",
            metrics={"accuracy": 0.85, "precision": 0.82},
            params={}, training_data_hash="h2",
            training_start="2024-01-03", training_end="2024-01-04",
            git_commit="def", artifact_uri="s3://bucket/v2", stage="Staging",
        )
        
        comparison = registry.compare_versions(v1, v2)
        
        assert "metric_deltas" in comparison
        assert comparison["metric_deltas"]["accuracy"]["delta"] == pytest.approx(0.05)
        assert comparison["winner"] == "2"
    
    def test_rollback_model(self, registry, mock_mlflow_client):
        """Test model rollback."""
        # Setup: current production = v2, rollback to v1
        v1 = MockModelVersion("test", "1", "Production", "r1", "uri")
        v2 = MockModelVersion("test", "2", "Production", "r2", "uri")
        
        # Patch get_latest_model to return v2 (current), and get_model_version not used
        with patch.object(registry, 'get_latest_model', return_value=v2), \
             patch.object(registry, 'promote_model') as mock_promote:
            registry.rollback_model("test_model", "1")
            
            # Should archive current (v2) and promote target (v1)
            assert mock_promote.call_count == 2
            calls = mock_promote.call_args_list
            # First call: archive v2
            assert calls[0][0] == ("test_model", "2", "Archived")
            # Second call: promote v1 to Production
            assert calls[1][0] == ("test_model", "1", "Production")


class TestModelVersion:
    """Test ModelVersion class."""
    
    def test_model_version_creation(self):
        """Test creating a ModelVersion."""
        mv = ModelVersion(
            name="test_model",
            version="1",
            run_id="abc123",
            metrics={"accuracy": 0.9, "precision": 0.85},
            params={"n_estimators": 100},
            training_data_hash="hash123",
            training_start="2024-01-01T00:00:00",
            training_end="2024-01-01T02:00:00",
            git_commit="abc123def",
            artifact_uri="s3://bucket/path",
            stage="Staging",
        )
        assert mv.name == "test_model"
        assert mv.version == "1"
        assert mv.stage == "Staging"
        assert mv.metrics["accuracy"] == 0.9
    
    def test_model_version_to_dict(self):
        """Test serialization."""
        mv = ModelVersion(
            name="test", version="1", run_id="run1",
            metrics={"f1": 0.88}, params={},
            training_data_hash="h", training_start="s", training_end="e",
            git_commit="g", artifact_uri="uri", stage="Production",
        )
        d = mv.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1"
        assert d["metrics"]["f1"] == 0.88


# Need MlflowClient import for spec
from mlflow.tracking import MlflowClient
