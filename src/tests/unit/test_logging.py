"""Unit tests for core/logging.py"""

import sys
from pathlib import Path


# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_logging_import():
    """Test that logging module imports successfully."""
    from core.logging import setup_logging, get_logger

    assert setup_logging is not None
    assert get_logger is not None


def test_setup_logging():
    """Test that setup_logging initializes logging."""
    from core.logging import setup_logging

    # Should not raise
    setup_logging()


def test_get_logger():
    """Test that get_logger returns a logger."""
    from core.logging import get_logger

    test_logger = get_logger(__name__)
    assert test_logger is not None


def test_logger_has_loguru_methods():
    """Test that returned logger has Loguru methods."""
    from core.logging import get_logger

    test_logger = get_logger(__name__)

    assert hasattr(test_logger, "debug")
    assert hasattr(test_logger, "info")
    assert hasattr(test_logger, "warning")
    assert hasattr(test_logger, "error")
    assert hasattr(test_logger, "critical")


def test_logging_to_file():
    """Test that logging creates log files."""
    from config.settings import settings
    from core.logging import setup_logging

    setup_logging()

    # Check logs directory exists
    logs_dir = settings.logs_dir
    assert logs_dir.exists()


def test_logging_levels():
    """Test that different log levels work."""
    from core.logging import get_logger

    test_logger = get_logger("test_levels")

    # Should not raise
    test_logger.debug("Debug message")
    test_logger.info("Info message")
    test_logger.warning("Warning message")
    test_logger.error("Error message")


def test_logging_with_context():
    """Test logging with additional context."""
    from core.logging import get_logger

    test_logger = get_logger("test_context")

    # Should not raise
    test_logger.info("Message with context", extra={"key": "value", "count": 42})


def test_logging_exception():
    """Test logging exceptions."""
    from core.logging import get_logger

    test_logger = get_logger("test_exception")

    try:
        raise ValueError("Test exception")
    except ValueError:
        # Should not raise
        test_logger.exception("Caught exception")


def test_multiple_loggers():
    """Test that multiple loggers can be created."""
    from core.logging import get_logger

    logger1 = get_logger("module1")
    logger2 = get_logger("module2")

    assert logger1 is not None
    assert logger2 is not None

    # Both should work
    logger1.info("Message from module1")
    logger2.info("Message from module2")


def test_logging_formats():
    """Test that logging uses proper format."""
    from core.logging import setup_logging

    # Should set up formatting without errors
    setup_logging()

    # Logger should still work after setup
    from core.logging import get_logger

    test_logger = get_logger("test_format")
    test_logger.info("Formatted message")


def test_log_file_rotation():
    """Test that log rotation settings are configured."""
    from config.settings import settings

    # Check that rotation settings exist
    assert hasattr(settings, "log_rotation")
    assert hasattr(settings, "log_retention")

    # Check default values
    assert settings.log_rotation == "10 MB"
    assert settings.log_retention == "10 days"
