"""Feature registry for tracking feature definitions."""

from typing import Dict, List, Optional
from datetime import datetime
import json

from .store import FeatureDefinition


class FeatureRegistry:
    """
    Central registry for all feature definitions.
    
    Maintains metadata about features including:
    - Computation logic
    - Dependencies
    - Version history
    - Documentation
    """
    
    def __init__(self):
        self._features: Dict[str, FeatureDefinition] = {}
        self._history: List[Dict] = []
    
    def register(self, feature: FeatureDefinition):
        """Register a new feature."""
        if feature.name in self._features:
            # Track version history
            old = self._features[feature.name]
            self._history.append({
                "feature": feature.name,
                "old_version": old.version,
                "new_version": feature.version,
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        self._features[feature.name] = feature
    
    def get(self, name: str) -> Optional[FeatureDefinition]:
        """Get feature definition."""
        return self._features.get(name)
    
    def list(self) -> List[FeatureDefinition]:
        """List all features."""
        return list(self._features.values())
    
    def list_by_tag(self, tag: str) -> List[FeatureDefinition]:
        """List features by tag."""
        return [f for f in self._features.values() if tag in f.tags]
    
    def get_dependencies(self, feature_name: str) -> List[str]:
        """Get feature dependencies (for topological ordering)."""
        feature = self._features.get(feature_name)
        if feature:
            return feature.dependencies.copy()
        return []
    
    def topological_sort(self) -> List[FeatureDefinition]:
        """
        Sort features topologically by dependencies.
        
        Ensures features are computed in correct order.
        """
        visited = set()
        temp = set()
        order = []
        
        def visit(fname: str):
            if fname in temp:
                raise ValueError(f"Circular dependency involving {fname}")
            if fname not in visited:
                temp.add(fname)
                for dep in self.get_dependencies(fname):
                    visit(dep)
                temp.remove(fname)
                visited.add(fname)
                order.append(self._features[fname])
        
        for fname in self._features:
            visit(fname)
        
        return order
    
    def to_json(self) -> str:
        """Export registry to JSON."""
        data = {
            "features": [f.to_dict() for f in self._features.values()],
            "history": self._history,
        }
        return json.dumps(data, indent=2)
    
    def from_json(self, json_str: str):
        """Import registry from JSON."""
        data = json.loads(json_str)
        for fdata in data.get("features", []):
            feature = FeatureDefinition(**fdata)
            self.register(feature)
