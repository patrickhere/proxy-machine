"""Configuration Schema

Pydantic models for configuration validation and type safety.
Supports YAML/JSON config files and environment variables.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from enum import Enum

try:
    from pydantic import BaseModel, Field, validator, root_validator
    from pydantic import BaseSettings

    PYDANTIC_AVAILABLE = True
except ImportError:
    # Fallback for environments without Pydantic
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    BaseSettings = object
    Field = lambda *args, **kwargs: None
    validator = lambda *args, **kwargs: lambda f: f
    root_validator = lambda *args, **kwargs: lambda f: f


class PaperSize(str, Enum):
    """Supported paper sizes."""

    LETTER = "letter"
    TABLOID = "tabloid"
    A4 = "a4"
    A3 = "a3"


class CardSize(str, Enum):
    """Supported card sizes."""

    STANDARD = "standard"
    MINI = "mini"
    JUMBO = "jumbo"


class Layout(str, Enum):
    """Supported PDF layouts."""

    LAYOUT_3X3 = "3x3"
    LAYOUT_2X4 = "2x4"
    LAYOUT_4X2 = "4x2"
    LAYOUT_1X1 = "1x1"


class DeckSource(BaseModel):
    """Configuration for a deck source."""

    type: str = Field(..., description="Source type (moxfield, local, url)")
    identifier: str = Field(..., description="Deck identifier (URL, file path, etc.)")
    name: Optional[str] = Field(None, description="Display name for the deck")

    @validator("type")
    def validate_type(cls, v):
        """Validate deck source type."""
        allowed_types = ["moxfield", "archidekt", "mtga", "local", "url"]
        if v not in allowed_types:
            raise ValueError(
                f"Invalid deck source type: {v}. Must be one of {allowed_types}"
            )
        return v


class PDFConfig(BaseModel):
    """PDF generation configuration."""

    paper_size: PaperSize = Field(PaperSize.LETTER, description="Paper size for PDF")
    card_size: CardSize = Field(CardSize.STANDARD, description="Card size")
    layout: Layout = Field(Layout.LAYOUT_3X3, description="Cards per page layout")
    crop_borders: bool = Field(False, description="Crop card borders")
    extend_corners: bool = Field(False, description="Extend card corners")
    ppi: int = Field(600, ge=150, le=1200, description="Pixels per inch")
    quality: int = Field(100, ge=50, le=100, description="JPEG quality percentage")


class FetchConfig(BaseModel):
    """Card fetching configuration."""

    languages: List[str] = Field(["en"], description="Preferred languages in order")
    max_workers: int = Field(8, ge=1, le=32, description="Concurrent download threads")
    timeout: int = Field(30, ge=5, le=120, description="Download timeout in seconds")
    max_retries: int = Field(3, ge=1, le=10, description="Max retry attempts")
    skip_existing: bool = Field(True, description="Skip files that already exist")
    dry_run: bool = Field(False, description="Preview mode without downloading")


class DatabaseConfig(BaseModel):
    """Database configuration."""

    path: Optional[Path] = Field(None, description="Custom database path")
    auto_rebuild: bool = Field(False, description="Auto-rebuild on schema changes")
    backup_count: int = Field(5, ge=0, le=50, description="Number of backups to keep")


class NotificationConfig(BaseModel):
    """Notification configuration."""

    enabled: bool = Field(False, description="Enable notifications")
    webhook_url: Optional[str] = Field(None, description="Discord/Slack webhook URL")
    macos_notifications: bool = Field(
        True, description="Use macOS native notifications"
    )


class ProfileConfig(BaseModel):
    """Profile-specific configuration."""

    name: str = Field(..., description="Profile name")
    display_name: Optional[str] = Field(None, description="Display name")
    deck_sources: List[DeckSource] = Field([], description="Configured deck sources")
    pdf: PDFConfig = Field(default_factory=PDFConfig, description="PDF settings")
    fetch: FetchConfig = Field(
        default_factory=FetchConfig, description="Fetch settings"
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate profile name."""
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Profile name must contain only letters, numbers, hyphens, and underscores"
            )
        return v


