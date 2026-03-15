"""
Data module for loading and validating market data.

This module provides:
- DataLoader: Load data from CSV or Yahoo Finance
- DataValidator: Validate data quality
- Data clients for different asset classes
"""

from .loader import DataLoader
from .validator import DataValidator

__all__ = ['DataLoader', 'DataValidator']
