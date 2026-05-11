"""Model validation and promotion gates."""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Model validation outcome."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationResult:
    """Result of model validation."""
    status: ValidationStatus
    checks: Dict[str, bool] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def add_check(self, name: str, passed: bool, message: str = ""):
        """Add a validation check result."""
        self.checks[name] = passed
        if not passed and message:
            self.errors.append(f"{name}: {message}")
    
    def add_warning(self, name: str, message: str):
        """Add a warning."""
        self.warnings.append(f"{name}: {message}")
    
    def is_passing(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "checks": self.checks,
            "metrics": self.metrics,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PromotionCriteria:
    """Criteria for promoting a model to production."""
    min_accuracy: float = 0.55
    min_precision: float = 0.50
    min_recall: float = 0.50
    min_f1: float = 0.50
    max_accuracy_drop: float = 0.02  # Max allowed drop vs baseline
    min_sharpe_ratio: Optional[float] = None
    min_trades: int = 100  # Minimum trades in backtest
    max_drawdown: float = 0.20
    requires_canary_pass: bool = True
    canary_duration_hours: int = 24
    canary_capital_pct: float = 0.01


class ModelValidator:
    """
    Model validation and promotion gates.
    
    Validates models before promotion to production based on:
    - Performance metrics thresholds
    - Comparison with current production
    - Backtest results
    - Stress test results
    """
    
    def __init__(self, criteria: Optional[PromotionCriteria] = None):
        """
        Initialize validator.
        
        Args:
            criteria: Promotion criteria configuration
        """
        self.criteria = criteria or PromotionCriteria()
        self.validation_history: List[ValidationResult] = []
    
    def validate(
        self,
        candidate_metrics: Dict[str, float],
        baseline_metrics: Optional[Dict[str, float]] = None,
        backtest_results: Optional[Dict[str, float]] = None,
        stress_results: Optional[Dict[str, float]] = None,
    ) -> ValidationResult:
        """
        Validate candidate model against criteria.
        
        Args:
            candidate_metrics: New model's metrics
            baseline_metrics: Current production metrics
            backtest_results: Backtest performance metrics
            stress_results: Stress test results
            
        Returns:
            ValidationResult with pass/fail status
        """
        result = ValidationResult(status=ValidationStatus.PASSED)
        
        # 1. Absolute metric thresholds
        self._check_absolute_thresholds(candidate_metrics, result)
        
        # 2. Compare with baseline (if available)
        if baseline_metrics:
            self._check_improvement(candidate_metrics, baseline_metrics, result)
        
        # 3. Backtest validation
        if backtest_results:
            self._check_backtest(backtest_results, result)
        
        # 4. Stress test validation
        if stress_results:
            self._check_stress(stress_results, result)
        
        # Determine final status
        if result.errors:
            result.status = ValidationStatus.FAILED
        elif result.warnings:
            result.status = ValidationStatus.WARNING
        
        self.validation_history.append(result)
        logger.info(f"Validation {result.status.value}: {len(result.errors)} errors, {len(result.warnings)} warnings")
        
        return result
    
    def _check_absolute_thresholds(
        self,
        metrics: Dict[str, float],
        result: ValidationResult,
    ):
        """Check absolute metric thresholds (only for metrics that are provided)."""
        metric_thresholds = {
            "accuracy": self.criteria.min_accuracy,
            "precision": self.criteria.min_precision,
            "recall": self.criteria.min_recall,
            "f1": self.criteria.min_f1,
        }
        
        for name, threshold in metric_thresholds.items():
            if name in metrics:
                value = metrics[name]
                passed = value >= threshold
                message = f"{name}={value:.4f} < {threshold:.4f}" if not passed else ""
                result.add_check(f"min_{name}", passed, message)
            # If metric not provided, skip the check entirely
    
    def _check_improvement(
        self,
        candidate: Dict[str, float],
        baseline: Dict[str, float],
        result: ValidationResult,
    ):
        """Check improvement over baseline."""
        primary_metric = "accuracy"
        candidate_val = candidate.get(primary_metric, 0)
        baseline_val = baseline.get(primary_metric, 0)
        
        if baseline_val > 0:
            delta = candidate_val - baseline_val
            relative_drop = (baseline_val - candidate_val) / baseline_val
            
            # Required improvement threshold
            improvement_ok = delta >= -self.criteria.max_accuracy_drop
            result.add_check(
                "improvement_vs_baseline",
                improvement_ok,
                f"Delta={delta:.4f}, max_drop={self.criteria.max_accuracy_drop:.4f}"
            )
    
    def _check_backtest(
        self,
        backtest: Dict[str, float],
        result: ValidationResult,
    ):
        """Validate backtest results."""
        # Sharpe ratio
        if self.criteria.min_sharpe_ratio is not None:
            sharpe = backtest.get("sharpe_ratio", -999)
            passed = sharpe >= self.criteria.min_sharpe_ratio
            result.add_check(
                "sharpe_ratio",
                passed,
                f"Sharpe={sharpe:.2f} < {self.criteria.min_sharpe_ratio:.2f}"
            )
        
        # Max drawdown
        drawdown = backtest.get("max_drawdown", 0)
        drawdown_ok = drawdown <= self.criteria.max_drawdown
        result.add_check(
            "max_drawdown",
            drawdown_ok,
            f"Drawdown={drawdown:.2%} > {self.criteria.max_drawdown:.2%}"
        )
        
        # Minimum trades
        trades = backtest.get("num_trades", 0)
        trades_ok = trades >= self.criteria.min_trades
        result.add_check(
            "min_trades",
            trades_ok,
            f"Trades={trades} < {self.criteria.min_trades}"
        )
    
    def _check_stress(
        self,
        stress: Dict[str, float],
        result: ValidationResult,
    ):
        """Validate stress test results."""
        # Stress testing should show < X% degradation
        stress_degradation = stress.get("accuracy_degradation_pct", 0)
        stress_ok = stress_degradation <= 20.0  # Max 20% degradation
        result.add_check(
            "stress_test",
            stress_ok,
            f"Degradation={stress_degradation:.1f}% > 20%"
        )
    
    def requires_canary(self) -> bool:
        """Check if canary deployment is required."""
        return self.criteria.requires_canary_pass
    
    def get_canary_config(self) -> Tuple[float, int]:
        """
        Get canary deployment configuration.
        
        Returns:
            (capital_allocation_pct, duration_hours)
        """
        return (
            self.criteria.canary_capital_pct,
            self.criteria.canary_duration_hours,
        )


class CanaryDeployer:
    """
    Manages gradual rollout of new models (canary deployment).
    
    Rollout phases:
    - Phase 1: 1% capital, 24 hours
    - Phase 2: 5% capital, 3 days
    - Phase 3: 25% capital, 1 week
    - Phase 4: 100% capital
    """
    
    PHASES = [
        (0.01, 24),     # Phase 1: 1% for 24h
        (0.05, 72),     # Phase 2: 5% for 3 days
        (0.25, 168),    # Phase 3: 25% for 1 week
        (1.00, float('inf')),  # Phase 4: 100% indefinitely
    ]
    
    def __init__(self, initial_capital: float):
        """
        Initialize canary deployer.
        
        Args:
            initial_capital: Total portfolio capital
        """
        self.initial_capital = initial_capital
        self.current_phase = 0
        self.phase_start_time: Optional[datetime] = None
        self.current_model_version: Optional[str] = None
        self.rollback_triggered = False
    
    def start_deployment(self, model_version: str):
        """Start canary deployment for new model."""
        self.current_model_version = model_version
        self.current_phase = 0
        self.phase_start_time = datetime.utcnow()
        self.rollback_triggered = False
        logger.info(f"Starting canary for model version {model_version}")
    
    def get_allocation(self, current_time: Optional[datetime] = None) -> float:
        """
        Get current capital allocation percentage for new model.
        
        Returns:
            Allocation fraction (0-1). Rest goes to baseline/old model.
        """
        if self.current_phase >= len(self.PHASES):
            return 1.0
        
        if self.phase_start_time is None:
            return 0.0
        
        current_time = current_time or datetime.utcnow()
        elapsed_hours = (current_time - self.phase_start_time).total_seconds() / 3600
        
        # Check if current phase is complete
        allocation, duration = self.PHASES[self.current_phase]
        if elapsed_hours >= duration:
            self.current_phase += 1
            return self.get_allocation(current_time)
        
        return allocation
    
    def should_rollback(
        self,
        current_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        threshold: float = 0.05,
    ) -> bool:
        """
        Check if rollback should be triggered during canary.
        
        Args:
            current_metrics: New model performance
            baseline_metrics: Old model performance
            threshold: Performance degradation threshold (e.g., 5%)
            
        Returns:
            True if rollback needed
        """
        accuracy_current = current_metrics.get("accuracy", 0)
        accuracy_baseline = baseline_metrics.get("accuracy", 0)
        
        if accuracy_baseline > 0:
            degradation = (accuracy_baseline - accuracy_current) / accuracy_baseline
            if degradation > threshold:
                logger.warning(
                    f"Canary degradation detected: {degradation:.2%} > {threshold:.2%}. "
                    f"Rolling back."
                )
                self.rollback_triggered = True
                return True
        
        return False
    
    def _get_phase_index(self, current_time: Optional[datetime] = None) -> int:
        """
        Compute current phase index based on elapsed time.
        
        Returns phase index (0 to len(PHASES)-1).
        """
        if self.phase_start_time is None:
            return 0
        
        current_time = current_time or datetime.utcnow()
        elapsed_hours = (current_time - self.phase_start_time).total_seconds() / 3600
        
        cumulative = 0.0
        for idx, (_, duration) in enumerate(self.PHASES):
            cumulative += duration
            if elapsed_hours < cumulative:
                return idx
        
        # If we've exceeded all finite durations, return last phase
        return len(self.PHASES) - 1
    
    def is_complete(self) -> bool:
        """Check if canary deployment is complete."""
        return self._get_phase_index() == len(self.PHASES) - 1
    
    def get_status(self) -> Dict[str, Any]:
        """Get current deployment status."""
        if self.phase_start_time is None:
            return {"status": "not_started"}
        
        elapsed = (datetime.utcnow() - self.phase_start_time).total_seconds() / 3600
        allocation, duration = self.PHASES[min(self.current_phase, len(self.PHASES)-1)]
        
        return {
            "status": "active" if not self.rollback_triggered else "rollback",
            "phase": self.current_phase + 1,
            "allocation_pct": allocation * 100,
            "elapsed_hours": elapsed,
            "phase_duration_hours": duration,
            "rollback_triggered": self.rollback_triggered,
            "model_version": self.current_model_version,
        }
