"""
Execution algorithms package.

Provides various order execution algorithms for smart order routing:
- TWAP: Time-Weighted Average Price
- VWAP: Volume-Weighted Average Price
- POV: Percentage of Volume
- Implementation Shortfall: Almgren-Chriss optimal execution
- Iceberg: Hidden order slicing
"""

from .base import OrderAlgorithm
from .twap import TWAPAlgorithm
from .vwap import VWAPAlgorithm
from .pov import POVAlgorithm
from .implementation_shortfall import ImplementationShortfallAlgorithm
from .iceberg import IcebergAlgorithm

__all__ = [
    "OrderAlgorithm",
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "POVAlgorithm",
    "ImplementationShortfallAlgorithm",
    "IcebergAlgorithm",
]
