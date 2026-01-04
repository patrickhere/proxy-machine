"""
Configuration management for The Proxy Machine.

Uses Pydantic for type-safe, validated configuration with environment variable support.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class ProxyMachineSettings(BaseSettings):
    """Main configuration for The Proxy Machine.

    Settings can be overridden via:
    1. Environment variables (prefixed with PM_)
    2. .env file in project root
    3. Programmatic overrides

    Example:
        export PM_MAX_DOWNLOAD_WORKERS=16
        export PM_LOG_LEVEL=DEBUG
    """

    # === Threading & Concurrency ===
    max_download_workers: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Number of concurrent image download threads",
    )
    max_retry_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed downloads",
    )
    retry_base_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Base delay for exponential backoff (seconds)",
    )

    # === Paths ===
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent,
        description="Project root directory",
    )
    bulk_data_dir: Path = Field(
        default=Path("magic-the-gathering/shared/bulk-data"),
        description="Directory for Scryfall bulk data files",
    )
    shared_assets_dir: Path = Field(
        default=Path("magic-the-gathering/shared"),
        description="Shared asset library directory",
    )
    profiles_dir: Path = Field(
        default=Path("magic-the-gathering/proxied-decks"),
        description="User profiles directory",
    )
    cache_dir: Path = Field(
        default=Path(".cache"),
        description="Cache directory for queries and HTTP responses",
    )
    logs_dir: Path = Field(default=Path("logs"), description="Log files directory")

    # === PDF Defaults ===
    default_card_size: Literal["standard", "mini", "jumbo"] = Field(
        default="standard", description="Default card size for PDF generation"
    )
    default_crop_mm: int = Field(
        default=3, ge=0, le=10, description="Default crop margin in millimeters"
    )
    default_ppi: int = Field(
        default=600,
        ge=300,
        le=1200,
        description="Default pixels per inch for image quality",
    )
    default_quality: int = Field(
        default=100, ge=1, le=100, description="Default JPEG quality (1-100)"
    )

    # === Database ===
    db_schema_version: int = Field(
        default=6, description="Expected database schema version"
    )
    db_wal_mode: bool = Field(
        default=True, description="Enable SQLite WAL mode for concurrent access"
    )
    db_cache_size_mb: int = Field(
        default=100, ge=10, le=1000, description="Database query cache size in MB"
    )

    # === Logging ===
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_rotation: str = Field(default="10 MB", description="Log file rotation size")
    log_retention: str = Field(
        default="10 days", description="Log file retention period"
    )
    log_to_file: bool = Field(default=True, description="Enable file logging")

    # === HTTP ===
    http_timeout: int = Field(
        default=30, ge=5, le=300, description="HTTP request timeout in seconds"
    )
    http_cache_size_mb: int = Field(
        default=500,
        ge=0,
        le=5000,
        description="HTTP response cache size in MB (0 to disable)",
    )

    # === API Server (future) ===
    api_enabled: bool = Field(default=False, description="Enable REST API server")
    api_host: str = Field(default="127.0.0.1", description="API server host")
    api_port: int = Field(
        default=5000, ge=1024, le=65535, description="API server port"
    )

    # === Metrics ===
    metrics_enabled: bool = Field(
        default=False, description="Enable Prometheus metrics"
    )
    metrics_port: int = Field(
        default=9090, ge=1024, le=65535, description="Metrics server port"
    )

    @field_validator(
        "bulk_data_dir", "shared_assets_dir", "profiles_dir", mode="before"
    )
    @classmethod
    def resolve_path(cls, v, info):
        """Resolve paths relative to project root."""
        if isinstance(v, str):
            v = Path(v)
        if not v.is_absolute() and info.data.get("project_root"):
            v = info.data["project_root"] / v
        return v

    model_config = {
        "env_prefix": "PM_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Global settings instance
settings = ProxyMachineSettings()


def reload_settings() -> ProxyMachineSettings:
    """Reload settings from environment and .env file.

    Useful for testing or runtime configuration changes.
    """
    global settings
    settings = ProxyMachineSettings()
    return settings
