"""MLOps package for QuantumTrade model lifecycle management."""

from .registry import ModelRegistry, ModelVersion, ModelInfo
from .pipeline import RetrainingPipeline, RetrainingConfig
from .validator import ModelValidator, ValidationResult, PromotionCriteria
from .drift_detector import DriftDetector, DriftReport
from .experiments.tracker import ExperimentTracker
from .features.store import FeatureStore, FeatureDefinition
from .features.online import OnlineFeatureStore, RedisFeatureBackend
from .features.registry import FeatureRegistry
from .monitoring.metrics import ModelMetrics, MetricSnapshot, PerformanceTrend
from .monitoring.alerts import AlertManager, ModelDriftAlert, AlertConfig
from .serving.predictor import Predictor, PredictionRequest, PredictionResponse
from .serving.versioning import ModelVersionManager, VersionMetadata, DeploymentStage

__all__ = [
    "ModelRegistry",
    "ModelVersion",
    "ModelInfo",
    "RetrainingPipeline",
    "RetrainingConfig",
    "ModelValidator",
    "ValidationResult",
    "PromotionCriteria",
    "DriftDetector",
    "DriftReport",
    "ExperimentTracker",
    "FeatureStore",
    "FeatureDefinition",
    "OnlineFeatureStore",
    "RedisFeatureBackend",
    "FeatureRegistry",
    "ModelMetrics",
    "MetricSnapshot",
    "PerformanceTrend",
    "AlertManager",
    "ModelDriftAlert",
    "AlertConfig",
    "Predictor",
    "PredictionRequest",
    "PredictionResponse",
    "ModelVersionManager",
    "VersionMetadata",
    "DeploymentStage",
]
