"""Integration tests for retraining pipeline."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
import os

from quantumtrade.mlops.pipeline import RetrainingPipeline, RetrainingConfig
from quantumtrade.mlops.registry import ModelRegistry
from quantumtrade.mlops.validator import ModelValidator, PromotionCriteria
from quantumtrade.mlops.drift_detector import DriftDetector
from ml.feature_engineer import FeatureEngineer
from ml.ml_predictor import MLPredictor


@pytest.fixture
def temp_mlflow_dir():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_training_data():
    """Generate synthetic training data."""
    np.random.seed(42)
    n_days = 200
    dates = pd.date_range(end=datetime.utcnow(), periods=n_days, freq='D')
    
    prices = 100 + np.cumsum(np.random.randn(n_days) * 0.5)
    
    df = pd.DataFrame({
        'Open': prices * (1 + np.random.randn(n_days) * 0.001),
        'High': prices * (1 + np.abs(np.random.randn(n_days)) * 0.005),
        'Low': prices * (1 - np.abs(np.random.randn(n_days)) * 0.005),
        'Close': prices,
        'Volume': np.random.randint(100000, 1000000, n_days),
    }, index=dates)
    
    return df


@pytest.fixture
def registry(temp_mlflow_dir):
    """Create test MLflow registry."""
    return ModelRegistry(
        tracking_uri=temp_mlflow_dir,
        artifact_location=temp_mlflow_dir,
        experiment_name="test_pipeline",
    )


@pytest.fixture
def validator():
    """Create test model validator."""
    criteria = PromotionCriteria(
        min_accuracy=0.55,
        improvement_threshold=0.01,
        requires_canary=False,  # Disable canary for unit tests
    )
    return ModelValidator(criteria=criteria)


@pytest.fixture
def drift_detector():
    """Create test drift detector."""
    return DriftDetector(psi_threshold=0.2, ks_alpha=0.05)


class TestRetrainingPipeline:
    """Test retraining pipeline."""
    
    def test_pipeline_initialization(self, registry, validator, drift_detector):
        """Test pipeline setup."""
        config = RetrainingConfig(
            enabled=True,
            min_samples=100,
            improvement_threshold=0.02,
        )
        
        pipeline = RetrainingPipeline(
            config=config,
            registry=registry,
            validator=validator,
            drift_detector=drift_detector,
        )
        
        assert pipeline.config.enabled is True
        assert pipeline.registry == registry
        assert pipeline.validator == validator
    
    def test_fetch_training_data(self, sample_training_data):
        """Test data fetching."""
        config = RetrainingConfig()
        pipeline = RetrainingPipeline(
            config=config,
            registry=Mock(),
            validator=Mock(),
        )
        
        # Override data fetcher
        pipeline.data_fetcher = lambda: sample_training_data
        
        data = pipeline._fetch_training_data()
        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0
    
    def test_data_validation_pass(self, sample_training_data):
        """Test data quality validation - passing."""
        config = RetrainingConfig()
        pipeline = RetrainingPipeline(
            config=config,
            registry=Mock(),
            validator=Mock(),
        )
        
        result = pipeline._validate_data(sample_training_data)
        assert result["passed"] is True
        assert len(result["errors"]) == 0
    
    def test_data_validation_fail(self):
        """Test data quality validation - failing."""
        config = RetrainingConfig()
        pipeline = RetrainingPipeline(
            config=config,
            registry=Mock(),
            validator=Mock(),
        )
        
        # Empty DataFrame
        empty_df = pd.DataFrame()
        result = pipeline._validate_data(empty_df)
        assert result["passed"] is False
    
    def test_pipeline_full_run(
        self, 
        registry, 
        validator, 
        sample_training_data
    ):
        """Test complete pipeline execution."""
        config = RetrainingConfig(
            enabled=True,
            min_samples=50,
            improvement_threshold=-0.01,  # Accept any improvement
            performance_threshold=0.5,
            requires_canary=False,
        )
        
        drift = DriftDetector()
        
        pipeline = RetrainingPipeline(
            config=config,
            registry=registry,
            validator=validator,
            drift_detector=drift,
        )
        
        # Mock backtester to return good results
        def mock_backtester(model, df):
            return {
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.15,
                "num_trades": 100,
                "win_rate": 0.55,
            }
        
        pipeline.backtester = mock_backtester
        
        # Override data fetcher
        pipeline.data_fetcher = lambda: sample_training_data
        
        # Run pipeline
        result = pipeline.run_pipeline(model_name="test_model")
        
        assert result["status"] in [
            "completed_canary_promoted",
            "completed_direct_promote",
        ]
        assert result["new_version"] is not None
        assert "steps" in result
    
    def test_pipeline_insufficient_data(self, registry, validator):
        """Test pipeline with insufficient data."""
        config = RetrainingConfig(min_samples=10000)
        pipeline = RetrainingPipeline(
            config=config,
            registry=registry,
            validator=validator,
        )
        
        # Small dataset
        small_df = pd.DataFrame({'Close': [1, 2, 3]})
        pipeline.data_fetcher = lambda: small_df
        
        result = pipeline.run_pipeline()
        assert result["status"] == "skipped_insufficient_data"
    
    def test_pipeline_below_threshold(self, registry, validator, sample_training_data):
        """Test pipeline with low model accuracy."""
        config = RetrainingConfig(
            min_samples=50,
            performance_threshold=0.95,  # Impossible threshold
            requires_canary=False,
        )
        pipeline = RetrainingPipeline(
            config=config,
            registry=registry,
            validator=validator,
        )
        pipeline.data_fetcher = lambda: sample_training_data
        
        result = pipeline.run_pipeline()
        assert result["status"] == "failed_performance_threshold"
    
    def test_parse_cron_time(self):
        """Test cron parsing."""
        config = RetrainingConfig()
        assert config._parse_cron_time("0 2 * * *") == "02:00"
        assert config._parse_cron_time("30 14 * * *") == "14:30"
    
    def test_pipeline_status(self, registry, validator):
        """Test pipeline status reporting."""
        config = RetrainingConfig()
        pipeline = RetrainingPipeline(config, registry, validator)
        status = pipeline.get_pipeline_status()
        
        assert "scheduler_running" in status
        assert "last_run" in status
        assert "config" in status


class TestEndToEndWorkflow:
    """End-to-end integration tests."""
    
    def test_complete_ml_lifecycle(
        self, 
        registry, 
        validator, 
        sample_training_data
    ):
        """
        Complete ML lifecycle test:
        1. Train initial model
        2. Register
        3. Promote to production
        4. Simulate drift
        5. Retrain
        6. Compare
        7. Promote new version
        """
        # Step 1: Train initial model
        engineer = FeatureEngineer()
        df_features = engineer.engineer_features(sample_training_data)
        X, y = engineer.get_feature_matrix(df_features)
        
        model = MLPredictor(model_type='random_forest')
        metrics1 = model.train(X, y)
        
        # Step 2: Register
        v1 = registry.register_model(
            model=model,
            name="e2e_test",
            metrics=metrics1,
            params={"model_type": "random_forest"},
            training_data=sample_training_data,
        )
        
        # Step 3: Promote to production
        registry.promote_model("e2e_test", v1, "Production")
        prod = registry.get_latest_model("e2e_test", stage="Production")
        assert prod.version == v1
        
        # Step 4: Simulate drift by lowering accuracy of next model
        # (In real scenario, would wait for new data)
        
        # Step 5: Retrain on slightly shifted data
        shifted_data = sample_training_data.copy()
        shifted_data['Close'] = shifted_data['Close'] * 1.01  # Slight trend shift
        
        df_features2 = engineer.engineer_features(shifted_data)
        X2, y2 = engineer.get_feature_matrix(df_features2)
        
        model2 = MLPredictor(model_type='random_forest')
        metrics2 = model2.train(X2, y2)
        
        # Step 6: Register and compare
        v2 = registry.register_model(
            model=model2,
            name="e2e_test",
            metrics=metrics2,
            params={},
            training_data=shifted_data,
        )
        
        mv1 = registry.get_model_version("e2e_test", v1)
        mv2 = registry.get_model_version("e2e_test", v2)
        comparison = registry.compare_versions(mv1, mv2)
        
        assert "metric_deltas" in comparison
        
        # Step 7: Promote if better
        accuracy_delta = comparison["metric_deltas"]["accuracy"]["delta"]
        if accuracy_delta > 0:
            registry.promote_model("e2e_test", v2, "Production")
            new_prod = registry.get_latest_model("e2e_test", stage="Production")
            assert new_prod.version == v2
    
    def test_concept_drift_triggers_alert(self, drift_detector, sample_training_data):
        """Test that concept drift triggers alert."""
        engineer = FeatureEngineer()
        df = engineer.engineer_features(sample_training_data)
        X, y = engineer.get_feature_matrix(df)
        
        model = MLPredictor()
        model.train(X, y)
        
        # Set baseline metrics
        baseline_metrics = model.get_metrics()
        
        # Simulate degradation
        degraded_metrics = baseline_metrics.copy()
        degraded_metrics["accuracy"] *= 0.9  # 10% drop
        
        drift_detector.set_baseline(df, model.predict(X)[1], baseline_metrics)
        
        report = drift_detector.detect_drift(
            df, 
            model.predict(X)[1], 
            degraded_metrics,
        )
        
        assert drift_detector.should_trigger_retraining(report) is True
