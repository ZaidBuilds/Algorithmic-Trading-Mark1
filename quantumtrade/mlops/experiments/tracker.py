"""MLflow experiment tracking wrapper."""

from typing import Dict, Any, Optional, List
from pathlib import Path
import mlflow
from mlflow.tracking import MlflowClient
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class ExperimentTracker:
    """
    Simplified MLflow experiment tracking wrapper.
    
    Provides high-level API for:
    - Experiment creation/management
    - Run tracking
    - Metric logging
    - Parameter logging
    - Artifact management
    - Model registration
    """
    
    def __init__(
        self,
        experiment_name: str = "quantumtrade_models",
        tracking_uri: Optional[str] = None,
    ):
        """
        Initialize experiment tracker.
        
        Args:
            experiment_name: MLflow experiment name
            tracking_uri: MLflow tracking server URI
        """
        self.tracking_uri = tracking_uri or "http://localhost:5000"
        mlflow.set_tracking_uri(self.tracking_uri)
        
        self.client = MlflowClient()
        self.experiment_name = experiment_name
        
        # Get or create experiment
        try:
            experiment = self.client.get_experiment_by_name(experiment_name)
            if experiment is None:
                self.experiment_id = self.client.create_experiment(experiment_name)
                logger.info(f"Created experiment: {experiment_name}")
            else:
                self.experiment_id = experiment.experiment_id
        except Exception as e:
            logger.warning(f"Failed to connect to MLflow: {e}")
            self.experiment_id = "0"
    
    def start_run(
        self,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Start a new tracking run.
        
        Args:
            run_name: Optional run name
            tags: Optional tags
            
        Returns:
            Run ID
        """
        active_run = mlflow.start_run(
            experiment_id=self.experiment_id,
            run_name=run_name,
            tags=tags or {},
        )
        run_id = active_run.info.run_id
        logger.info(f"Started MLflow run: {run_id}")
        return run_id
    
    def end_run(self, status: str = "FINISHED"):
        """End current run."""
        mlflow.end_run(status=status)
        logger.info(f"Ended MLflow run with status: {status}")
    
    def log_params(self, params: Dict[str, Any]):
        """Log parameters."""
        for key, value in params.items():
            # Convert non-string values
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)
            mlflow.log_param(key, str(value))
    
    def log_metrics(self, metrics: Dict[str, float], step: Optional[int] = None):
        """Log metrics."""
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, float(value), step=step)
    
    def log_artifact(self, local_path: str, artifact_path: Optional[str] = None):
        """Log artifact file."""
        mlflow.log_artifact(local_path, artifact_path)
    
    def log_text(self, text: str, artifact_file: str):
        """Log text as artifact."""
        mlflow.log_text(text, artifact_file)
    
    def log_dict(self, dictionary: Dict, artifact_file: str):
        """Log dictionary as JSON artifact."""
        import json
        path = Path(artifact_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(dictionary, f, indent=2, default=str)
        mlflow.log_artifact(str(path))
    
    def log_model(
        self,
        model: Any,
        artifact_path: str = "model",
        registered_model_name: Optional[str] = None,
    ):
        """
        Log and optionally register model.
        
        Args:
            model: Model object (sklearn, pyfunc, etc.)
            artifact_path: MLflow artifact path
            registered_model_name: If provided, register model
        """
        import mlflow.sklearn
        
        if registered_model_name:
            mlflow.sklearn.log_model(
                model,
                artifact_path=artifact_path,
                registered_model_name=registered_model_name,
            )
        else:
            mlflow.sklearn.log_model(model, artifact_path=artifact_path)
    
    def load_model(
        self,
        model_uri: str,
        dst_path: Optional[str] = None,
    ) -> Any:
        """Load model from MLflow."""
        return mlflow.sklearn.load_model(model_uri, dst_path)
    
    def search_runs(
        self,
        filter_string: Optional[str] = None,
        order_by: Optional[List[str]] = None,
        max_results: int = 100,
    ) -> List[Any]:
        """Search runs."""
        return self.client.search_runs(
            experiment_ids=[self.experiment_id],
            filter_string=filter_string,
            order_by=order_by,
            max_results=max_results,
        )
    
    def get_best_run(
        self,
        metric_name: str = "accuracy",
        ascending: bool = False,
    ) -> Optional[Any]:
        """Get best run by metric."""
        order = [f"metrics.{metric_name} {'ASC' if ascending else 'DESC'}"]
        runs = self.search_runs(order_by=order, max_results=1)
        return runs[0] if runs else None
    
    def register_model(
        self,
        model_uri: str,
        name: str,
    ) -> str:
        """Register model from run."""
        model_version = self.client.create_model_version(
            name=name,
            source=model_uri,
            run_id=model_uri.split("/")[1],  # Extract run ID
        )
        return model_version.version
    
    def export_run_info(self, run_id: str, output_path: str):
        """Export run details to JSON."""
        run = self.client.get_run(run_id)
        data = {
            "run_id": run_id,
            "experiment_id": run.info.experiment_id,
            "start_time": datetime.fromtimestamp(run.info.start_time / 1000).isoformat(),
            "end_time": (
                datetime.fromtimestamp(run.info.end_time / 1000).isoformat()
                if run.info.end_time else None
            ),
            "status": run.info.status,
            "metrics": run.data.metrics,
            "params": run.data.params,
            "tags": run.data.tags,
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported run info to {output_path}")
