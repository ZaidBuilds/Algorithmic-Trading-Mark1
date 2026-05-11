"""
Configuration module for the trading system.

This module provides:
- Settings: Pydantic-based configuration management
- Assets: Asset registry and metadata
"""

from .settings import settings, Settings
from .assets import ASSETS_REGISTRY, AssetClass

__all__ = ['settings', 'Settings', 'ASSETS_REGISTRY', 'AssetClass']
