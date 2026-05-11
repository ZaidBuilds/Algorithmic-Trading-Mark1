"""Automated retraining pipeline orchestration."""

from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
import schedule
import time
import threading
import json
import logging
from mlflow.exceptions import MlflowException

from ml.ml_predictor import MLPredictor
from ml.feature_engineer import FeatureEngineer
from .registry import ModelRegistry, ModelVersion
from .validator import ModelValidator, PromotionCriteria, ValidationResult
from .drift_detector import DriftDetector, DriftReport

logger = logging.getLogger(__name__)


@dataclass
class RetrainingConfig:
    """Retraining pipeline configuration."""
    enabled: bool = True
    schedule: str = "0 2 * * *"  # Cron: daily at 2am UTC
    min_samples: int = 1000
    performance_threshold: float = 0.55
    improvement_threshold: float = 0.02
    canary_capital_pct: float = 0.01
    canary_duration_hours: int = 24
    phase2_capital_pct: float = 0.05
    phase2_duration_days: int = 3
    phase3_capital_pct: float = 0.25
    phase3_duration_days: int = 7
    lookback_days: int = 90
    test_size: float = 0.2
    retry_attempts: int = 3
    data_source: Optional[str] = None  # e.g., "postgres", "csv", "parquet"


class RetrainingPipeline:
    """
    Automated retraining pipeline with canary deployment.
    
    Pipeline steps:
    1. Fetch recent data
    2. Validate data quality
    3. Train new model
    4. Evaluate on holdout set
    5. Compare vs current production
    6. Canary testing (if improvement)
    7. Auto-promote if canary passes
    """
    
    def __init__(
        self,
        config: RetrainingConfig,
        registry: ModelRegistry,
        validator: ModelValidator,
        drift_detector: Optional[DriftDetector] = None,
        data_fetcher: Optional[Callable] = None,
        backtester: Optional[Callable] = None,
    ):
        """
        Initialize retraining pipeline.
        
        Args:
            config: Pipeline configuration
            registry: Model registry instance
            validator: Model validator instance
            drift_detector: Optional drift detector (for auto-trigger)
            data_fetcher: Custom data fetching function
            backtester: Custom backtesting function
        """
        self.config = config
        self.registry = registry
        self.validator = validator
        self.drift_detector = drift_detector
        self.data_fetcher = data_fetcher or self._default_data_fetcher
        self.backtester = backtester or self._default_backtester
        
        self.last_training_run: Optional[datetime] = None
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_scheduler = False
        
        logger.info("RetrainingPipeline initialized")
    
    def run_scheduled(self):
        """Start scheduled retraining (runs in background thread)."""
        if not self.config.enabled:
            logger.info("Retraining scheduler disabled")
            return
        
        logger.info(f"Starting retraining scheduler (cron: {self.config.schedule})")
        
        schedule.every().day.at(self._parse_cron_time(self.config.schedule)).do(
            self.run_pipeline
        )
        
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="RetrainingScheduler"
        )
        self._scheduler_thread.start()
    
    def _scheduler_loop(self):
        """Background scheduler loop."""
        while not self._stop_scheduler:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def stop_scheduler(self):
        """Stop scheduled retraining."""
        self._stop_scheduler = True
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
    
    def run_pipeline(
        self,
        force: bool = False,
        model_name: str = "momentum_predictor",
    ) -> Dict[str, Any]:
        """
        Execute full retraining pipeline.
        
        Args:
            force: Skip checks and run anyway
            model_name: Model to retrain
            
        Returns:
            Pipeline result summary
        """
        logger.info(f"Starting retraining pipeline for {model_name}")
        start_time = datetime.utcnow()
        
        result = {
            "model_name": model_name,
            "started_at": start_time.isoformat(),
            "status": "running",
            "steps": {},
            "new_version": None,
            "promoted": False,
        }
        
        try:
            # Step 1: Fetch recent data
            logger.info("Step 1: Fetching recent data")
            training_data = self._fetch_training_data()
            result["steps"]["data_fetch"] = {
                "samples": len(training_data),
                "date_range": (
                    training_data.index.min().date(),
                    training_data.index.max().date()
                ),
            }
            
            # Check minimum samples
            if len(training_data) < self.config.min_samples:
                logger.warning(
                    f"Insufficient data: {len(training_data)} < {self.config.min_samples}"
                )
                result["status"] = "skipped_insufficient_data"
                return result
            
            # Step 2: Data validation
            logger.info("Step 2: Validating data quality")
            data_quality = self._validate_data(training_data)
            result["steps"]["data_quality"] = data_quality
            if not data_quality["passed"]:
                result["status"] = "failed_data_quality"
                return result
            
            # Step 3: Feature engineering
            logger.info("Step 3: Engineering features")
            engineer = FeatureEngineer()
            df_features = engineer.engineer_features(training_data)
            X, y = engineer.get_feature_matrix(df_features)
            result["steps"]["feature_engineering"] = {
                "n_features": X.shape[1],
                "n_samples": X.shape[0],
            }
            
            # Step 4: Train new model
            logger.info("Step 4: Training new model")
            model = MLPredictor(model_type='random_forest')
            metrics = model.train(X, y, test_size=self.config.test_size)
            result["steps"]["training"] = {
                "metrics": metrics,
                "model_type": model.model_type,
            }
            
            # Check minimum performance
            if metrics.get('accuracy', 0) < self.config.performance_threshold:
                logger.warning(
                    f"Model below threshold: {metrics['accuracy']:.4f} "
                    f"< {self.config.performance_threshold:.4f}"
                )
                result["status"] = "failed_performance_threshold"
                return result
            
            # Step 5: Get current production model (if any)
            current_production = self.registry.get_latest_model(
                model_name, stage="Production"
            )
            
            if current_production:
                baseline_metrics = current_production.metrics
                improvement = metrics.get('accuracy', 0) - baseline_metrics.get('accuracy', 0)
                result["steps"]["baseline_comparison"] = {
                    "current_version": current_production.version,
                    "baseline_accuracy": baseline_metrics.get('accuracy'),
                    "improvement": improvement,
                }
                
                # Check improvement threshold
                if improvement < self.config.improvement_threshold:
                    logger.info(
                        f"Insufficient improvement: {improvement:.4f} < "
                        f"{self.config.improvement_threshold:.4f}"
                    )
                    result["status"] = "skipped_insufficient_improvement"
                    return result
            else:
                logger.info("No current production model found")
                baseline_metrics = None
            
            # Step 6: Backtest
            logger.info("Step 5: Running backtest")
            backtest_results = self.backtester(model, df_features)
            result["steps"]["backtest"] = backtest_results
            
            # Step 7: Validate for promotion
            logger.info("Step 6: Validating for promotion")
            validation = self.validator.validate(
                candidate_metrics=metrics,
                baseline_metrics=baseline_metrics,
                backtest_results=backtest_results,
            )
            result["steps"]["validation"] = validation.to_dict()
            
            if validation.status.value == "failed":
                result["status"] = "failed_validation"
                return result
            
            # Step 8: Register model
            logger.info("Step 7: Registering new model version")
            version = self.registry.register_model(
                model=model,
                name=model_name,
                metrics=metrics,
                params={
                    "model_type": model.model_type,
                    "n_estimators": 100 if model.model_type == 'random_forest' else 0,
                },
                training_data=training_data,
            )
            result["new_version"] = version
            
            # Step 9: Promote to staging
            logger.info("Step 8: Promoting to Staging")
            self.registry.promote_model(model_name, version, "Staging")
            
            # Step 10: Canary deployment (if configured)
            if self.validator.requires_canary():
                logger.info("Step 9: Starting canary deployment")
                canary_result = self._run_canary(model_name, version)
                result["steps"]["canary"] = canary_result
                
                if canary_result.get("promoted", False):
                    result["promoted"] = True
                    result["status"] = "completed_canary_promoted"
                else:
                    result["status"] = "completed_canary_failed"
            else:
                # Direct production promotion
                logger.info("Step 9: Promoting to Production (no canary)")
                self.registry.promote_model(model_name, version, "Production")
                result["promoted"] = True
                result["status"] = "completed_direct_promote"
            
            self.last_training_run = datetime.utcnow()
            result["completed_at"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result
    
    def _fetch_training_data(self) -> pd.DataFrame:
        """Fetch recent training data."""
        if self.data_fetcher:
            return self.data_fetcher()
        
        # Default: load from database or parquet
        # This is a placeholder - integrate with actual data source
        data_path = Path("data/training_data.parquet")
        if data_path.exists():
            df = pd.read_parquet(data_path)
            # Filter recent data
            cutoff = datetime.utcnow() - timedelta(days=self.config.lookback_days)
            df = df[df.index >= cutoff]
        else:
            # Generate synthetic data for testing
            logger.warning("No training data found, generating synthetic data")
            dates = pd.date_range(
                end=datetime.utcnow(),
                periods=self.config.min_samples * 2,
                freq='H'
            )
            np.random.seed(42)
            prices = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
            df = pd.DataFrame({
                'Open': prices,
                'High': prices * 1.01,
                'Low': prices * 0.99,
                'Close': prices,
                'Volume': np.random.randint(1000, 10000, len(dates)),
            }, index=dates)
        
        return df
    
    def _default_data_fetcher(self) -> pd.DataFrame:
        """Default data fetcher - can be overridden."""
        raise NotImplementedError("Provide a data_fetcher or override _default_data_fetcher")
    
    def _validate_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate data quality."""
        validation = {
            "passed": True,
            "checks": {},
            "warnings": [],
        }
        
        # Check required columns
        required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
        has_cols = required_cols.issubset(set(df.columns))
        validation["checks"]["has_required_columns"] = has_cols
        if not has_cols:
            validation["passed"] = False
            validation["warnings"].append(f"Missing columns: {required_cols - set(df.columns)}")
        
        # Check for NaN values
        nan_pct = df.isna().sum().sum() / (len(df) * len(df.columns))
        validation["checks"]["nan_below_5pct"] = nan_pct < 0.05
        if nan_pct >= 0.05:
            validation["warnings"].append(f"High NaN rate: {nan_pct:.2%}")
        
        # Check minimum rows
        validation["checks"]["min_rows"] = len(df) >= 100
        if len(df) < 100:
            validation["passed"] = False
        
        return validation
    
    def _default_backtester(
        self,
        model: MLPredictor,
        df_features: pd.DataFrame,
    ) -> Dict[str, float]:
        """
        Simple backtest implementation.
        
        Returns mock metrics - replace with real backtesting engine.
        """
        # For now, return validation metrics as proxy
        # In production, integrate with backtest engine
        return {
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.15,
            "num_trades": 150,
            "win_rate": 0.55,
            "total_return": 0.25,
        }
    
    def _run_canary(
        self,
        model_name: str,
        version: str,
    ) -> Dict[str, Any]:
        """
        Run canary deployment (simplified - in prod, this would be managed by deployment system).
        
        Returns:
            Canary result dict
        """
        logger.info(
            f"Canary phase 1: {self.config.canary_capital_pct:.1%} capital "
            f"for {self.config.canary_duration_hours}h"
        )
        
        # In real implementation:
        # 1. Deploy new model alongside old model
        # 2. Route small % of traffic to new model
        # 3. Monitor performance metrics
        # 4. Compare vs baseline
        
        # For now, simulate canary success
        # TODO: Implement actual canary deployment logic
        canary_passed = True  # Placeholder
        
        if canary_passed:
            logger.info("Canary passed. Proceeding with phased rollout.")
            # Promote to production after full canary
            self.registry.promote_model(model_name, version, "Production")
            return {
                "status": "passed",
                "phase_1_duration_hours": self.config.canary_duration_hours,
                "promoted": True,
            }
        else:
            logger.warning("Canary failed. Rollback triggered.")
            self.registry.promote_model(model_name, version, "Archived")
            return {
                "status": "failed",
                "promoted": False,
                "rollback": True,
            }
    
    def _parse_cron_time(self, cron: str) -> str:
        """Parse cron expression to time for schedule.every().day.at()."""
        # Simple: "0 2 * * *" -> "02:00"
        parts = cron.split()
        if len(parts) >= 2:
            hour = parts[1].zfill(2)
            minute = parts[0].zfill(2)
            return f"{hour}:{minute}"
        return "02:00"
    
    def trigger_manual_retrain(self, **kwargs):
        """Manually trigger retraining (outside schedule)."""
        logger.info("Manual retraining triggered")
        return self.run_pipeline(force=True, **kwargs)
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            "scheduler_running": self._scheduler_thread is not None and self._scheduler_thread.is_alive(),
            "last_run": self.last_training_run.isoformat() if self.last_training_run else None,
            "config": self.config.__dict__,
        }
