"""Optional structured logging configuration with loguru.

This module provides structured logging as an opt-in feature.
By default, the project uses click.echo() for user-friendly output.

Enable structured logging by setting environment variable:
    export ENABLE_STRUCTURED_LOGGING=1

Logs will be written to: logs/{profile}/session_{timestamp}.jsonl
"""

import os
import sys
import uuid
from pathlib import Path
from contextvars import ContextVar
from typing import Optional, Dict, Any

# Check if loguru is available
try:
    from loguru import logger as _logger

    LOGURU_AVAILABLE = True
    logger = _logger
except ImportError:
    LOGURU_AVAILABLE = False
    logger = None  # type: ignore[assignment]


# Context variables for tracking operation context
_operation_id: ContextVar[Optional[str]] = ContextVar("operation_id", default=None)
_deck_id: ContextVar[Optional[str]] = ContextVar("deck_id", default=None)
_job_id: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


def is_enabled() -> bool:
    """Check if structured logging is enabled."""
    return os.getenv("ENABLE_STRUCTURED_LOGGING", "0") == "1" and LOGURU_AVAILABLE


def setup_logging(profile: str = "default") -> None:
    """Setup structured logging if enabled.

    Args:
        profile: User profile name for log directory
    """
    if not is_enabled():
        return

    # Create logs directory
    log_dir = Path("logs") / profile
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure loguru
    logger.remove()  # type: ignore[union-attr]

    # Add console handler (human-readable)
    logger.add(  # type: ignore[union-attr]
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
    )

    # Add JSON file handler (structured)
    logger.add(  # type: ignore[union-attr]
        log_dir / "session_{time:YYYY-MM-DD_HH-mm-ss}.jsonl",
        format="{message}",
        level="DEBUG",
        serialize=True,  # JSON format
        rotation="100 MB",  # Rotate at 100MB
        retention="30 days",  # Keep for 30 days
        compression="gz",  # Compress old logs
    )

    logger.info("Structured logging enabled", profile=profile, log_dir=str(log_dir))  # type: ignore[union-attr]


def get_logger():
    """Get logger instance (loguru or None).

    Returns:
        loguru.logger if available and enabled, None otherwise
    """
    if is_enabled():
        return logger
    return None


# Example usage functions
def log_info(message: str, **kwargs):
    """Log info message if structured logging enabled."""
    if is_enabled():
        context = get_context()
        logger.info(message, **context, **kwargs)  # type: ignore[union-attr]


def log_error(message: str, **kwargs):
    """Log error message if structured logging enabled."""
    if is_enabled():
        context = get_context()
        logger.error(message, **context, **kwargs)  # type: ignore[union-attr]


def log_warning(message: str, **kwargs):
    """Log warning message if structured logging enabled."""
    if is_enabled():
        context = get_context()
        logger.warning(message, **context, **kwargs)  # type: ignore[union-attr]


def log_debug(message: str, **kwargs):
    """Log debug message if structured logging enabled."""
    if is_enabled():
        context = get_context()
        logger.debug(message, **context, **kwargs)  # type: ignore[union-attr]


def get_context() -> Dict[str, Any]:
    """Get current logging context."""
    context = {}
    if _operation_id.get():
        context["operation_id"] = _operation_id.get()
    if _deck_id.get():
        context["deck_id"] = _deck_id.get()
    if _job_id.get():
        context["job_id"] = _job_id.get()
    return context


class LogContext:
    """Context manager for setting logging context (operation_id, deck_id, job_id).

    Usage:
        with LogContext(deck_id="my-deck", operation_id="build-pdf"):
            log_info("Building PDF")  # Will include deck_id and operation_id
    """

    def __init__(
        self,
        operation_id: Optional[str] = None,
        deck_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ):
        self.operation_id = operation_id or str(uuid.uuid4())[:8]
        self.deck_id = deck_id
        self.job_id = job_id
        self.tokens = []

    def __enter__(self):
        self.tokens.append(_operation_id.set(self.operation_id))
        if self.deck_id:
            self.tokens.append(_deck_id.set(self.deck_id))
        if self.job_id:
            self.tokens.append(_job_id.set(self.job_id))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for token in reversed(self.tokens):
            token.var.reset(token)
        return False


# Context manager for operation logging
class LogOperation:
    """Context manager for logging operations with timing."""

    def __init__(self, operation: str, **kwargs):
        self.operation = operation
        self.kwargs = kwargs
        self.start_time = None

    def __enter__(self):
        if is_enabled():
            import time

            self.start_time = time.time()
            logger.info(f"Starting {self.operation}", **self.kwargs)  # type: ignore[union-attr]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if is_enabled():
            import time

            duration = time.time() - self.start_time if self.start_time else 0

            if exc_type is None:
                logger.info(  # type: ignore[union-attr]
                    f"Completed {self.operation}",
                    duration_seconds=duration,
                    **self.kwargs,
                )
            else:
                logger.error(  # type: ignore[union-attr]
                    f"Failed {self.operation}",
                    duration_seconds=duration,
                    error=str(exc_val),
                    **self.kwargs,
                )
        return False  # Don't suppress exceptions


# Usage example
if __name__ == "__main__":
    # Enable for testing
    os.environ["ENABLE_STRUCTURED_LOGGING"] = "1"

    setup_logging("test")

    log_info("Test message", key="value", count=42)

    with LogOperation("test_operation", param1="value1"):
        log_debug("Inside operation")
        # Do work here

    log_warning("Warning message", severity="medium")

    try:
        raise ValueError("Test error")
    except Exception as e:
        log_error("Error occurred", error=str(e))
