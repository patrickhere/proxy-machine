"""Exception hierarchy for The Proxy Machine.

Provides structured error handling with specific exception types
for different failure modes.
"""


class ProxyError(Exception):
    """Base exception for all Proxy Machine errors.

    All custom exceptions inherit from this base class for easy catching.
    """

    pass


class NetworkError(ProxyError):
    """Network-related errors (downloads, API calls, timeouts)."""

    pass


class DatabaseError(ProxyError):
    """Database-related errors (connection, query, schema)."""

    pass


class ValidationError(ProxyError):
    """Validation errors (invalid input, malformed data)."""

    pass


class PDFError(ProxyError):
    """PDF generation errors (layout, rendering, file I/O)."""

    pass


class DeckParsingError(ValidationError):
    """Deck file parsing errors (invalid format, missing cards)."""

    pass


class AssetError(ProxyError):
    """Asset management errors (missing files, corrupted images)."""

    pass


class ConfigurationError(ProxyError):
    """Configuration errors (invalid settings, missing profiles)."""

    pass
