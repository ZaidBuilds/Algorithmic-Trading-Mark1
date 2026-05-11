"""Model registry with MLflow integration for versioning and promotion."""

import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import hashlib
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ModelVersion:
    """Represents a registered model version with metadata."""
    
    def __init__(
        self,
        name: str,
        version: str,
        run_id: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        training_data_hash: str,
        training_start: str,
        training_end: str,
        git_commit: str,
        artifact_uri: str,
        stage: str = "None",
    ):
        self.name = name
        self.version = version
        self.run_id = run_id
        self.metrics = metrics
        self.params = params
        self.training_data_hash = training_data_hash
        self.training_start = training_start
        self.training_end = training_end
        self.git_commit = git_commit
        self.artifact_uri = artifact_uri
        self.stage = stage
    
    @classmethod
    def from_mlflow(cls, name: str, version: str, client: MlflowClient):
        """Create ModelVersion from MLflow model version."""
        mv = client.get_model_version(name, version)
        run = client.get_run(mv.run_id)
        
        return cls(
            name=name,
            version=version,
            run_id=mv.run_id,
            metrics=run.data.metrics,
            params=run.data.params,
            training_data_hash=run.data.params.get("training_data_hash", ""),
            training_start=run.data.params.get("training_start", ""),
            training_end=run.data.params.get("training_end", ""),
            git_commit=run.data.params.get("git_commit", ""),
            artifact_uri=mv.source,
            stage=mv.current_stage,
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "run_id": self.run_id,
            "metrics": self.metrics,
            "params": self.params,
            "training_data_hash": self.training_data_hash,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "git_commit": self.git_commit,
            "artifact_uri": self.artifact_uri,
            "stage": self.stage,
        }


class ModelInfo:
    """Summary information for a registered model."""
    
    def __init__(self, name: str, latest_versions: List[ModelVersion], 
                 creation_timestamp: datetime):
        self.name = name
        self.latest_versions = latest_versions
        self.creation_timestamp = creation_timestamp
    
    def get_latest_version(self, stage: str = "production") -> Optional[ModelVersion]:
        """Get latest version in given stage."""
        for v in self.latest_versions:
            if v.stage == stage:
                return v
        return None


