"""Centralized helpers for resolving bulk-data paths.

This module defines the primary destination for Scryfall bulk assets
(`proxy-machine/bulk-data`) while still supporting legacy layouts
under `magic-the-gathering/` for a gentler migration path.  A caller can
optionally supply the `PM_BULK_DATA_DIR` environment variable to point at
an alternate location (absolute or relative to the repository root).
"""

from __future__ import annotations

from pathlib import Path
import os
from typing import Iterable

# Repository structure
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROXY_MACHINE_ROOT = _REPO_ROOT / "proxy-machine"

# Path candidates
PRIMARY_BULK_DATA_DIR = _PROXY_MACHINE_ROOT / "bulk-data"
LEGACY_BULK_DATA_DIR = _REPO_ROOT / "magic-the-gathering" / "bulk-data"
SHARED_BULK_DATA_DIR = _REPO_ROOT / "magic-the-gathering" / "shared" / "bulk-data"


def _expand_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return path


def legacy_bulk_locations() -> Iterable[Path]:
    """Return legacy bulk directories (old layouts) in priority order."""
    return (LEGACY_BULK_DATA_DIR, SHARED_BULK_DATA_DIR)


def get_bulk_data_directory(*, prefer_primary: bool = False) -> Path:
    """Resolve the directory that should hold bulk assets."""
    # Check both PM_BULK_DATA_DIR and BULK_DATA_DIR (Docker compatibility)
    env_dir = os.environ.get("PM_BULK_DATA_DIR") or os.environ.get("BULK_DATA_DIR")
    if env_dir:
        return _expand_path(env_dir)

    if prefer_primary:
        return PRIMARY_BULK_DATA_DIR

    if PRIMARY_BULK_DATA_DIR.exists():
        return PRIMARY_BULK_DATA_DIR

    for legacy_dir in legacy_bulk_locations():
        if legacy_dir.exists():
            return legacy_dir

    return PRIMARY_BULK_DATA_DIR


def ensure_bulk_data_directory(*, prefer_primary: bool = False) -> Path:
    """Ensure the bulk data directory exists and return it as a Path."""
    directory = get_bulk_data_directory(prefer_primary=prefer_primary)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def bulk_file_path(filename: str, *, prefer_primary: bool = False) -> Path:
    """Return the path to a file within the resolved bulk directory."""
    return get_bulk_data_directory(prefer_primary=prefer_primary) / filename


def bulk_db_path(*, prefer_primary: bool = False) -> Path:
    """Shortcut for locating the SQLite database file."""
    return bulk_file_path("bulk.db", prefer_primary=prefer_primary)