class ProxyMachineConfig(BaseSettings if PYDANTIC_AVAILABLE else BaseModel):
    """Main configuration for Proxy Machine."""

    # Global settings
    default_profile: str = Field("default", description="Default profile name")
    project_root: Optional[Path] = Field(None, description="Project root directory")

    # Component configurations
    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig, description="Database settings"
    )
    notifications: NotificationConfig = Field(
        default_factory=NotificationConfig, description="Notification settings"
    )

    # Profiles
    profiles: Dict[str, ProfileConfig] = Field({}, description="User profiles")

    # Plugin settings
    plugins: Dict[str, Dict[str, Any]] = Field(
        {}, description="Plugin-specific settings"
    )

    class Config:
        """Pydantic configuration."""

        env_prefix = "PROXY_"
        env_file = ".env"
        case_sensitive = False

        # Field aliases for environment variables
        fields = {
            "default_profile": {"env": "PROXY_PROFILE"},
            "project_root": {"env": "PROXY_ROOT"},
        }

    @root_validator
    def validate_config(cls, values):
        """Validate overall configuration."""
        # Ensure default profile exists
        default_profile = values.get("default_profile", "default")
        profiles = values.get("profiles", {})

        if default_profile not in profiles:
            # Create default profile
            profiles[default_profile] = ProfileConfig(name=default_profile)
            values["profiles"] = profiles

        return values

    def get_profile(self, name: Optional[str] = None) -> ProfileConfig:
        """Get profile configuration by name."""
        profile_name = name or self.default_profile

        if profile_name not in self.profiles:
            raise ValueError(f"Profile '{profile_name}' not found")

        return self.profiles[profile_name]

    def add_profile(self, profile: ProfileConfig) -> None:
        """Add a new profile."""
        self.profiles[profile.name] = profile

    def remove_profile(self, name: str) -> None:
        """Remove a profile."""
        if name == self.default_profile:
            raise ValueError("Cannot remove default profile")

        if name not in self.profiles:
            raise ValueError(f"Profile '{name}' not found")

        del self.profiles[name]


def load_config(config_path: Optional[Path] = None) -> ProxyMachineConfig:
    """Load configuration from file or environment."""
    if not PYDANTIC_AVAILABLE:
        # Return basic config without validation
        return ProxyMachineConfig()

    if config_path and config_path.exists():
        # Load from YAML/JSON file
        import yaml

        with open(config_path, "r") as f:
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                data = yaml.safe_load(f)
            else:
                import json

                data = json.load(f)

        return ProxyMachineConfig(**data)
    else:
        # Load from environment variables
        return ProxyMachineConfig()


def save_config(config: ProxyMachineConfig, config_path: Path) -> None:
    """Save configuration to file."""
    if not PYDANTIC_AVAILABLE:
        raise RuntimeError("Pydantic not available for config serialization")

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Export to dict
    data = config.dict(exclude_unset=True)

    # Save as YAML
    import yaml

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, indent=2)


def create_example_config() -> ProxyMachineConfig:
    """Create an example configuration with common settings."""
    # Create example deck sources
    deck_sources = [
        DeckSource(type="moxfield", identifier="abc123", name="My Commander Deck"),
        DeckSource(
            type="local", identifier="/path/to/deck.txt", name="Local Deck List"
        ),
    ]

    # Create example profile
    profile = ProfileConfig(
        name="patrick",
        display_name="Patrick's Profile",
        deck_sources=deck_sources,
        pdf=PDFConfig(paper_size=PaperSize.LETTER, layout=Layout.LAYOUT_3X3, ppi=600),
        fetch=FetchConfig(languages=["ph", "en"], max_workers=8),
    )

    # Create main config
    config = ProxyMachineConfig(
        default_profile="patrick",
        profiles={"patrick": profile},
        database=DatabaseConfig(auto_rebuild=False, backup_count=5),
        notifications=NotificationConfig(enabled=True, macos_notifications=True),
    )

    return config


# Global config instance (lazy loaded)
_config: Optional[ProxyMachineConfig] = None


def get_config() -> ProxyMachineConfig:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[Path] = None) -> ProxyMachineConfig:
    """Reload configuration from file."""
    global _config
    _config = load_config(config_path)
    return _config
