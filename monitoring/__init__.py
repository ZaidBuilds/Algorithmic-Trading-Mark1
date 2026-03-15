"""
Monitoring module for logging and dashboard.

This module provides:
- Logging configuration and setup
- Web dashboard server and API endpoints
"""

from .logger import logger, setup_logger

__all__ = ['logger', 'setup_logger']
