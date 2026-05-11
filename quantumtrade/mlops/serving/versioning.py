"""Model version management and A/B testing support."""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DeploymentStage(Enum):
    """Model deployment stages."""
    NONE = "None"
    STAGING = "Staging"
    PRODUCTION = "Production"
    ARCHIVED = "Archived"


@dataclass
class VersionMetadata:
    """Metadata for a model version."""
    version: str
    stage: DeploymentStage
    registered_at: datetime
    run_id: str
    metrics: Dict[str, float]
    params: Dict[str, Any]
    artifact_uri: str
    description: Optional[str] = None
    promoted_at: Optional[datetime] = None


class ModelVersionManager:
    """
    Manages model versions, promotions, and rollbacks.
    
    Features:
    - Stage transitions
    - Version comparison
    - Rollback capability
    - A/B testing traffic splitting (future)
    """
    
    def __init__(self, registry):
        self.registry = registry
        self._ab_test_config: Dict[str, Dict] = {}
    
    def get_current_production(self, model_name: str) -> Optional[VersionMetadata]:
        """Get current production version."""
        mv = self.registry.get_latest_model(model_name, stage="Production")
        if mv:
            return VersionMetadata(
                version=mv.version,
                stage=DeploymentStage.PRODUCTION,
                registered_at=datetime.utcnow(),  # TODO: parse from run
                run_id=mv.run_id,
                metrics=mv.metrics,
                params=mv.params,
                artifact_uri=mv.artifact_uri,
            )
        return None
    
    def promote(
        self,
        model_name: str,
        version: str,
        stage: str,
        description: Optional[str] = None,
    ):
        """Promote model version to stage."""
        self.registry.promote_model(model_name, version, stage)
        logger.info(f"Promoted {model_name} v{version} to {stage}")
    
    def rollback(self, model_name: str, to_version: str):
        """Rollback to previous version."""
        self.registry.rollback_model(model_name, to_version)
    
    def compare(
        self,
        model_name: str,
        v1: str,
        v2: str,
    ) -> Dict[str, Any]:
        """Compare two model versions."""
        mv1 = self.registry.get_model_version(model_name, v1)
        mv2 = self.registry.get_model_version(model_name, v2)
        return self.registry.compare_versions(mv1, mv2)
    
    def configure_ab_test(
        self,
        model_name: str,
        control_version: str,
        treatment_version: str,
        traffic_split: float = 0.5,  # 50% to treatment
    ):
        """
        Configure A/B test between two versions.
        
        Args:
            model_name: Model name
            control_version: Baseline version
            treatment_version: New candidate version
            traffic_split: Fraction of traffic to treatment (0-1)
        """
        self._ab_test_config[model_name] = {
            "control": control_version,
            "treatment": treatment_version,
            "split": traffic_split,
            "enabled": True,
        }
        logger.info(
            f"A/B test configured: {control_version} vs {treatment_version} "
            f"({traffic_split:.1%} treatment)"
        )
    
    def get_version_for_request(
        self,
        model_name: str,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Get version to use for this request (supports A/B testing).
        
        Args:
            model_name: Model name
            request_id: Unique request identifier (for consistent routing)
            
        Returns:
            Version string
        """
        ab_config = self._ab_test_config.get(model_name)
        if not ab_config or not ab_config.get("enabled"):
            # No A/B test, use production
            prod = self.get_current_production(model_name)
            return prod.version if prod else "latest"
        
        # Consistent routing based on request_id hash
        if request_id:
            hash_val = hash(request_id) % 100
            threshold = int(ab_config["split"] * 100)
            if hash_val < threshold:
                return ab_config["treatment"]
            else:
                return ab_config["control"]
        else:
            # Random routing
            import random
            if random.random() < ab_config["split"]:
                return ab_config["treatment"]
            else:
                return ab_config["control"]
    
    def get_ab_test_status(self, model_name: str) -> Optional[Dict]:
        """Get A/B test configuration."""
        return self._ab_test_config.get(model_name)
