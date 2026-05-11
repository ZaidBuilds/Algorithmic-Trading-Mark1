"""Data and concept drift detection monitoring."""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import jensenshannon
import warnings
import logging

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """Report from drift detection analysis."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    feature_drifts: Dict[str, Dict[str, float]] = field(default_factory=dict)
    concept_drifts: Dict[str, float] = field(default_factory=dict)
    overall_drift_detected: bool = False
    psi_threshold: float = 0.2
    ks_alpha: float = 0.05
    
    def add_feature_drift(
        self,
        feature_name: str,
        psi: float,
        ks_stat: float,
        ks_pvalue: float,
        drift_detected: bool,
    ):
        """Add feature-level drift metrics."""
        self.feature_drifts[feature_name] = {
            "psi": psi,
            "ks_statistic": ks_stat,
            "ks_pvalue": ks_pvalue,
            "drift_detected": drift_detected,
        }
    
    def add_concept_drift(
        self,
        metric: str,
        current_value: float,
        baseline_value: float,
        drift_detected: bool,
    ):
        """Add concept drift metric."""
        self.concept_drifts[metric] = {
            "current": current_value,
            "baseline": baseline_value,
            "drift_detected": drift_detected,
        }
    
    def summarize(self) -> Dict[str, Any]:
        """Generate summary."""
        n_feature_drift = sum(
            1 for f in self.feature_drifts.values() 
            if f.get("drift_detected", False)
        )
        n_concept_drift = sum(
            1 for f in self.concept_drifts.values() 
            if f.get("drift_detected", False)
        )
        
        self.overall_drift_detected = (
            n_feature_drift > 0 or n_concept_drift > 0
        )
        
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_drift": self.overall_drift_detected,
            "features_with_drift": n_feature_drift,
            "concepts_with_drift": n_concept_drift,
            "total_features": len(self.feature_drifts),
            "total_concepts": len(self.concept_drifts),
            "feature_drifts": self.feature_drifts,
            "concept_drifts": self.concept_drifts,
        }


class DriftDetector:
    """
    Drift detection for data and concept shifts.
    
    Methods:
      - Population Stability Index (PSI) for feature distribution shifts
      - Kolmogorov-Smirnov test for continuous features
      - Jensen-Shannon divergence for probability distributions
      - Performance degradation monitoring
    """
    
    def __init__(
        self,
        psi_threshold: float = 0.2,
        ks_alpha: float = 0.05,
        js_threshold: float = 0.1,
        window_size: int = 1000,
    ):
        """
        Initialize drift detector.
        
        Args:
            psi_threshold: PSI threshold (0.2 = significant)
            ks_alpha: KS test significance level (0.05)
            js_threshold: Jensen-Shannon divergence threshold
            window_size: Size of sliding window for recent predictions
        """
        self.psi_threshold = psi_threshold
        self.ks_alpha = ks_alpha
        self.js_threshold = js_threshold
        self.window_size = window_size
        
        # Baseline distributions
        self.baseline_features: Optional[Dict[str, np.ndarray]] = None
        self.baseline_predictions: Optional[np.ndarray] = None
        self.baseline_metrics: Optional[Dict[str, float]] = None
        
        # History
        self.drift_history: List[DriftReport] = []
        
        logger.info("DriftDetector initialized")
    
    def set_baseline(
        self,
        features: pd.DataFrame,
        predictions: np.ndarray,
        metrics: Optional[Dict[str, float]] = None,
    ):
        """
        Set baseline distribution for comparison.
        
        Call this after initial model training.
        """
        self.baseline_features = {
            col: features[col].dropna().values 
            for col in features.columns
        }
        self.baseline_predictions = predictions
        self.baseline_metrics = metrics or {}
        logger.info(f"Baseline set with {len(features)} samples, {len(features.columns)} features")
    
    def detect_drift(
        self,
        current_features: pd.DataFrame,
        current_predictions: np.ndarray,
        current_metrics: Optional[Dict[str, float]] = None,
    ) -> DriftReport:
        """
        Detect drift in current data vs baseline.
        
        Args:
            current_features: Current feature values
            current_predictions: Current model predictions
            current_metrics: Current performance metrics
            
        Returns:
            DriftReport with findings
        """
        if self.baseline_features is None:
            raise ValueError("Baseline not set. Call set_baseline() first.")
        
        report = DriftReport(
            psi_threshold=self.psi_threshold,
            ks_alpha=self.ks_alpha,
        )
        
        # 1. Data Drift: Feature distributions
        logger.info("Checking feature drift...")
        for col in current_features.columns:
            if col in self.baseline_features:
                baseline_array = self.baseline_features[col]
                current_array = current_features[col].dropna().values
                
                if len(baseline_array) > 0 and len(current_array) > 0:
                    psi = self._calculate_psi(baseline_array, current_array)
                    ks_stat, ks_pvalue = stats.ks_2samp(baseline_array, current_array)
                    drift = (psi > self.psi_threshold) or (ks_pvalue < self.ks_alpha)
                    
                    report.add_feature_drift(
                        feature_name=col,
                        psi=psi,
                        ks_stat=ks_stat,
                        ks_pvalue=ks_pvalue,
                        drift_detected=drift,
                    )
        
        # 2. Concept Drift: Model performance degradation
        if current_metrics and self.baseline_metrics:
            logger.info("Checking concept drift...")
            
            # Accuracy drop
            acc_baseline = self.baseline_metrics.get("accuracy", 0)
            acc_current = current_metrics.get("accuracy", 0)
            acc_drop = (acc_baseline - acc_current) / acc_baseline if acc_baseline > 0 else 0
            acc_drift = acc_drop > 0.05  # 5% drop
            
            report.add_concept_drift(
                metric="accuracy",
                current_value=acc_current,
                baseline_value=acc_baseline,
                drift_detected=acc_drift,
            )
            
            # Confidence degradation
            if self.baseline_predictions is not None:
                baseline_conf = self._average_confidence(self.baseline_predictions)
                current_conf = self._average_confidence(current_predictions)
                conf_drop = (baseline_conf - current_conf) / baseline_conf if baseline_conf > 0 else 0
                conf_drift = conf_drop > 0.10  # 10% drop
                
                report.add_concept_drift(
                    metric="confidence",
                    current_value=current_conf,
                    baseline_value=baseline_conf,
                    drift_detected=conf_drift,
                )
        
        summary = report.summarize()
        self.drift_history.append(report)
        
        logger.info(
            f"Drift check: {summary['features_with_drift']}/{summary['total_features']} "
            f"features drifted, {summary['concepts_with_drift']}/{summary['total_concepts']} "
            f"concept metrics drifted"
        )
        
        return report
    
    def _average_confidence(self, probabilities: np.ndarray) -> float:
        """Compute average prediction confidence."""
        if len(probabilities) == 0:
            return 0.0
        # Confidence = max(p, 1-p) averaged
        confidences = np.maximum(probabilities, 1 - probabilities)
        return float(confidences.mean())
    
    def _calculate_psi(
        self,
        baseline: np.ndarray,
        current: np.ndarray,
        bins: int = 10,
    ) -> float:
        """
        Calculate Population Stability Index.
        
        PSI = Σ((actual_pct - expected_pct) * ln(actual_pct / expected_pct))
        
        Interpretation:
          - PSI < 0.1: No significant change
          - 0.1 <= PSI < 0.2: Moderate change
          - PSI >= 0.2: Significant shift
        """
        # Create bins based on baseline
        hist_baseline, bin_edges = np.histogram(baseline, bins=bins, density=True)
        hist_current, _ = np.histogram(current, bins=bin_edges, density=True)
        
        # Add small epsilon to avoid division by zero
        epsilon = 1e-10
        hist_baseline = hist_baseline + epsilon
        hist_current = hist_current + epsilon
        
        # Normalize to percentages
        hist_baseline = hist_baseline / hist_baseline.sum()
        hist_current = hist_current / hist_current.sum()
        
        # Calculate PSI
        psi = np.sum((hist_current - hist_baseline) * np.log(hist_current / hist_baseline))
        return float(psi)
    
    def _calculate_ks_test(
        self,
        baseline: np.ndarray,
        current: np.ndarray,
    ) -> Tuple[float, float]:
        """Kolmogorov-Smirnov test for distribution equality."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return stats.ks_2samp(baseline, current)
    
    def _calculate_js_divergence(
        self,
        baseline: np.ndarray,
        current: np.ndarray,
        bins: int = 10,
    ) -> float:
        """Jensen-Shannon divergence between distributions."""
        hist_baseline, _ = np.histogram(baseline, bins=bins, density=True)
        hist_current, _ = np.histogram(current, bins=bins, density=True)
        
        # Normalize to probabilities
        hist_baseline = hist_baseline / hist_baseline.sum()
        hist_current = hist_current / hist_current.sum()
        
        return jensenshannon(hist_baseline, hist_current)
    
    def get_drift_summary(self, last_n: Optional[int] = None) -> Dict[str, Any]:
        """Get summary of drift history."""
        history = self.drift_history[-last_n:] if last_n else self.drift_history
        
        if not history:
            return {"no_drift_reports": True}
        
        total_checks = len(history)
        drift_events = sum(1 for r in history if r.overall_drift_detected)
        
        return {
            "total_checks": total_checks,
            "drift_events": drift_events,
            "drift_rate": drift_events / total_checks if total_checks > 0 else 0,
            "latest": history[-1].summarize() if history else None,
        }
    
    def should_trigger_retraining(self, report: DriftReport) -> bool:
        """Determine if drift warrants automatic retraining."""
        summary = report.summarize()
        if not report.overall_drift_detected:
            return False
        
        # Trigger if >30% features drifted
        if summary['total_features'] > 0:
            drift_rate = summary['features_with_drift'] / summary['total_features']
            if drift_rate > 0.3:
                logger.warning(f"High feature drift rate: {drift_rate:.1%}")
                return True
        
        # Trigger if accuracy dropped >5%
        for metric_info in report.concept_drifts.values():
            if metric_info.get("drift_detected"):
                metric_name = next(
                    (k for k, v in report.concept_drifts.items() if v == metric_info),
                    "unknown"
                )
                if metric_name == "accuracy":
                    return True
        
        return False
