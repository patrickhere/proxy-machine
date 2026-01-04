"""
Logging configuration for The Proxy Machine.

Uses loguru for structured, performant logging with rotation and retention.
"""

import sys

from loguru import logger

from config.settings import settings


def setup_logging() -> None:
    """Configure logging based on settings.

    Sets up:
    - Console output with color and formatting
    - File output with rotation and retention
    - Log levels from configuration

    Should be called once at application startup.
    """
    # Remove default handler
    logger.remove()

    # Console handler - colorized, formatted
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File handler - with rotation and retention
    if settings.log_to_file:
        log_dir = settings.logs_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_dir / "proxy-machine_{time:YYYY-MM-DD}.log",
            level="DEBUG",  # Always log everything to file
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            compression="gz",
            enqueue=True,  # Async logging for performance
        )

    logger.info("Logging initialized (level={})", settings.log_level)


def get_logger(name: str):
    """Get a logger instance for a specific module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        >>> from core.logging import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing card: {}", card_name)
    """
    return logger.bind(module=name)


# Context managers for structured logging
class log_operation:
    """Context manager for logging operations with timing.

    Example:
        >>> with log_operation("Fetching cards from set", set_code="znr"):
        ...     fetch_cards(set_code="znr")
        # Logs: "Fetching cards from set [set_code=znr] completed in 2.34s"
    """

    def __init__(self, operation: str, **context):
        self.operation = operation
        self.context = context
        self.start_time = None

    def __enter__(self):
        import time

        self.start_time = time.time()
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
        logger.info("{} [{}] starting...", self.operation, context_str)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time

        duration = time.time() - self.start_time
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())

        if exc_type is None:
            logger.info(
                "{} [{}] completed in {:.2f}s", self.operation, context_str, duration
            )
        else:
            logger.error(
                "{} [{}] failed after {:.2f}s: {}",
                self.operation,
                context_str,
                duration,
                exc_val,
            )

        return False  # Don't suppress exceptions


# Convenience function for backwards compatibility
def setup_logger():
    """Legacy function for backwards compatibility."""
    setup_logging()
