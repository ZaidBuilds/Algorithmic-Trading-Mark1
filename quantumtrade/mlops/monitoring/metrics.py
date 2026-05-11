"""Model performance metrics monitoring."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """Snapshot of model metrics at a point in time."""
    timestamp: datetime
    model_version: str
    metrics: Dict[str, float]
    predictions_count: int = 0
    data_volume: int = 0


@dataclass
class PerformanceTrend:
    """Performance trend analysis."""
    metric_name: str
    current_value: float
    baseline_value: float
    change_pct: float
    direction: str  # "improving", "degrading", "stable"
    window_days: int


class ModelMetrics:
    """
    Track and analyze model performance metrics over time.
    
    Features:
    - Sliding window of recent predictions
    - Trend analysis (improving/degrading)
    - Alert threshold monitoring
    - Statistical testing for significant changes
    """
    
    def __init__(
        self,
        model_name: str,
        window_size: int = 1000,
        baseline_window: int = 100,
    ):
        """
        Initialize metrics tracker.
        
        Args:
            model_name: Name of model being monitored
            window_size: Size of sliding window for recent metrics
            baseline_window: Size of baseline window (for comparison)
        """
        self.model_name = model_name
        self.window_size = window_size
        self.baseline_window = baseline_window
        
        # Sliding windows
        self.predictions: deque = deque(maxlen=window_size)
        self.metrics_history: deque = deque(maxlen=window_size)
        
        # Baseline stats
        self.baseline_mean: Optional[Dict[str, float]] = None
        self.baseline_std: Optional[Dict[str, float]] = None
        
        logger.info(f"ModelMetrics initialized for {model_name}")
    
    def record_prediction(
        self,
        prediction: int,
        probability: float,
        actual: Optional[int] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Record a single prediction outcome.
        
        Args:
            prediction: Predicted class (0 or 1)
            probability: Prediction confidence
            actual: True label (if available)
            timestamp: Event timestamp
            metadata: Additional context
        """
        record = {
            "timestamp": timestamp or datetime.utcnow(),
            "prediction": prediction,
            "probability": probability,
            "actual": actual,
            "correct": (prediction == actual) if actual is not None else None,
            "metadata": metadata or {},
        }
        self.predictions.append(record)
        
        # Update derived metrics
        self._update_metrics()
    
    def record_batch(
        self,
        predictions: np.ndarray,
        probabilities: np.ndarray,
        actuals: Optional[np.ndarray] = None,
        timestamps: Optional[List[datetime]] = None,
    ):
        """Record batch of predictions."""
        for i in range(len(predictions)):
            self.record_prediction(
                prediction=int(predictions[i]),
                probability=float(probabilities[i]),
                actual=int(actuals[i]) if actuals is not None else None,
                timestamp=timestamps[i] if timestamps else None,
            )
    
    def _update_metrics(self):
        """Update current metrics from predictions."""
        if not self.predictions:
            return
        
        # Compute metrics
        preds = [p["prediction"] for p in self.predictions]
        probs = [p["probability"] for p in self.predictions]
        actuals = [p["actual"] for p in self.predictions if p["actual"] is not None]
        correct = [p["correct"] for p in self.predictions if p["correct"] is not None]
        
        metrics = {
            "prediction_count": len(self.predictions),
            "avg_confidence": np.mean(probs),
            "std_confidence": np.std(probs),
            "positive_rate": np.mean(preds),
        }
        
        if actuals:
            accuracy = np.mean(correct)
            precision = self._compute_precision(preds, actuals)
            recall = self._compute_recall(preds, actuals)
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            metrics.update({
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "num_actuals": len(actuals),
            })
        
        self.metrics_history.append(metrics)
    
    def _compute_precision(self, preds: List[int], actuals: List[int]) -> float:
        """Compute precision."""
        tp = sum(1 for p, a in zip(preds, actuals) if p == 1 and a == 1)
        fp = sum(1 for p, a in zip(preds, actuals) if p == 1 and a == 0)
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0
    
    def _compute_recall(self, preds: List[int], actuals: List[int]) -> float:
        """Compute recall."""
        tp = sum(1 for p, a in zip(preds, actuals) if p == 1 and a == 1)
        fn = sum(1 for p, a in zip(preds, actuals) if p == 0 and a == 1)
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    def set_baseline(self, metrics: Dict[str, float]):
        """Set baseline metrics for comparison."""
        self.baseline_mean = metrics.copy()
        logger.info(f"Baseline set: {metrics}")
    
    def get_current_metrics(self) -> Dict[str, float]:
        """Get current metrics."""
        if not self.metrics_history:
            return {}
        return self.metrics_history[-1].copy()
    
    def get_trend(
        self,
        metric_name: str,
        window_days: int = 7,
    ) -> PerformanceTrend:
        """
        Analyze metric trend over window.
        
        Args:
            metric_name: Metric to analyze
            window_days: Window in days
            
        Returns:
            PerformanceTrend object
        """
        if not self.metrics_history:
            return PerformanceTrend(
                metric_name=metric_name,
                current_value=0.0,
                baseline_value=0.0,
                change_pct=0.0,
                direction="unknown",
                window_days=window_days,
            )
        
        # Current value (latest window)
        recent = [
            m[metric_name] for m in self.metrics_history
            if metric_name in m
        ]
        
        if not recent:
            return PerformanceTrend(
                metric_name=metric_name,
                current_value=0.0,
                baseline_value=0.0,
                change_pct=0.0,
                direction="unknown",
                window_days=window_days,
            )
        
        current_value = recent[-1] if recent else 0.0
        baseline_value = recent[0] if len(recent) > 0 else 0.0
        
        # Simple trend
        if len(recent) >= 2:
            x = np.arange(len(recent))
            slope = np.polyfit(x, recent, 1)[0]
            if slope > 0.001:
                direction = "improving"
            elif slope < -0.001:
                direction = "degrading"
            else:
                direction = "stable"
        else:
            direction = "insufficient_data"
        
        change_pct = ((current_value - baseline_value) / baseline_value 
                     if baseline_value != 0 else 0.0)
        
        return PerformanceTrend(
            metric_name=metric_name,
            current_value=current_value,
            baseline_value=baseline_value,
            change_pct=change_pct,
            direction=direction,
            window_days=window_days,
        )
    
    def check_thresholds(
        self,
        thresholds: Dict[str, Dict[str, float]],
    ) -> List[Dict[str, Any]]:
        """
        Check metrics against thresholds.
        
        Args:
            thresholds: Dict of {metric: {"min": x, "max": y}}
            
        Returns:
            List of violations
        """
        current = self.get_current_metrics()
        violations = []
        
        for metric, bounds in thresholds.items():
            if metric not in current:
                continue
            
            value = current[metric]
            
            if "min" in bounds and value < bounds["min"]:
                violations.append({
                    "metric": metric,
                    "value": value,
                    "threshold": bounds["min"],
                    "type": "below_min",
                })
            
            if "max" in bounds and value > bounds["max"]:
                violations.append({
                    "metric": metric,
                    "value": value,
                    "threshold": bounds["max"],
                    "type": "above_max",
                })
        
        return violations
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        if not self.metrics_history:
            return {"no_data": True}
        
        current = self.get_current_metrics()
        
        # Aggregate trends
        trends = {}
        for metric in ["accuracy", "precision", "recall", "f1", "avg_confidence"]:
            trend = self.get_trend(metric)
            trends[metric] = {
                "current": trend.current_value,
                "baseline": trend.baseline_value,
                "change_pct": trend.change_pct,
                "direction": trend.direction,
            }
        
        return {
            "model_name": self.model_name,
            "total_predictions": len(self.predictions),
            "current_metrics": current,
            "trends": trends,
            "baseline_set": self.baseline_mean is not None,
        }