class ModelRegistry:
    """
    Model registry using MLflow for versioning, storage, and promotion.
    
    Features:
    - Automatic version numbering
    - Stage transitions (Staging -> Production -> Archived)
    - Metadata tracking (metrics, params, data hash, git commit)
    - Model comparison and rollback
    - Model artifact storage
    """
    
    def __init__(
        self,
        tracking_uri: Optional[str] = None,
        artifact_location: Optional[str] = None,
        experiment_name: str = "quantumtrade_models",
    ):
        """
        Initialize model registry.
        
        Args:
            tracking_uri: MLflow tracking server URI
            artifact_location: S3 or local path for artifacts
            experiment_name: Name of MLflow experiment
        """
        self.tracking_uri = tracking_uri or "http://localhost:5000"
        self.artifact_location = artifact_location or "./mlflow_artifacts"
        self.experiment_name = experiment_name
        
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient()
        
        # Get or create experiment
        try:
            experiment = self.client.get_experiment_by_name(experiment_name)
            if experiment is None:
                experiment_id = self.client.create_experiment(
                    name=experiment_name,
                    artifact_location=self.artifact_location,
                )
                logger.info(f"Created MLflow experiment: {experiment_name}")
            else:
                experiment_id = experiment.experiment_id
        except Exception as e:
            logger.warning(f"MLflow connection failed: {e}")
            experiment_id = "0"
        
        self.experiment_id = experiment_id
        logger.info(f"ModelRegistry initialized (tracking: {self.tracking_uri})")
    
    def _compute_data_hash(self, df: pd.DataFrame) -> str:
        """Compute hash of training data for integrity tracking."""
        return hashlib.sha256(
            pd.util.hash_pandas_object(df).values.tobytes()
        ).hexdigest()[:16]
    
    def _get_git_commit(self) -> str:
        """Get current git commit hash."""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()[:8]
        except Exception:
            return "unknown"
    
    def register_model(
        self,
        model: Any,
        name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        training_data: Optional[pd.DataFrame] = None,
        artifacts: Optional[Dict[str, str]] = None,
        run_name: Optional[str] = None,
    ) -> str:
        """
        Register new model version.
        
        Args:
            model: Trained model object (sklearn, etc.)
            name: Model name (e.g., 'momentum_predictor')
            metrics: Performance metrics (accuracy, precision, recall, etc.)
            params: Hyperparameters
            training_data: DataFrame used for training (for hashing)
            artifacts: Additional artifact paths {name: path}
            run_name: Optional MLflow run name
            
        Returns:
            Model version string
        """
        with mlflow.start_run(run_name=run_name) as run:
            run_id = run.info.run_id
            
            # Log metrics
            mlflow.log_metrics(metrics)
            
            # Log parameters
            mlflow.log_params(params)
            
            # Log training metadata
            training_hash = self._compute_data_hash(training_data) if training_data is not None else "unknown"
            mlflow.log_param("training_data_hash", training_hash)
            mlflow.log_param("training_start", datetime.utcnow().isoformat())
            mlflow.log_param("training_end", datetime.utcnow().isoformat())
            mlflow.log_param("git_commit", self._get_git_commit())
            mlflow.log_param("registered_at", datetime.utcnow().isoformat())
            
            # Log model
            if hasattr(model, '__module__') and 'sklearn' in str(type(model)):
                mlflow.sklearn.log_model(model, "model")
            else:
                mlflow.pyfunc.log_model(
                    python_model=model,
                    artifact_path="model",
                )
            
            # Log additional artifacts
            if artifacts:
                for artifact_name, artifact_path in artifacts.items():
                    if Path(artifact_path).exists():
                        mlflow.log_artifact(artifact_path, artifact_name)
            
            # Register model version
            model_uri = f"runs:/{run_id}/model"
            try:
                mv = self.client.create_model_version(
                    name=name,
                    source=model_uri,
                    run_id=run_id,
                )
                version = mv.version
                logger.info(f"Registered model {name} version {version} (run: {run_id})")
                return version
            except Exception as e:
                logger.error(f"Failed to register model: {e}")
                raise
    
    def promote_model(self, model_name: str, version: str, stage: str):
        """
        Promote model to stage (Staging/Production/Archived).
        
        Args:
            model_name: Name of the model
            version: Version to promote
            stage: Target stage (Staging, Production, Archived)
        """
        valid_stages = ["None", "Staging", "Production", "Archived"]
        if stage not in valid_stages:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {valid_stages}")
        
        try:
            self.client.transition_model_version_stage(
                name=model_name,
                version=version,
                stage=stage,
            )
            logger.info(f"Promoted {model_name} v{version} -> {stage}")
        except Exception as e:
            logger.error(f"Failed to promote model: {e}")
            raise
    
    def get_latest_model(
        self, 
        name: str, 
        stage: str = "production"
    ) -> Optional[ModelVersion]:
        """Get latest model version in given stage."""
        try:
            versions = self.client.search_model_versions(f"name='{name}'")
            stage_versions = [v for v in versions if v.current_stage == stage]
            
            if not stage_versions:
                return None
            
            # Sort by version number (descending) and take latest
            latest = sorted(stage_versions, key=lambda x: int(x.version), reverse=True)[0]
            return ModelVersion.from_mlflow(name, latest.version, self.client)
        except Exception as e:
            logger.error(f"Failed to get latest model: {e}")
            return None
    
    def get_model_version(self, name: str, version: str) -> ModelVersion:
        """Get specific model version."""
        try:
            return ModelVersion.from_mlflow(name, version, self.client)
        except Exception as e:
            logger.error(f"Failed to get model version: {e}")
            raise
    
    def compare_versions(
        self, 
        v1: ModelVersion, 
        v2: ModelVersion
    ) -> Dict[str, Any]:
        """Compare two model versions' performance."""
        comparison = {
            "version_1": v1.version,
            "version_2": v2.version,
            "metric_deltas": {},
            "param_differences": {},
            "winner": None,
        }
        
        # Compare metrics
        all_metrics = set(v1.metrics.keys()) | set(v2.metrics.keys())
        for metric in all_metrics:
            val1 = v1.metrics.get(metric, None)
            val2 = v2.metrics.get(metric, None)
            if val1 is not None and val2 is not None:
                delta = val2 - val1
                comparison["metric_deltas"][metric] = {
                    "v1": val1,
                    "v2": val2,
                    "delta": delta,
                    "pct_change": delta / val1 if val1 != 0 else None,
                }
        
        # Determine winner (higher accuracy/precision/f1 is better)
        primary_metric = "accuracy"
        if primary_metric in comparison["metric_deltas"]:
            delta = comparison["metric_deltas"][primary_metric]["delta"]
            comparison["winner"] = v2.version if delta > 0 else v1.version
        
        return comparison
    
    def rollback_model(self, name: str, to_version: str):
        """
        Rollback model to previous version.
        
        Steps:
        1. Archive current production version
        2. Promote specified version to production
        """
        try:
            # Archive current production
            current = self.get_latest_model(name, stage="Production")
            if current and current.version != to_version:
                self.promote_model(name, current.version, "Archived")
                logger.info(f"Archived previous production version: {current.version}")
            
            # Promote target version to production
            self.promote_model(name, to_version, "Production")
            logger.info(f"Rolled back {name} to version {to_version}")
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            raise
    
    def list_models(self) -> List[ModelInfo]:
        """List all registered models."""
        try:
            # Get all registered models
            experiments = self.client.search_experiments()
            models = []
            
            for exp in experiments:
                # Search model versions for this experiment
                # Note: MLflow API is a bit awkward for this
                pass
            
            # Alternative: List all model versions and group by name
            all_versions = self.client.search_model_versions()
            model_names = set(v.name for v in all_versions)
            
            result = []
            for name in model_names:
                versions = [v for v in all_versions if v.name == name]
                model_versions = [
                    ModelVersion.from_mlflow(name, v.version, self.client)
                    for v in versions
                ]
                
                # Get creation timestamp from first version
                if model_versions:
                    try:
                        run = self.client.get_run(model_versions[0].run_id)
                        timestamp = datetime.fromtimestamp(run.info.start_time / 1000)
                    except:
                        timestamp = datetime.utcnow()
                    
                    result.append(ModelInfo(name, model_versions, timestamp))
            
            return result
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    def list_versions(self, name: str) -> List[ModelVersion]:
        """List all versions for a model."""
        try:
            versions = self.client.search_model_versions(f"name='{name}'")
            return [ModelVersion.from_mlflow(name, v.version, self.client) for v in versions]
        except Exception as e:
            logger.error(f"Failed to list versions: {e}")
            return []
    
    def delete_model(self, name: str):
        """Delete all versions of a model (archive first)."""
        try:
            versions = self.list_versions(name)
            for v in versions:
                if v.stage != "Archived":
                    self.promote_model(name, v.version, "Archived")
            
            self.client.delete_registered_model(name)
            logger.info(f"Deleted model: {name}")
        except Exception as e:
            logger.error(f"Failed to delete model: {e}")
            raise
    
    def load_model(self, name: str, stage: str = "production") -> Any:
        """Load model from MLflow."""
        model_version = self.get_latest_model(name, stage=stage)
        if model_version is None:
            raise ValueError(f"No {stage} model found for {name}")
        
        try:
            model = mlflow.sklearn.load_model(model_version.artifact_uri + "/model")
            logger.info(f"Loaded model {name} version {model_version.version} from {stage}")
            return model
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
