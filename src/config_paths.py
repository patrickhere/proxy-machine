"""
Configuration for file paths - centralized for easy Unraid/Docker deployment.

Update these paths when deploying to different environments.
"""

import os

# Base directory - override with environment variable for Docker/Unraid
# Note: __file__ is now in src/, so go up one level to project root
PROJECT_ROOT = os.getenv(
    "PROXY_MACHINE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Shared asset library
SHARED_ROOT = os.getenv(
    "SHARED_ROOT",
    os.path.join(os.path.dirname(PROJECT_ROOT), "magic-the-gathering", "shared"),
)

# Profiles root directory
PROFILES_ROOT = os.getenv(
    "PROFILES_ROOT",
    os.path.join(os.path.dirname(PROJECT_ROOT), "magic-the-gathering", "proxied-decks"),
)

# Database and bulk data
BULK_DATA_DIR = os.getenv(
    "BULK_DATA_DIR", os.path.join(PROJECT_ROOT, "data", "bulk-data")
)
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BULK_DATA_DIR, "bulk-index.db"))

# Output directories
PDF_OUTPUT_DIR = os.getenv("PDF_OUTPUT_DIR", None)  # None = use profile-specific paths
REPORTS_DIR = os.getenv("REPORTS_DIR", os.path.join(SHARED_ROOT, "reports"))

# Web server settings
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")  # Use "0.0.0.0" for Unraid/Docker
WEB_PORT = int(os.getenv("WEB_PORT", "5001"))

# Tailscale settings (for future integration)
TAILSCALE_ENABLED = os.getenv("TAILSCALE_ENABLED", "false").lower() == "true"
TAILSCALE_HOSTNAME = os.getenv("TAILSCALE_HOSTNAME", None)


def get_paths_summary():
    """Return a dictionary of all configured paths."""
    return {
        "PROJECT_ROOT": PROJECT_ROOT,
        "SHARED_ROOT": SHARED_ROOT,
        "PROFILES_ROOT": PROFILES_ROOT,
        "BULK_DATA_DIR": BULK_DATA_DIR,
        "DATABASE_PATH": DATABASE_PATH,
        "PDF_OUTPUT_DIR": PDF_OUTPUT_DIR,
        "REPORTS_DIR": REPORTS_DIR,
        "WEB_HOST": WEB_HOST,
        "WEB_PORT": WEB_PORT,
        "TAILSCALE_ENABLED": TAILSCALE_ENABLED,
        "TAILSCALE_HOSTNAME": TAILSCALE_HOSTNAME,
    }
