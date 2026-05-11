"""Tests for drift detection module."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from quantumtrade.mlops.drift_detector import DriftDetector, DriftReport

# Fixtures will be defined inline for self-containment


class TestDriftDetector:
    """Test DriftDetector functionality."""
    
    @pytest.fixture
    def detector(self):
        """Create drift detector with test thresholds."""
        return DriftDetector(
            psi_threshold=0.2,
            ks_alpha=0.05,
            js_threshold=0.1,
            window_size=100,
        )
    
    @pytest.fixture
    def baseline_data(self):
        """Generate stable baseline distribution."""
        np.random.seed(42)
        return np.random.normal(0, 1, 1000)
    
    @pytest.fixture
    def shifted_data(self):
        """Generate shifted distribution."""
        np.random.seed(43)
        return np.random.normal(1, 1, 1000)  # Mean shift
    
    @pytest.fixture
    def identical_data(self):
        """Generate identical distribution."""
        np.random.seed(42)
        return np.random.normal(0, 1, 1000)
    
    def test_detector_initialization(self, detector):
        """Test detector initializes correctly."""
        assert detector.psi_threshold == 0.2
        assert detector.ks_alpha == 0.05
        assert detector.window_size == 100
        assert detector.baseline_features is None
    
    def test_set_baseline(self, detector, baseline_data):
        """Test setting baseline."""
        baseline_df = pd.DataFrame({"feature1": baseline_data})
        detector.set_baseline(baseline_df, np.random.randint(0, 2, 1000))
        
        assert detector.baseline_features is not None
        assert "feature1" in detector.baseline_features
        assert len(detector.baseline_features["feature1"]) == 1000
    
    def test_psi_calculation(self, detector, baseline_data, shifted_data):
        """Test PSI calculation."""
        psi = detector._calculate_psi(baseline_data, shifted_data)
        assert psi > 0  # Should be > 0 due to shift
        assert psi < 2  # PSI typically < 1 for reasonable shifts
    
    def test_ks_test(self, detector, baseline_data, shifted_data):
        """Test Kolmogorov-Smirnov test."""
        stat, pvalue = detector._calculate_ks_test(baseline_data, shifted_data)
        assert 0 <= stat <= 1
        assert 0 <= pvalue <= 1
        # Shifted distributions should have lower p-value
        assert pvalue < 0.05  # Should reject identical distribution
    
    def test_identical_distributions(self, detector, baseline_data, identical_data):
        """Test with identical distributions."""
        stat, pvalue = detector._calculate_ks_test(baseline_data, identical_data)
        assert pvalue > 0.05  # Should not reject identicality
    
    def test_detect_drift_no_baseline(self, detector, baseline_data):
        """Test error when baseline not set."""
        current_df = pd.DataFrame({"feature1": baseline_data[:500]})
        with pytest.raises(ValueError, match="Baseline not set"):
            detector.detect_drift(current_df, np.zeros(500))
    
    def test_detect_drift_feature_level(self, detector, baseline_data, shifted_data):
        """Test feature-level drift detection."""
        # Set baseline with metrics
        baseline_df = pd.DataFrame({"feat1": baseline_data, "feat2": baseline_data})
        detector.set_baseline(
            baseline_df, 
            np.zeros(1000),
            metrics={"accuracy": 0.85}
        )
        
        # Current with shift
        current_df = pd.DataFrame({"feat1": shifted_data, "feat2": baseline_data})
        report = detector.detect_drift(
            current_df,
            np.zeros(1000),
            current_metrics={"accuracy": 0.75},
        )
        
        assert isinstance(report, DriftReport)
        summary = report.summarize()
        assert summary["total_features"] == 2
        # feat1 should show drift, feat2 should not
    
    def test_concept_drift_detection(self, detector, baseline_data):
        """Test concept drift (performance degradation)."""
        baseline_df = pd.DataFrame({"f": baseline_data})
        detector.set_baseline(
            baseline_df, np.zeros(1000),
            metrics={"accuracy": 0.85, "precision": 0.80}
        )
        
        current_df = pd.DataFrame({"f": baseline_data[:500]})
        report = detector.detect_drift(
            current_df, np.zeros(500),
            current_metrics={"accuracy": 0.78, "precision": 0.72},
        )
        
        summary = report.summarize()
        assert summary["overall_drift"] is True
        # Should have accuracy concept drift detected
    
    def test_should_trigger_retraining(self, detector, baseline_data):
        """Test retraining trigger logic."""
        # No drift -> no retrain
        baseline_df = pd.DataFrame({"f": baseline_data})
        detector.set_baseline(baseline_df, np.zeros(1000))
        
        no_drift_report = DriftReport()
        no_drift_report.feature_drifts["f"] = {
            "psi": 0.05, "ks_statistic": 0.01, "ks_pvalue": 0.50,
            "drift_detected": False,
        }
        assert detector.should_trigger_retraining(no_drift_report) is False
        
        # High drift -> retrain
        drift_report = DriftReport()
        drift_report.feature_drifts["f"] = {
            "psi": 0.3, "ks_statistic": 0.2, "ks_pvalue": 0.001,
            "drift_detected": True,
        }
        assert detector.should_trigger_retraining(drift_report) is True
    
    def test_drift_summary(self, detector, baseline_data, shifted_data):
        """Test drift summary generation."""
        baseline_df = pd.DataFrame({"f": baseline_data})
        detector.set_baseline(baseline_df, np.zeros(1000))
        
        current_df = pd.DataFrame({"f": shifted_data})
        report = detector.detect_drift(current_df, np.zeros(1000))
        summary = report.summarize()
        
        assert "total_features" in summary
        assert "features_with_drift" in summary
        assert "overall_drift" in summary
        assert summary["total_features"] == 1
    
    def test_multiple_features(self, detector):
        """Test with multiple features."""
        np.random.seed(42)
        n = 1000
        baseline = pd.DataFrame({
            "f1": np.random.normal(0, 1, n),
            "f2": np.random.uniform(0, 1, n),
            "f3": np.random.exponential(1, n),
        })
        detector.set_baseline(baseline, np.zeros(n))
        
        # Shift only f2
        current = pd.DataFrame({
            "f1": baseline["f1"],
            "f2": baseline["f2"] + 1.0,  # shift
            "f3": baseline["f3"],
        })
        report = detector.detect_drift(current, np.zeros(n))
        summary = report.summarize()
        
        assert summary["features_with_drift"] == 1


class TestDriftReport:
    """Test DriftReport dataclass."""
    
    def test_report_creation(self):
        """Test creating a drift report."""
        report = DriftReport()
        assert report.feature_drifts == {}
        assert report.concept_drifts == {}
        assert report.overall_drift_detected is False
    
    def test_add_feature_drift(self):
        """Test adding feature drift."""
        report = DriftReport()
        report.add_feature_drift(
            feature_name="test_feature",
            psi=0.25,
            ks_stat=0.15,
            ks_pvalue=0.01,
            drift_detected=True,
        )
        assert "test_feature" in report.feature_drifts
        assert report.feature_drifts["test_feature"]["psi"] == 0.25
    
    def test_add_concept_drift(self):
        """Test adding concept drift."""
        report = DriftReport()
        report.add_concept_drift(
            metric="accuracy",
            current_value=0.75,
            baseline_value=0.85,
            drift_detected=True,
        )
        assert "accuracy" in report.concept_drifts
    
    def test_summarize(self):
        """Test summary generation."""
        report = DriftReport()
        report.add_feature_drift("f1", 0.3, 0.2, 0.001, True)
        report.add_feature_drift("f2", 0.1, 0.05, 0.2, False)
        report.add_concept_drift("accuracy", 0.75, 0.85, True)
        
        summary = report.summarize()
        assert summary["features_with_drift"] == 1
        assert summary["total_features"] == 2
        assert summary["concepts_with_drift"] == 1
        assert summary["overall_drift"] is True
    
    def test_summarize_no_drift(self):
        """Test summary with no drift."""
        report = DriftReport()
        report.add_feature_drift("f1", 0.05, 0.01, 0.9, False)
        report.add_concept_drift("accuracy", 0.85, 0.85, False)
        
        summary = report.summarize()
        assert summary["overall_drift"] is False
