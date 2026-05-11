"""
Structured logging module for QuantumTrade.

Provides JSON-formatted logging with correlation IDs (trace_id, span_id)
and support for structured key-value pairs.
"""
import logging
import sys
import json
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional, Dict, Any
import os

# Context variables for correlation IDs
CURRENT_TRACE_ID: ContextVar[str] = ContextVar('trace_id', default='')
CURRENT_SPAN_ID: ContextVar[str] = ContextVar('span_id', default='')

# Default logger configuration from environment
LOG_FORMAT = os.getenv('LOG_FORMAT', 'json').lower()  # json or console
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()


class JSONFormatter(logging.Formatter):
    """Custom JSON log formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log data
        log_data: Dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'component': record.name,
            'message': record.getMessage(),
        }
        
        # Add trace and span IDs from context
        trace_id = CURRENT_TRACE_ID.get()
        if trace_id:
            log_data['trace_id'] = trace_id
            
        span_id = CURRENT_SPAN_ID.get()
        if span_id:
            log_data['span_id'] = span_id
        
        # Add any extra fields passed in the log call
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


class StructuredLogger:
    """Structured logger wrapper."""
    
    def __init__(self, name: str):
        self.name = name
        self._logger = logging.getLogger(name)
        self._configured = False
    
    def _configure(self):
        """Configure the logger if not already done."""
        if self._configured:
            return
        
        # Avoid adding handlers multiple times
        if not self._logger.handlers:
            self._logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
            
            # Choose formatter based on LOG_FORMAT
            if LOG_FORMAT == 'json':
                formatter = JSONFormatter()
            else:
                # Console format for development
                formatter = logging.Formatter(
                    '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
                    datefmt='%H:%M:%S'
                )
            
            # Ensure the console stream supports UTF-8 on Windows
            try:
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)
            
            # File handler with rotation (basic implementation)
            log_file = os.getenv('LOG_FILE', 'logs/quantumtrade.log')
            # Ensure logs directory exists
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            # Simple file handler (for production, consider using RotatingFileHandler)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(JSONFormatter())  # Always JSON for file
            self._logger.addHandler(file_handler)
        
        self._configured = True
    
    def _log(self, level: int, msg: str, **kwargs):
        """Internal log method."""
        self._configure()
        
        # Create a LogRecord with extra fields
        extra = {'extra_fields': kwargs} if kwargs else {}
        self._logger.log(level, msg, extra=extra)
    
    def debug(self, msg: str, **kwargs):
        """Log a debug message."""
        self._log(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        """Log an info message."""
        self._log(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Log a warning message."""
        self._log(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        """Log an error message."""
        self._log(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        """Log a critical message."""
        self._log(logging.CRITICAL, msg, **kwargs)
    
    def exception(self, msg: str, **kwargs):
        """Log an exception with traceback."""
        self._configure()
        extra = {'extra_fields': kwargs} if kwargs else {}
        self._logger.exception(msg, extra=extra)
    
    def span(self, operation_name: str, **context):
        """Context manager for creating a span."""
        return LoggingSpan(self, operation_name, **context)


class LoggingSpan:
    """Context manager for trace/span correlation."""
    
    def __init__(self, logger: StructuredLogger, operation_name: str, **context):
        self.logger = logger
        self.operation_name = operation_name
        self.context = context
        self.trace_id_token = None
        self.span_id_token = None
    
    def __enter__(self):
        # Generate or use provided trace/span IDs
        trace_id = self.context.get('trace_id') or str(uuid.uuid4())
        span_id = self.context.get('span_id') or str(uuid.uuid4())
        
        # Set context variables
        self.trace_id_token = CURRENT_TRACE_ID.set(trace_id)
        self.span_id_token = CURRENT_SPAN_ID.set(span_id)
        
        # Log span start
        self.logger.info(f"Span started: {self.operation_name}", 
                        trace_id=trace_id, span_id=span_id, **self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Log span end
        if exc_type:
            self.logger.error(f"Span failed: {self.operation_name}", 
                            exc_info=(exc_type, exc_val, exc_tb))
        else:
            self.logger.info(f"Span ended: {self.operation_name}")
        
        # Reset context variables
        if self.trace_id_token:
            CURRENT_TRACE_ID.reset(self.trace_id_token)
        if self.span_id_token:
            CURRENT_SPAN_ID.reset(self.span_id_token)


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)


# For backward compatibility, also provide a standard logger interface
def get_standard_logger(name: str) -> logging.Logger:
    """
    Get a standard logger (for compatibility with existing code).
    
    Args:
        name: Logger name
        
    Returns:
        Standard logging.Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Configure if not already done
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        formatter = JSONFormatter() if LOG_FORMAT == 'json' else logging.Formatter(
            '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger