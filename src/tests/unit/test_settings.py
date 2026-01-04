"""Unit tests for config/settings.py"""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_settings_import():
    """Test that settings module imports successfully."""
    from config.settings import ProxyMachineSettings, settings

    assert settings is not None
    assert isinstance(settings, ProxyMachineSettings)


def test_settings_defaults():
    """Test default settings values."""
    from config.settings import settings

    assert settings.max_download_workers == 8
    assert settings.log_level == "INFO"
    assert settings.default_ppi == 600
    assert settings.db_cache_size_mb == 100
    assert settings.log_to_file is True


def test_settings_paths_exist():
    """Test that default paths are valid Paths."""
    from config.settings import settings

    assert isinstance(settings.project_root, Path)
    assert isinstance(settings.bulk_data_dir, Path)
    assert isinstance(settings.shared_assets_dir, Path)
    assert isinstance(settings.logs_dir, Path)


def test_settings_path_resolution():
    """Test that key paths are resolved to absolute paths."""
    from config.settings import settings

    # Project root and bulk data paths should be absolute
    assert settings.project_root.is_absolute()
    assert settings.bulk_data_dir.is_absolute()
    assert settings.shared_assets_dir.is_absolute()

    # logs_dir and cache_dir can be relative (resolved at runtime)
    assert isinstance(settings.logs_dir, Path)
    assert isinstance(settings.cache_dir, Path)


def test_settings_env_var_override(monkeypatch):
    """Test that environment variables override defaults."""
    # Set environment variable
    monkeypatch.setenv("PM_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PM_MAX_DOWNLOAD_WORKERS", "16")

    # Reload settings to pick up env vars
    from importlib import reload
    import config.settings

    reload(config.settings)
    settings = config.settings.settings

    assert settings.log_level == "DEBUG"
    assert settings.max_download_workers == 16


def test_settings_validation():
    """Test that settings validation works."""
    from config.settings import ProxyMachineSettings

    # Valid settings
    valid_settings = ProxyMachineSettings(
        max_download_workers=10, log_level="WARNING", default_ppi=800
    )
    assert valid_settings.max_download_workers == 10
    assert valid_settings.log_level == "WARNING"
    assert valid_settings.default_ppi == 800

    # Invalid max_download_workers (too high)
    with pytest.raises(Exception):  # Pydantic ValidationError
        ProxyMachineSettings(max_download_workers=100)

    # Invalid log_level
    with pytest.raises(Exception):  # Pydantic ValidationError
        ProxyMachineSettings(log_level="INVALID")


def test_settings_ppi_validation():
    """Test PPI validation."""
    from config.settings import ProxyMachineSettings

    # Valid PPI values
    ProxyMachineSettings(default_ppi=300)
    ProxyMachineSettings(default_ppi=600)
    ProxyMachineSettings(default_ppi=1200)

    # Invalid PPI (too low)
    with pytest.raises(Exception):  # Pydantic ValidationError
        ProxyMachineSettings(default_ppi=100)

    # Invalid PPI (too high)
    with pytest.raises(Exception):  # Pydantic ValidationError
        ProxyMachineSettings(default_ppi=2000)


def test_settings_cache_size_validation():
    """Test cache size validation."""
    from config.settings import ProxyMachineSettings

    # Valid cache sizes
    ProxyMachineSettings(db_cache_size_mb=50)
    ProxyMachineSettings(db_cache_size_mb=500)

    # Invalid cache size (negative)
    with pytest.raises(Exception):  # Pydantic ValidationError
        ProxyMachineSettings(db_cache_size_mb=-10)


def test_settings_repr():
    """Test that settings has a useful repr."""
    from config.settings import settings

    # Settings should have a repr
    repr_str = repr(settings)
    assert "ProxyMachineSettings" in repr_str
    assert "max_download_workers" in repr_str
