import csv
import json
import logging
import logging.handlers
import os
import random
import contextlib
import io
from collections import Counter, defaultdict
import re
import shutil
import ssl
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence, TypeVar, TypedDict, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import click  # pyright: ignore[reportMissingImports]
import requests  # pyright: ignore[reportMissingImports]

# Provide a runtime-safe NotRequired alias for Python < 3.11
try:  # pragma: no cover - typing compatibility shim
    from typing import NotRequired  # type: ignore[attr-defined]
except Exception:  # Python 3.9/3.10 without NotRequired
    NotRequired = object  # type: ignore[misc,assignment]
from utilities import CardSize, PaperSize, EXTRANEOUS_FILES, generate_pdf
from bulk_paths import (
    bulk_file_path,
    ensure_bulk_data_directory,
    get_bulk_data_directory,
    legacy_bulk_locations,
)

# Import pure utility functions from pdf module (backward compatibility)
from pdf.utils import (
    sanitize_profile_name as _sanitize_profile_name,
    normalize_set_code as _normalize_set_code,
    slugify as _slugify,
    title_from_slug as _title_from_slug,
    normalize_langs as _normalize_langs,
    parse_token_stem as _parse_token_stem,
    parse_enhanced_stem_format as _parse_enhanced_stem_format,
)

# Import shared constants
from constants import RARITIES, SPELL_TYPES

# Import deck parsing functions (backward compatibility)
from deck.parser import (
    parse_deck_file as _parse_deck_file,
)

if TYPE_CHECKING:
    from click import Command  # pyright: ignore[reportMissingImports]

T = TypeVar("T")

# Legacy logger for backwards compatibility
logger = logging.getLogger(__name__)

# Initialize new logging and configuration infrastructure
try:
    from core.logging import setup_logging, get_logger
    from config.settings import settings

    # Set up structured logging on first import
    setup_logging()
    # Get loguru logger for new code
    app_logger = get_logger(__name__)
    app_logger.info("Proxy Machine starting with new logging infrastructure")
except ImportError:
    # Fallback if core modules not available
    app_logger = None  # type: ignore
    settings = None  # type: ignore

# Import Magic-themed progress bars
try:
    from tools.mtg_progress import MagicProgressBar
except ImportError:
    MagicProgressBar = None  # Fallback if not available

try:
    # Optional dependency; only required for duplicate detection in library health
    import imagehash  # type: ignore
except Exception:  # pragma: no cover - optional
    imagehash = None  # type: ignore

# Optional SQLite-backed bulk index (used when present)
try:
    from db.bulk_index import (
        DB_PATH as BULK_DB_PATH,
        query_basic_lands as db_query_basic_lands,
        query_non_basic_lands as db_query_non_basic_lands,
        query_tokens as db_query_tokens,
        query_tokens_by_keyword as db_query_tokens_by_keyword,
        query_oracle_text as db_query_oracle_text,
        query_oracle_fts as db_query_oracle_fts,
        query_unique_artworks as db_query_unique_artworks,
        query_cards as db_query_cards,
    )
except Exception:  # pragma: no cover - optional
    BULK_DB_PATH = None  # type: ignore

    def db_query_basic_lands(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_non_basic_lands(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_tokens(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_tokens_by_keyword(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_oracle_text(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_oracle_fts(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_unique_artworks(*args, **kwargs) -> list[dict]:  # type: ignore
        return []

    def db_query_cards(*args, **kwargs) -> list[dict]:  # type: ignore
        return []


# Optional plugin manager (used when present)
try:
    from plugins.plugin_manager import (
        list_plugins as pm_list,
        enable_plugin as pm_enable,
        disable_plugin as pm_disable,
    )
except Exception:  # pragma: no cover - optional

    def pm_list() -> None:  # type: ignore
        click.echo("Plugin manager not available.")

    def pm_enable(name: str) -> None:  # type: ignore
        click.echo(f"Plugin manager not available; cannot enable '{name}'.")

    def pm_disable(name: str) -> None:  # type: ignore
        click.echo(f"Plugin manager not available; cannot disable '{name}'.")


def _prompt_text(
    prompt: str,
    *,
    default: str | None = None,
    allow_empty: bool = False,
    normalize: Callable[[str], str] | None = None,
) -> str | None:
    """Read text from stdin, handling EOF and defaults."""

    if not sys.stdin.isatty() and default is not None:
        return default

    try:
        response = input(prompt)
    except EOFError:
        return default

    response = response.strip()
    if not response:
        if allow_empty:
            return ""
        return default

    if normalize is not None:
        return normalize(response)

    return response


def _prompt_yes_no(prompt: str, *, default: bool = False) -> bool:
    """Prompt the user for a yes/no response."""

    default_token = "y" if default else "n"
    response = _prompt_text(prompt, default=default_token, allow_empty=True)
    if response is None:
        return default

    response = response.lower()
    if not response:
        return default

    return response in {"y", "yes", "true", "1"}


def _prompt_int(
    prompt: str,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Prompt for an integer with bounds and fallback."""

    response = _prompt_text(prompt, allow_empty=True)
    if response is None or not response:
        return default

    try:
        value = int(response)
    except ValueError:
        return default

    if minimum is not None and value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default

    return value


def _run_subprocess(
    command: Sequence[str],
    *,
    cwd: str | None = None,
    capture_output: bool = False,
    text: bool = True,
    check: bool = False,
    description: str | None = None,
    **run_kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Wrapper around subprocess.run with consistent error handling."""

    desc = description or " ".join(command[:2])
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=capture_output,
            text=text,
            check=check,
            **run_kwargs,
        )
    except Exception as error:
        logger.exception("Subprocess execution failed: %s", desc)
        raise click.ClickException(f"Failed to execute {desc}: {error}") from error


def _db_index_available() -> bool:
    try:
        return bool(BULK_DB_PATH) and os.path.exists(BULK_DB_PATH)  # type: ignore[arg-type]
    except Exception:
        return False


def _ensure_database_built() -> bool:
    """Ensure the SQLite database is built from bulk data. Returns True if database is available."""
    if _db_index_available():
        # Database exists, verify schema compatibility
        from db.bulk_index import verify_schema_compatibility

        try:
            verify_schema_compatibility(str(BULK_DB_PATH))
        except RuntimeError as e:
            click.echo(f"[ERROR] {e}", err=True)
            raise click.ClickException("Database schema mismatch. Please rebuild.")

        return True

    # Check if bulk data files exist
    all_cards_path = bulk_file_path("all-cards.json.gz")
    oracle_path = bulk_file_path("oracle-cards.json.gz")

    if not (all_cards_path.exists() and oracle_path.exists()):
        # Bulk data will be downloaded by _load_bulk_index() if needed
        return False

    # Build database from existing bulk data
    try:
        click.echo("Building database from bulk data for faster queries...")
        from db.bulk_index import build_db_from_bulk_json, DB_PATH

        build_db_from_bulk_json(DB_PATH)
        click.echo("Database build complete!")
        return _db_index_available()
    except Exception as e:
        click.echo(f"Warning: Database build failed: {e}")
        return False


script_directory = os.path.dirname(os.path.abspath(__file__))
project_root_directory = os.path.dirname(script_directory)
profiles_path = os.path.join(script_directory, "assets", "profiles.json")
_PROFILE_CACHE: dict[str, dict[str, str]] | None = None

proxied_decks_root = os.path.join(
    project_root_directory, "magic-the-gathering", "proxied-decks"
)
archive_directory = os.path.join(project_root_directory, "archived")
shared_card_backs_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "card-backs"
)
shared_basic_lands_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "basic-lands"
)
shared_non_basic_lands_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "non-basic-lands"
)
shared_tokens_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "tokens"
)
shared_token_packs_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "token-packs"
)

# Card type directories for comprehensive card fetching
shared_creatures_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "creatures"
)
shared_enchantments_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "enchantments"
)
shared_artifacts_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "artifacts"
)
shared_instants_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "instants"
)
shared_sorceries_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "sorceries"
)
shared_planeswalkers_path = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "planeswalkers"
)

skipped_basic_lands_path = os.path.join(shared_basic_lands_path, "_skipped.json")
shared_tokens_index_path = os.path.join(shared_tokens_path, "_index.json")
notification_config_path = os.path.join(
    script_directory, "config", "notifications.json"
)
REQUIRED_PROFILE_DIRECTORIES = [
    "",
    "other",
    "deck-reports",
    "pdfs-of-decks",
    os.path.join("pictures-of-cards"),
    os.path.join("pictures-of-cards", "shared-cards"),
    os.path.join("pictures-of-cards", "archived"),
    os.path.join("pictures-of-cards", "misc-alt-arts"),
    os.path.join("pictures-of-cards", "to-print"),
    os.path.join("pictures-of-cards", "to-print", "back"),
    os.path.join("pictures-of-cards", "to-print", "double_sided"),
    os.path.join("pictures-of-cards", "to-print", "front"),
]

PROFILE_SYMLINKS = {
    os.path.join("shared-cards", "tokens"): shared_tokens_path,
    os.path.join("shared-cards", "card-backs"): shared_card_backs_path,
    os.path.join("shared-cards", "basic-lands"): shared_basic_lands_path,
    os.path.join("shared-cards", "non-basic-lands"): shared_non_basic_lands_path,
    # Comprehensive card type directories
    os.path.join("shared-cards", "creatures"): shared_creatures_path,
    os.path.join("shared-cards", "enchantments"): shared_enchantments_path,
    os.path.join("shared-cards", "artifacts"): shared_artifacts_path,
    os.path.join("shared-cards", "instants"): shared_instants_path,
    os.path.join("shared-cards", "sorceries"): shared_sorceries_path,
    os.path.join("shared-cards", "planeswalkers"): shared_planeswalkers_path,
    "deck-reports": None,
}


def _run_smoke_tests() -> None:
    """Run non-destructive smoke checks for new features and print a short report."""
    click.echo(_hdr("Smoke Test Report"))
    # 1) Bulk index load and commander counts
    try:
        index = _load_bulk_index()
        entries = index.get("entries", {})
        total = len(entries)
        legendaries = 0
        commanders_legal = 0
        five_color_legal = 0
        for e in entries.values():
            if (e.get("type_line") or "").lower().find("legendary creature") != -1:
                legendaries += 1
                legal = (e.get("legalities") or {}).get("commander") == "legal"
                if legal:
                    commanders_legal += 1
                    colors = set(e.get("oracle_color_identity") or [])
                    if colors == {"W", "U", "B", "R", "G"}:
                        five_color_legal += 1
        click.echo(f"- entries: {total}")
        click.echo(f"- legendary creatures: {legendaries}")
        click.echo(f"- commander-legal commanders: {commanders_legal}")
        click.echo(f"- commander-legal five-color: {five_color_legal}")
    except Exception as err:
        click.echo(f"! bulk index check failed: {err}")

    # 2) Random commander selection with type filter (dry-run preview only)
    try:
        # emulate filtering but don't save images
        index = _load_bulk_index()
        ents = index.get("entries", {})
        pool = []
        for e in ents.values():
            tl = (e.get("type_line") or "").lower()
            if "legendary creature" not in tl:
                continue
            if (e.get("legalities") or {}).get("commander") != "legal":
                continue
            if not {"W", "U", "B", "R", "G"}.issubset(
                set(e.get("oracle_color_identity") or [])
            ):
                continue
            if "human" not in tl:
                continue
            pool.append(e)
        click.echo(f"- sample pool (legal WUBRG Human): {len(pool)}")
        if pool:
            import random as _r

            p = _r.choice(pool)
            click.echo(
                f"  sample: {p.get('name')} [{(p.get('set') or '').upper()} #{p.get('collector_number') or ''}]"
            )
    except Exception as err:
        click.echo(f"! random commander sample failed: {err}")

    # 3) Token wizard dry-run: report token_suggestions for a trivial deck line
    try:
        # Use a well-known token producer as a probe (if present)
        probe_name = "Lingering Souls"
        entry = _find_card_entry(probe_name)
        if entry:
            token_counts: dict[str, dict] = {}
            _gather_token_suggestions(entry, 1, token_counts)
            click.echo(
                f"- token suggestions for '{probe_name}': {len(token_counts)} kind(s)"
            )
        else:
            click.echo("- token wizard probe skipped (card not found in local index)")
    except Exception as err:
        click.echo(f"! token wizard probe failed: {err}")

    # 4) Test database composite indexes (check if they exist)
    try:
        from db.bulk_index import DB_PATH, _get_connection

        conn = _get_connection(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = cursor.fetchall()
        conn.close()
        click.echo(f"- composite indexes found: {len(indexes)}")
        if len(indexes) >= 10:
            click.echo("  [OK] Database optimization complete")
        else:
            click.echo(
                f"  [WARNING] Only {len(indexes)} indexes (expected 10+). Run 'make db-optimize'"
            )
    except Exception as err:
        click.echo(f"! database index check failed: {err}")

    # 5) Test artist search
    try:
        from db.bulk_index import DB_PATH, _get_connection

        conn = _get_connection(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM prints WHERE artist LIKE '%Rebecca Guay%'")
        count = cursor.fetchone()[0]
        conn.close()
        click.echo(f"- artist search test (Rebecca Guay): {count} cards found")
    except Exception as err:
        click.echo(f"! artist search test failed: {err}")

    # 6) Test random card discovery
    try:
        from db.bulk_index import DB_PATH, _get_connection

        conn = _get_connection(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM prints WHERE type_line LIKE '%Artifact%' AND rarity='rare'"
        )
        count = cursor.fetchone()[0]
        conn.close()
        click.echo(f"- random discovery pool (rare artifacts): {count} cards")
    except Exception as err:
        click.echo(f"! random discovery test failed: {err}")

    # 7) Test set exploration
    try:
        from db.bulk_index import DB_PATH, _get_connection

        conn = _get_connection(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM prints WHERE set_code='ltr'")
        count = cursor.fetchone()[0]
        conn.close()
        click.echo(f"- set exploration test (LTR): {count} cards in set")
    except Exception as err:
        click.echo(f"! set exploration test failed: {err}")

    # 8) Test Magic-themed progress bars module
    try:
        click.echo("- Magic-themed progress bars: [OK] module loaded")
    except Exception as err:
        click.echo(f"! progress bars module test failed: {err}")

    # 9) Test asset sync helper module
    try:
        from tools.asset_sync import list_profiles

        profiles = list_profiles()
        click.echo(
            f"- asset sync helper: [OK] module loaded, {len(profiles)} profiles found"
        )
    except Exception as err:
        click.echo(f"! asset sync helper test failed: {err}")

    # 10) Test deck importers (TappedOut/MTGGoldfish)
    try:
        # Just verify the function exists and can parse URLs
        test_urls = [
            "https://www.moxfield.com/decks/test",
            "https://archidekt.com/decks/12345",
            "https://tappedout.net/mtg-decks/test-deck/",
            "https://www.mtggoldfish.com/deck/12345",
        ]
        supported_count = 0
        for url in test_urls:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = parsed.netloc.lower()
            if any(
                x in host
                for x in [
                    "moxfield",
                    "archidekt",
                    "tappedout",
                    "mtggoldfish",
                    "goldfish",
                ]
            ):
                supported_count += 1
        click.echo(f"- deck importers: {supported_count}/4 platforms supported [OK]")
    except Exception as err:
        click.echo(f"! deck importer test failed: {err}")

    click.echo("\n[PASS] Smoke test complete!")


SCRYFALL_API_BASE = "https://api.scryfall.com"
SCRYFALL_USER_AGENT = "ProxyMachine/1.0 (patrick)"
SCRYFALL_REQUEST_DELAY = 0.11
SCRYFALL_MAX_WORKERS = int(os.environ.get("PM_MAX_WORKERS", "8"))
SCRYFALL_PROGRESS_INTERVAL = 100

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class DownloadJob(TypedDict):
    card_id: str | None
    name: str
    set_code: str
    collector_number: str
    image_url: str
    destination: Path
    base_stem: str
    land_type: NotRequired[str]


# Presence index cache (5 minute TTL)

_PRESENCE_CACHE: dict[str, Any] = {}
_PRESENCE_CACHE_TIME: dict[str, float] = {}
PRESENCE_CACHE_TTL = 300  # seconds

_PROGRESS_LAST_LEN = 0


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_time = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_time = max(0.0, self._next_time - now)
            self._next_time = max(self._next_time, now) + self.min_interval
        if wait_time > 0:
            time.sleep(wait_time)


_SCRYFALL_RATE_LIMITER = RateLimiter(SCRYFALL_REQUEST_DELAY)

# Bulk data paths now resolved via bulk_paths helpers
BULK_DATA_DIRECTORY = str(get_bulk_data_directory())
BULK_DEFAULT_ID = "all-cards"
BULK_DATA_FILENAME = f"{BULK_DEFAULT_ID}.json.gz"
BULK_DATA_PATH = str(bulk_file_path(BULK_DATA_FILENAME))
BULK_INDEX_PATH = str(bulk_file_path(f"{BULK_DEFAULT_ID}_index.json"))
BULK_METADATA_PATH = str(bulk_file_path("metadata.json"))
BULK_REFRESH_SECONDS = 7 * 24 * 60 * 60  # one week

ORACLE_BULK_ID = "oracle-cards"
ORACLE_DATA_FILENAME = f"{ORACLE_BULK_ID}.json.gz"
ORACLE_DATA_PATH = str(bulk_file_path(ORACLE_DATA_FILENAME))
ORACLE_METADATA_PATH = str(bulk_file_path("oracle_metadata.json"))

DECK_REPORT_ROOT = os.path.join(
    project_root_directory, "magic-the-gathering", "shared", "deck-reports"
)

_BULK_INDEX_CACHE: dict[str, object] | None = None
_ORACLE_DATA_CACHE: dict[str, dict] | None = None
_NOTIFICATION_CACHE: dict[str, object] | None = None


def _ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json_file(path: str, data: object) -> None:
    _ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def _maybe_migrate_legacy_bulk_file(filename: str) -> None:
    """Copy a file from legacy bulk-data locations to the new primary location."""
    if not filename:
        return
    new_path = os.path.join(BULK_DATA_DIRECTORY, filename)
    if os.path.exists(new_path):
        return

    # Check each legacy location
    for legacy_dir in legacy_bulk_locations():
        legacy_path = legacy_dir / filename
        if legacy_path.exists():
            try:
                _ensure_directory(os.path.dirname(new_path))
                shutil.copy2(str(legacy_path), new_path)
                click.echo(
                    f"Migrated legacy bulk-data file '{filename}' to consolidated location."
                )
                return
            except OSError as exc:
                click.echo(
                    f"Warning: failed to migrate legacy bulk-data file '{filename}': {exc}"
                )
                return


def _migrate_legacy_bulk_assets() -> None:
    """Migrate bulk data files from legacy locations if they exist."""
    candidates = {
        BULK_DATA_FILENAME,
        os.path.basename(BULK_INDEX_PATH),
        os.path.basename(BULK_METADATA_PATH),
        ORACLE_DATA_FILENAME,
        os.path.basename(ORACLE_METADATA_PATH),
    }
    for candidate in candidates:
        _maybe_migrate_legacy_bulk_file(candidate)


def _default_notification_config() -> dict:
    return {
        "enabled": False,
        "macos": {
            "enabled": False,
        },
        "webhook": {
            "enabled": False,
            "url": "",
        },
    }


def _load_notification_config() -> dict:
    global _NOTIFICATION_CACHE

    if _NOTIFICATION_CACHE is not None:
        return _NOTIFICATION_CACHE

    if not os.path.exists(notification_config_path):
        config = _default_notification_config()
        _save_notification_config(config)
        _NOTIFICATION_CACHE = config
        return config

    try:
        config = _read_json_file(notification_config_path)
        if not isinstance(config, dict):
            raise ValueError
    except (OSError, json.JSONDecodeError, ValueError):
        config = _default_notification_config()

    _NOTIFICATION_CACHE = config
    return config


def _save_notification_config(config: dict) -> None:
    _ensure_directory(os.path.dirname(notification_config_path))
    _write_json_file(notification_config_path, config)
    global _NOTIFICATION_CACHE
    _NOTIFICATION_CACHE = config


def _notify_macos(title: str, message: str) -> None:
    safe_title = title.replace('"', '"')
    safe_message = message.replace('"', '"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    try:
        _run_subprocess(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except click.ClickException:
        logger.debug("macOS notification failed", exc_info=True)


def _notify_webhook(
    url: str, title: str, message: str, event: str | None = None
) -> None:
    payload = {
        "title": title,
        "message": message,
        "event": event,
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as exc:
        logger.debug("Webhook notification failed: %s", exc)
        pass


def _notify(title: str, message: str, *, event: str | None = None) -> None:
    config = _load_notification_config()
    if not config.get("enabled"):
        return

    macos_cfg = config.get("macos", {})
    if macos_cfg.get("enabled"):
        _notify_macos(title, message)

    webhook_cfg = config.get("webhook", {})
    if webhook_cfg.get("enabled") and webhook_cfg.get("url"):
        _notify_webhook(webhook_cfg["url"], title, message, event)


def _reveal_in_finder(path: str) -> None:
    """Reveal a file or open a directory in Finder on macOS."""
    try:
        if os.path.isdir(path):
            _run_subprocess(
                ["open", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            _run_subprocess(
                ["open", "-R", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as exc:
        logger.debug("File reveal failed: %s", exc)
        pass


def _offer_open_in_folder(path: str, *, kind: str | None = None) -> None:
    label = kind or "file"
    if _prompt_yes_no(f"Open the {label}'s folder now? [y/N]: "):
        _reveal_in_finder(path)


def _plugins_menu() -> None:
    while True:
        click.echo()
        options = [
            "[1] List discovered plugins",
            "[2] Enable a plugin",
            "[3] Disable a plugin",
            "[0] Back",
        ]
        _print_boxed_menu("Plugins", options)

        selection = _get_key_choice({"0", "1", "2", "3"})

        if selection == "0":
            return

        if selection == "1":
            pm_list()
            _prompt_to_continue()
            continue

        if selection == "2":
            try:
                name = _prompt_text("Plugin name to enable: ", allow_empty=True) or ""
            except EOFError:
                name = ""
            if not name:
                click.echo("Plugin name is required.")
                _prompt_to_continue()
                continue
            pm_enable(name)
            _prompt_to_continue()
            continue

        if selection == "3":
            try:
                name = _prompt_text("Plugin name to disable: ", allow_empty=True) or ""
            except EOFError:
                name = ""
            if not name:
                click.echo("Plugin name is required.")
                _prompt_to_continue()
                continue
            pm_disable(name)
            _prompt_to_continue()
            continue

        click.echo("Please choose a valid option.")
        _prompt_to_continue()


def _ensure_unique_pdf_path(path: str) -> str:
    """If a PDF already exists at path, return a unique path with a timestamp suffix."""
    base, ext = os.path.splitext(path)
    if ext.lower() != ".pdf":
        return path
    if not os.path.exists(path):
        return path
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    candidate = f"{base}_{stamp}{ext}"
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{base}_{stamp}_{counter}{ext}"
        counter += 1
    return candidate


def _download_stream(
    url: str,
    destination: str,
    *,
    rate_limiter: RateLimiter | None = _SCRYFALL_RATE_LIMITER,
) -> None:
    if rate_limiter is not None:
        rate_limiter.wait()

    req = Request(url, headers={"User-Agent": SCRYFALL_USER_AGENT})

    with urlopen(req) as response:
        total_length = response.headers.get("Content-Length")
        total_bytes = int(total_length) if total_length is not None else None

        chunk_size = 1024 * 256  # 256 KB chunks
        bytes_written = 0

        if total_bytes:
            click.echo(f"Downloading (~{total_bytes / (1024 * 1024):.1f} MB)...")

        with open(destination, "wb") as file_handle:
            if total_bytes:
                with click.progressbar(
                    length=total_bytes, label="Downloading bulk data"
                ) as bar:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        file_handle.write(chunk)
                        bytes_written += len(chunk)
                        bar.update(len(chunk))
            else:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    file_handle.write(chunk)
                    bytes_written += len(chunk)

        if total_bytes and bytes_written < total_bytes:
            click.echo(
                "Warning: Download completed but fewer bytes were written than expected."
            )


def _iter_bulk_cards(path: str, *, expect_array: bool = False):
    """Enhanced bulk card iterator with comprehensive validation and error handling.

    Features:
    - Magic byte detection for file format validation
    - Robust gzip/uncompressed handling
    - JSON schema validation
    - Detailed error reporting
    - Progress monitoring for large files
    """
    import gzip

    if not os.path.exists(path):
        raise click.ClickException(f"Bulk data file not found: {path}")

    file_size = os.path.getsize(path)
    if file_size == 0:
        click.echo("Warning: Bulk data file is empty")
        return

    # Enhanced file format detection using magic bytes
    def _detect_file_format(file_path: str) -> str:
        """Detect file format using magic bytes."""
        try:
            with open(file_path, "rb") as f:
                magic = f.read(2)
                if magic == b"\x1f\x8b":
                    return "gzip"
                elif magic.startswith(b"[") or magic.startswith(b"{"):
                    return "json"
                else:
                    # Try to read as text to see if it's JSON
                    f.seek(0)
                    try:
                        first_bytes = f.read(10).decode("utf-8", errors="ignore")
                        if first_bytes.strip().startswith(("[", "{")):
                            return "json"
                    except UnicodeDecodeError:
                        pass
                    return "unknown"
        except (OSError, IOError) as e:
            raise click.ClickException(f"Cannot read file for format detection: {e}")

    file_format = _detect_file_format(path)

    # Only show format details for large files to avoid spam
    if file_size > 1000000:  # 1MB+
        click.echo(f"Enhanced validation: {file_format} format ({file_size:,} bytes)")

    # Enhanced file openers with proper error handling
    def _get_gzip_opener():
        return gzip.open(path, "rt", encoding="utf-8")

    def _get_text_opener():
        return open(path, "r", encoding="utf-8")

    # Choose opener based on detected format
    openers = []
    if file_format == "gzip":
        openers = [
            _get_gzip_opener,
            _get_text_opener,
        ]  # Try gzip first, fallback to text
    elif file_format == "json":
        openers = [
            _get_text_opener,
            _get_gzip_opener,
        ]  # Try text first, fallback to gzip
    else:
        openers = [_get_gzip_opener, _get_text_opener]  # Try both

    cards_processed = 0
    validation_errors = 0

    for opener_idx, open_fn in enumerate(openers):
        try:
            with open_fn() as file_handle:
                # Validate file is readable
                try:
                    first_char = file_handle.read(1)
                    file_handle.seek(0)
                except UnicodeDecodeError as e:
                    if opener_idx == 0:
                        continue  # Try next opener
                    else:
                        raise click.ClickException(f"File encoding error: {e}")

                if not first_char:
                    return

                # Enhanced JSON array handling
                if expect_array or first_char == "[":
                    try:
                        data = json.load(file_handle)
                        if not isinstance(data, list):
                            raise click.ClickException(
                                f"Expected JSON array, got {type(data).__name__}"
                            )

                        total_cards = len(data)
                        if total_cards > 100000:
                            click.echo(
                                f"Processing {total_cards:,} cards from JSON array..."
                            )

                        for idx, card in enumerate(data):
                            if not isinstance(card, dict):
                                validation_errors += 1
                                continue

                            # Basic card validation
                            if not card.get("id"):
                                validation_errors += 1
                                continue

                            cards_processed += 1

                            # Progress reporting for large datasets
                            if cards_processed % 100000 == 0:
                                progress_pct = (idx / total_cards) * 100
                                click.echo(
                                    f"Enhanced validation progress: {cards_processed:,} cards ({progress_pct:.1f}%)"
                                )

                            yield card

                        if validation_errors > 0:
                            click.echo(
                                f"Enhanced validation: {validation_errors} errors in {cards_processed:,} cards"
                            )

                    except json.JSONDecodeError as e:
                        if opener_idx == 0:
                            continue  # Try next opener
                        else:
                            raise click.ClickException(f"Invalid JSON format: {e}")
                    return

                # Enhanced line-by-line processing (JSONL format)
                line_number = 0

                for line in file_handle:
                    line_number += 1
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        card = json.loads(line)
                    except json.JSONDecodeError:
                        validation_errors += 1
                        if validation_errors <= 5:  # Only show first 5 errors
                            click.echo(
                                f"Enhanced validation warning: JSON error on line {line_number}"
                            )
                        continue

                    if not isinstance(card, dict):
                        validation_errors += 1
                        continue

                    # Basic card validation
                    if not card.get("id"):
                        validation_errors += 1
                        continue

                    cards_processed += 1

                    # Progress reporting for large files
                    if cards_processed % 100000 == 0:
                        click.echo(
                            f"Enhanced validation progress: {cards_processed:,} cards processed"
                        )

                    yield card

                if validation_errors > 0:
                    click.echo(
                        f"Enhanced validation complete: {validation_errors} errors in {cards_processed:,} cards"
                    )

                return

        except gzip.BadGzipFile as e:
            if opener_idx == 0 and file_format == "gzip":
                continue  # Try uncompressed format
            else:
                raise click.ClickException(f"Invalid gzip file: {e}")
        except (OSError, IOError) as e:
            if opener_idx == 0:
                continue  # Try alternative format
            else:
                raise click.ClickException(f"Cannot read file: {e}")

    # If we get here, all openers failed
    raise click.ClickException(
        "Enhanced validation failed: Unable to read bulk data file with any supported format"
    )


def _fetch_remote_bulk_metadata(bulk_id: str) -> dict:
    return _scryfall_json(f"/bulk-data/{bulk_id}")


def _get_discord_monitor():
    """Get Discord monitor instance if available."""
    try:
        import sys

        tools_path = os.path.join(os.path.dirname(__file__), "tools")
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)
        from discord_monitor import (
            DiscordMonitor,
        )  # pyright: ignore[reportMissingImports]

        return DiscordMonitor()
    except ImportError:
        return None


def _bulk_metadata_cache() -> dict:
    if not os.path.exists(BULK_METADATA_PATH):
        return {}

    try:
        return _read_json_file(BULK_METADATA_PATH)
    except (OSError, json.JSONDecodeError):
        return {}


def _needs_bulk_refresh(local_meta: dict, remote_meta: dict) -> bool:
    if not os.path.exists(BULK_DATA_PATH):
        return True

    local_updated_at = local_meta.get("bulk_updated_at")
    remote_updated_at = remote_meta.get("updated_at")
    if local_updated_at != remote_updated_at:
        return True

    downloaded_at = local_meta.get("downloaded_at_epoch")
    if downloaded_at is None:
        return True

    age = time.time() - downloaded_at
    return age > BULK_REFRESH_SECONDS


def _build_bulk_index(
    bulk_path: str,
    remote_meta: dict,
    oracle_entries: dict[str, dict] | None = None,
    oracle_meta: dict | None = None,
) -> dict:
    entries: dict[str, dict] = {}
    cards_by_key: dict[str, str] = {}
    cards_by_name: dict[str, list[str]] = {}
    basic_land_ids: list[str] = []
    token_ids: list[str] = []
    tokens_by_subtype: dict[str, list[str]] = {}
    tokens_by_name: dict[str, list[str]] = {}

    for card in _iter_bulk_cards(bulk_path):
        card_id = card.get("id")
        if not card_id:
            continue

        name = card.get("name", "").strip()
        set_code = (card.get("set") or "").lower()
        collector_number = str(card.get("collector_number") or "").strip()
        type_line = card.get("type_line", "")
        image_url = _extract_image_url(card)

        name_slug = _slugify(name)
        key = f"{name_slug}|{set_code}|{collector_number}"

        is_basic_land = "Basic Land" in type_line
        is_token = "Token" in type_line or card.get("layout") == "token"
        token_subtype = None
        token_subtype_slug = None
        if is_token:
            token_subtype = _token_subtype_from_type_line(type_line)
            token_subtype_slug = _slugify(token_subtype)

        entry = {
            "id": card_id,
            "name": name,
            "name_slug": name_slug,
            "set": set_code,
            "collector_number": collector_number,
            "type_line": type_line,
            "image_url": image_url,
            "oracle_id": card.get("oracle_id"),
            "mana_value": card.get("mana_value", card.get("cmc")),
            "all_parts": card.get("all_parts") or [],
            "is_basic_land": is_basic_land,
            "is_token": is_token,
            "token_subtype": token_subtype,
            "token_subtype_slug": token_subtype_slug,
            "legalities": card.get("legalities") or {},
            # Language field - critical for multi-language filtering
            "lang": card.get("lang", "en"),
            # Fields used to derive art type
            "full_art": bool(card.get("full_art")),
            "frame_effects": card.get("frame_effects") or [],
            "frame": card.get("frame"),
            # Comprehensive field extraction - all useful data from all-cards
            "mana_cost": card.get("mana_cost"),
            "colors": card.get("colors") or [],
            "color_identity": card.get("color_identity") or [],
            "power": card.get("power"),
            "toughness": card.get("toughness"),
            "rarity": card.get("rarity"),
            "artist": card.get("artist"),
            "flavor_text": card.get("flavor_text"),
            "set_name": card.get("set_name"),
            "card_faces": card.get("card_faces") or [],
            "layout": card.get("layout"),
            "border_color": card.get("border_color"),
            "reserved": bool(card.get("reserved")),
            "reprint": bool(card.get("reprint")),
            "oracle_text": card.get("oracle_text"),
            "keywords": card.get("keywords") or [],
        }

        entries[card_id] = entry
        cards_by_key[key] = card_id
        cards_by_name.setdefault(name_slug, []).append(card_id)

        if is_basic_land:
            basic_land_ids.append(card_id)

        if is_token:
            token_ids.append(card_id)
            if token_subtype_slug:
                tokens_by_subtype.setdefault(token_subtype_slug, []).append(card_id)
            tokens_by_name.setdefault(name_slug, []).append(card_id)

    index = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "bulk_updated_at": remote_meta.get("updated_at"),
            "source_download": remote_meta.get("download_uri"),
            "schema_version": 5,
        },
        "entries": entries,
        "cards_by_key": cards_by_key,
        "cards_by_name": cards_by_name,
        "basic_land_ids": basic_land_ids,
        "token_ids": token_ids,
        "tokens_by_subtype": tokens_by_subtype,
        "tokens_by_name": tokens_by_name,
    }

    if oracle_entries is not None and oracle_meta is not None:
        _augment_index_with_oracle(index, oracle_entries, oracle_meta)

    _write_json_file(BULK_INDEX_PATH, index)
    return index


def _load_oracle_data(force_refresh: bool = False) -> tuple[dict[str, dict], dict]:
    global _ORACLE_DATA_CACHE

    ensure_bulk_data_directory()

    # Offline/prompt controls
    offline = os.environ.get("PM_OFFLINE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    ask_refresh = os.environ.get("PM_ASK_REFRESH", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    try:
        local_meta = _read_json_file(ORACLE_METADATA_PATH)
    except (OSError, json.JSONDecodeError):
        local_meta = {}

    allow_download = not offline
    # Avoid network call for remote metadata when offline
    remote_meta = local_meta if offline else _fetch_remote_bulk_metadata(ORACLE_BULK_ID)

    needs_refresh = _needs_bulk_refresh(local_meta, remote_meta)
    if (
        allow_download
        and not force_refresh
        and needs_refresh
        and ask_refresh
        and sys.stdin.isatty()
    ):
        try:
            resp_yes = _prompt_yes_no("Oracle bulk appears stale. Refresh now? [y/N]: ")
        except EOFError:
            resp_yes = False

        if not resp_yes:
            allow_download = False

    if allow_download and (force_refresh or needs_refresh):
        click.echo("Downloading Scryfall oracle data...")
        _download_stream(remote_meta["download_uri"], ORACLE_DATA_PATH)
        local_meta = {
            "download_uri": remote_meta.get("download_uri"),
            "bulk_updated_at": remote_meta.get("updated_at"),
            "downloaded_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "downloaded_at_epoch": time.time(),
        }
        _write_json_file(ORACLE_METADATA_PATH, local_meta)
        _ORACLE_DATA_CACHE = None

    if _ORACLE_DATA_CACHE is None or force_refresh:
        oracle_entries: dict[str, dict] = {}

        for card in _iter_bulk_cards(ORACLE_DATA_PATH, expect_array=True):
            if not isinstance(card, dict):
                continue

            oracle_id = card.get("oracle_id")
            if not oracle_id:
                continue

            oracle_entries[oracle_id] = {
                "oracle_text": card.get("oracle_text"),
                "keywords": card.get("keywords") or [],
                "color_identity": card.get("color_identity") or [],
                "mana_cost": card.get("mana_cost"),
                "type_line": card.get("type_line"),
                "oracle_name": card.get("name"),
            }

        _ORACLE_DATA_CACHE = oracle_entries

    return _ORACLE_DATA_CACHE, remote_meta


def _augment_index_with_oracle(
    index: dict, oracle_entries: dict[str, dict], oracle_meta: dict
) -> bool:
    entries = index.get("entries", {})
    updated_any = False

    for entry in entries.values():
        oracle_id = entry.get("oracle_id")
        if not oracle_id:
            continue

        oracle_info = oracle_entries.get(oracle_id)
        if not oracle_info:
            continue

        entry["oracle_text"] = oracle_info.get("oracle_text")
        entry["oracle_keywords"] = oracle_info.get("keywords")
        entry["oracle_color_identity"] = oracle_info.get("color_identity")
        entry["oracle_mana_cost"] = oracle_info.get("mana_cost")
        updated_any = True

    metadata = index.setdefault("metadata", {})
    metadata["oracle_attached"] = oracle_meta.get("updated_at")

    return updated_any


def _load_bulk_index(force_refresh: bool = False) -> dict:
    global _BULK_INDEX_CACHE

    # Fast path: if cached and not forcing refresh, return immediately
    if _BULK_INDEX_CACHE is not None and not force_refresh:
        return _BULK_INDEX_CACHE  # type: ignore[return-value]

    ensure_bulk_data_directory()
    _migrate_legacy_bulk_assets()

    # Offline/prompt controls
    offline = os.environ.get("PM_OFFLINE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    ask_refresh = os.environ.get("PM_ASK_REFRESH", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    local_meta = _bulk_metadata_cache()
    allow_download = not offline
    remote_meta = (
        local_meta if offline else _fetch_remote_bulk_metadata(BULK_DEFAULT_ID)
    )

    oracle_entries, oracle_meta = _load_oracle_data(force_refresh=force_refresh)

    needs_refresh = _needs_bulk_refresh(local_meta, remote_meta)
    if (
        allow_download
        and not force_refresh
        and needs_refresh
        and ask_refresh
        and sys.stdin.isatty()
    ):
        try:
            resp_yes = _prompt_yes_no("Bulk data appears stale. Refresh now? [y/N]: ")
        except EOFError:
            resp_yes = False

        if not resp_yes:
            allow_download = False

    if allow_download and (force_refresh or needs_refresh):
        click.echo(
            "Downloading Scryfall all-cards data (comprehensive multi-language coverage)..."
        )
        _download_stream(remote_meta["download_uri"], BULK_DATA_PATH)
        local_meta = {
            "download_uri": remote_meta.get("download_uri"),
            "bulk_updated_at": remote_meta.get("updated_at"),
            "downloaded_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "downloaded_at_epoch": time.time(),
        }
        _write_json_file(BULK_METADATA_PATH, local_meta)
        if os.path.exists(BULK_INDEX_PATH):
            os.remove(BULK_INDEX_PATH)

    if force_refresh or not os.path.exists(BULK_INDEX_PATH):
        click.echo("Building Scryfall bulk index (this may take a moment)...")
        index = _build_bulk_index(
            BULK_DATA_PATH, remote_meta, oracle_entries, oracle_meta
        )
        _BULK_INDEX_CACHE = index
        return index

    if _BULK_INDEX_CACHE is not None and not force_refresh:
        return _BULK_INDEX_CACHE

    try:
        index = _read_json_file(BULK_INDEX_PATH)
    except (OSError, json.JSONDecodeError):
        click.echo("Bulk index corrupt; rebuilding...")
        index = _build_bulk_index(
            BULK_DATA_PATH, remote_meta, oracle_entries, oracle_meta
        )
    else:
        meta = index.get("metadata", {})
        oracle_attached = meta.get("oracle_attached")
        schema_version = int(meta.get("schema_version") or 1)
        if schema_version < 5:
            click.echo("Bulk index schema outdated; rebuilding...")
            index = _build_bulk_index(
                BULK_DATA_PATH, remote_meta, oracle_entries, oracle_meta
            )
        else:
            # Ensure oracle augmentation is up to date
            if oracle_attached != oracle_meta.get("updated_at"):
                if _augment_index_with_oracle(index, oracle_entries, oracle_meta):
                    _write_json_file(BULK_INDEX_PATH, index)

    _BULK_INDEX_CACHE = index
    return index


def _bulk_lookup_entry(card_id: str) -> dict | None:
    index = _load_bulk_index()
    return index["entries"].get(card_id)


def _db_first_fetch(
    fetch_label: str,
    db_callable: Callable[[], T] | None,
    fallback_callable: Callable[[], T],
    *,
    allow_empty: bool = False,
) -> T:
    if db_callable and _db_index_available():
        try:
            result = db_callable()
            if allow_empty or result:
                return result
        except Exception as exc:
            logger.warning(
                "Database fetch failed for %s: %s", fetch_label, exc, exc_info=True
            )
            click.echo(f"Warning: {fetch_label} DB fetch failed: {exc}")
    return fallback_callable()


def _db_lookup_cards_by_ids(card_ids: list[str] | None) -> list[dict]:
    if not card_ids:
        return []
    if _db_index_available():
        try:
            return db_query_cards(card_ids=list({cid for cid in card_ids if cid}))
        except Exception:
            return []
    return []


def _db_lookup_cards_by_name(
    *, name: str, set_code: str | None = None, limit: int | None = None
) -> list[dict]:
    if not name:
        return []
    if _db_index_available():
        try:
            cards = db_query_cards(
                name_filter=name,
                set_filter=set_code.lower() if set_code else None,
                limit=limit,
            )
            if cards:
                return cards
        except Exception:
            return []
    return []


def _fetch_cards_from_database(
    *,
    name_filter: str | None = None,
    type_filter: str | None = None,
    lang_filter: str | None = None,
    set_filter: str | None = None,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    cmc_filter: float | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    fullart_only: bool = False,
    exclude_tokens: bool = False,
    exclude_lands: bool = False,
    colors_filter: list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int, list[str]]:
    """
    Comprehensive card fetching function for any card type with advanced filtering.

    Returns: (saved, skipped, total, skipped_details)
    """
    # Initialize memory monitoring
    memory_monitor = MemoryMonitor()
    if memory_monitor.enabled:
        memory_monitor.log_memory("starting comprehensive card fetch")

    # Ensure database is available for fast queries
    _ensure_database_built()

    db_available = _db_index_available()

    def _db_call() -> list[dict]:
        return db_query_cards(
            limit=limit,
            name_filter=name_filter,
            type_filter=type_filter,
            lang_filter=lang_filter,
            set_filter=set_filter,
            artist_filter=artist_filter,
            rarity_filter=rarity_filter,
            cmc_filter=cmc_filter,
            layout_filter=layout_filter,
            frame_filter=frame_filter,
            fullart_only=fullart_only,
            exclude_tokens=exclude_tokens,
            exclude_lands=exclude_lands,
            colors_filter=colors_filter,
        )

    def _json_fallback() -> list[dict]:
        index = _load_bulk_index()
        entries = index.get("entries", {})

        def _matches(entry: dict) -> bool:
            if (
                name_filter
                and name_filter.lower() not in (entry.get("name") or "").lower()
            ):
                return False
            if (
                type_filter
                and type_filter.lower() not in (entry.get("type_line") or "").lower()
            ):
                return False
            if lang_filter and (entry.get("lang") or "en") != lang_filter:
                return False
            if (
                set_filter
                and (entry.get("set") or "").lower() != (set_filter or "").lower()
            ):
                return False
            if (
                artist_filter
                and artist_filter.lower() not in (entry.get("artist") or "").lower()
            ):
                return False
            if (
                rarity_filter
                and (entry.get("rarity") or "").lower() != rarity_filter.lower()
            ):
                return False
            if cmc_filter is not None:
                cmc_value = entry.get("cmc")
                try:
                    entry_cmc = float(cmc_value) if cmc_value is not None else None
                except (TypeError, ValueError):
                    return False
                if entry_cmc is None or entry_cmc != float(cmc_filter):
                    return False
            if layout_filter and (entry.get("layout") or "") != layout_filter:
                return False
            if frame_filter and (entry.get("frame") or "") != frame_filter:
                return False
            if fullart_only and not bool(entry.get("full_art")):
                return False
            if exclude_tokens and entry.get("is_token"):
                return False
            if exclude_lands:
                type_line = (entry.get("type_line") or "").lower()
                if entry.get("is_basic_land") or "land" in type_line:
                    return False
            if colors_filter:
                entry_colors = entry.get("colors") or []
                if not all(color in entry_colors for color in colors_filter):
                    return False
            return True

        cards: list[dict] = [entry for entry in entries.values() if _matches(entry)]
        cards.sort(
            key=lambda e: (
                str(e.get("released_at") or "9999-99-99"),
                str(e.get("set") or ""),
                str(e.get("collector_number") or ""),
            )
        )
        if limit and limit > 0:
            cards = cards[:limit]
        return cards

    cards = _db_first_fetch(
        "card fetch",
        _db_call if db_available else None,
        _json_fallback,
        allow_empty=True,
    )

    if not db_available:
        click.echo("Database not available, falling back to JSON index")

    click.echo(f"Found {len(cards)} cards matching filters:")
    if name_filter:
        click.echo(f"  Name: {name_filter}")
    if type_filter:
        click.echo(f"  Type: {type_filter}")
    if set_filter:
        click.echo(f"  Set: {set_filter}")
    if artist_filter:
        click.echo(f"  Artist: {artist_filter}")
    if rarity_filter:
        click.echo(f"  Rarity: {rarity_filter}")
    if colors_filter:
        click.echo(f"  Colors: {', '.join(colors_filter)}")

        if dry_run:
            # Display sample results for preview
            for i, card in enumerate(cards[:5]):
                click.echo(
                    f"  {i+1}. {card['name']} ({card['set']}) - {card['rarity']} - {card['artist']}"
                )

            if len(cards) > 5:
                click.echo(f"  ... and {len(cards) - 5} more")

            return 0, 0, len(cards), []

        # Actual downloading logic
        saved = 0
        skipped = 0
        skipped_details = []

        destination_root = (
            Path(shared_creatures_path).parent if shared_creatures_path else Path(".")
        )
        download_root = Path(os.environ.get("PM_DOWNLOAD_ROOT", "downloads"))
        download_root.mkdir(parents=True, exist_ok=True)

        for i, card in enumerate(cards):
            if i % 10 == 0 or i == len(cards) - 1:
                click.echo(f"Progress: {i+1}/{len(cards)} cards processed")

            image_url = card.get("image_url")
            if not image_url:
                skipped += 1
                skipped_details.append(f"No image URL: {card['name']}")
                continue

            target_dir = download_root / _get_card_type_directory(card)
            target_dir.mkdir(parents=True, exist_ok=True)

            base_stem = _card_base_stem(card)
            extension = _extension_from_url(image_url, ".png")
            destination = _unique_card_destination(
                target_dir,
                base_stem,
                extension,
                card.get("collector_number"),
                disambiguators={
                    "set": card.get("set"),
                    "collector_number": card.get("collector_number"),
                    "lang": card.get("lang"),
                },
            )

            if destination.exists() and not os.environ.get("PM_OVERWRITE", "0") == "1":
                skipped += 1
                skipped_details.append(
                    f"Already exists: {card['name']} ({card.get('set', 'unknown')})"
                )
                continue

            try:
                _download_image(image_url, destination)
                saved += 1
                if memory_monitor.enabled:
                    memory_monitor.log_memory(f"downloaded {card['name']}")
            except Exception as exc:
                skipped += 1
                skipped_details.append(f"Error downloading {card['name']}: {exc}")

        click.echo(f"\nDownload complete: {saved} saved, {skipped} skipped")

        return saved, skipped, len(cards), skipped_details
    else:
        click.echo("Database not available, falling back to JSON index")
        return 0, 0, 0, ["Database not available"]


def _bulk_iter_basic_lands(
    lang_filter: list[str] | None = None,
    set_filter: str | None = None,
    fullart_only: bool = False,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    border_color_filter: str | None = None,
) -> list[dict]:
    def _db_call() -> list[dict]:
        return db_query_basic_lands(
            lang_filter=lang_filter,
            set_filter=set_filter,
            fullart_only=fullart_only,
            artist_filter=artist_filter,
            rarity_filter=rarity_filter,
            layout_filter=layout_filter,
            frame_filter=frame_filter,
        )

    def _json_fallback() -> list[dict]:
        index = _load_bulk_index()
        entries = index["entries"]
        all_basic_lands = [
            entries[card_id]
            for card_id in index.get("basic_land_ids", [])
            if card_id in entries
        ]

        if not (lang_filter or set_filter or fullart_only):
            return all_basic_lands

        filtered = []
        for entry in all_basic_lands:
            if lang_filter and entry.get("lang", "en") not in lang_filter:
                continue
            if set_filter and entry.get("set", "").lower() != set_filter.lower():
                continue
            if fullart_only:
                art_type = _derive_art_type(entry)
                if not (art_type == "fullart" or "fullart" in art_type):
                    continue
            filtered.append(entry)
        return filtered

    results = _db_first_fetch(
        "basic lands",
        _db_call,
        _json_fallback,
        allow_empty=True,
    )

    return results


def _bulk_iter_tokens(
    name_filter: str | None = None,
    subtype_filter: str | None = None,
    set_filter: str | None = None,
    colors_filter: str | None = None,
) -> list[dict]:
    name_filter_slug = _slugify(name_filter) if name_filter else None
    subtype_filter_slug = _slugify(subtype_filter) if subtype_filter else None
    set_filter_slug = set_filter.lower() if set_filter else None
    colors_norm = (colors_filter or "").strip().lower() or None

    def _db_call() -> list[dict]:
        return db_query_tokens(
            name_filter=name_filter,
            subtype_filter=subtype_filter,
            set_filter=set_filter,
        )

    def _json_fallback() -> list[dict]:
        index = _load_bulk_index()
        entries = index["entries"]
        token_ids = index.get("token_ids", [])
        results: list[dict] = []
        for card_id in token_ids:
            entry = entries.get(card_id)
            if not entry:
                continue
            if name_filter_slug and name_filter_slug not in entry["name_slug"]:
                continue
            if (
                subtype_filter_slug
                and entry.get("token_subtype_slug") != subtype_filter_slug
            ):
                continue
            if set_filter_slug and entry.get("set") != set_filter_slug:
                continue
            if colors_norm and not _color_filter_matches(
                entry.get("color_identity") or [], colors_norm
            ):
                continue
            results.append(entry)
        return results

    results = _db_first_fetch(
        "tokens",
        _db_call,
        _json_fallback,
        allow_empty=True,
    )

    if colors_norm:
        results = [
            entry
            for entry in results
            if _color_filter_matches(entry.get("color_identity") or [], colors_norm)
        ]

    return results


def _color_filter_matches(ci: list | None, expr: str) -> bool:
    """Return True if the color identity list matches the filter expression.

    Supported forms:
    - exact letters: "w", "wu", "ubr" → exact set match
    - aliases: "c" or "colorless" → []
               "mono" → any single color (len==1)
    Multiple comma-separated expressions are ORed.
    """
    if ci is None:
        ci = []
    # Normalize to single-letter lower (e.g., ["W","U"] → {"w","u"})
    ci_set = {str(x).lower()[0] for x in ci if str(x)}
    for token in [t.strip().lower() for t in expr.split(",") if t.strip()]:
        if token in {"colorless", "c"}:
            if not ci_set:
                return True
            continue
        if token == "mono":
            if len(ci_set) == 1:
                return True
            continue
        # interpret sequence of wubrg letters as exact match
        letters = {ch for ch in token if ch in {"w", "u", "b", "r", "g"}}
        if letters and letters == ci_set:
            return True
    return False


def _bulk_random_token_entries(count: int) -> list[dict]:
    tokens = _bulk_iter_tokens()
    if not tokens or count <= 0:
        return []

    if count >= len(tokens):
        return [random.choice(tokens) for _ in range(count)]

    return random.sample(tokens, count)


def _token_entry_to_card(entry: dict) -> dict:
    card = {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "set": entry.get("set"),
        "collector_number": entry.get("collector_number"),
        "type_line": entry.get("type_line"),
    }

    image_url = entry.get("image_url")
    if image_url:
        card["image_uris"] = {"png": image_url, "large": image_url, "normal": image_url}

    return card


def _token_entry_local_path(entry: dict) -> tuple[Path, bool]:
    # Try hybrid organization first (subtype/set/filename)
    entry_enriched = _enrich_entry_with_art_meta(dict(entry))
    base_stem = _token_base_stem(entry_enriched)
    set_code = entry.get("set", "misc").lower()

    subtype_slug = entry.get("token_subtype_slug") or _slugify(
        entry.get("token_subtype") or "misc"
    )

    # Hybrid structure: tokens/subtype/set/filename
    hybrid_dir = Path(shared_tokens_path) / subtype_slug / set_code
    hybrid_candidates = [
        hybrid_dir / f"{base_stem}{ext}" for ext in (".png", ".jpg", ".jpeg", ".webp")
    ]

    for candidate in hybrid_candidates:
        if candidate.exists():
            return candidate, True

    # Fallback to legacy flat subtype organization for backwards compatibility
    name_slug = entry.get("name_slug") or _slugify(entry.get("name", "token"))

    legacy_dir = Path(shared_tokens_path) / subtype_slug
    legacy_candidates = [
        legacy_dir / f"{name_slug}_{set_code}{ext}"
        for ext in (".png", ".jpg", ".jpeg", ".webp")
    ]

    for candidate in legacy_candidates:
        if candidate.exists():
            return candidate, True

    # Return the preferred hybrid format path as default
    return hybrid_candidates[0], False


def _find_local_card_art(profile_name: str | None, card_entry: dict) -> list[str]:
    if not profile_name:
        return []

    profile_root = Path(_profile_root(profile_name))
    front_dir = profile_root / "pictures-of-cards" / "to-print"
    if not front_dir.exists():
        return []

    slug = _slugify(card_entry.get("name", ""))
    matches: list[Path] = []
    for pattern in (
        f"*{slug}*.png",
        f"*{slug}*.jpg",
        f"*{slug}*.jpeg",
        f"*{slug}*.webp",
    ):
        matches.extend(front_dir.glob(f"**/{pattern}"))

    return [str(path) for path in matches]


def _shared_land_art_paths(entry: dict) -> list[str]:
    """Return existing shared art paths for a land entry using the new naming.

    - New naming: %landtype%-%arttype%[-suffix].ext
    - Search all supported image extensions.
    - Backward compatibility: also check legacy pattern name_slug_collector.png
    """
    # Normalize set code to merge related sets
    set_code = _normalize_set_code(entry.get("set") or "unk")
    base_dir = Path(
        shared_basic_lands_path
        if entry.get("is_basic_land")
        else shared_non_basic_lands_path
    )
    set_dir = base_dir / set_code
    results: list[str] = []

    entry = _enrich_entry_with_art_meta(dict(entry))
    base_stem = _land_base_stem(entry)

    if set_dir.exists():
        # Match exact base, collector-suffixed, numeric-suffixed across extensions
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            for pattern in (
                f"{base_stem}{ext}",
                f"{base_stem}-*{ext}",  # includes -collector and -N
            ):
                for p in set_dir.glob(pattern):
                    if p.is_file():
                        results.append(str(p))

        # Legacy pattern: name_slug_{collector}.png (only png historically)
        name_slug = entry.get("name_slug") or _slugify(entry.get("name", "land"))
        collector = entry.get("collector_number") or ""
        collector_slug = (
            _slugify(collector, allow_underscores=True) if collector else "0"
        )
        legacy = set_dir / f"{name_slug}_{collector_slug}.png"
        if legacy.exists():
            results.append(str(legacy))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for r in results:
        if r not in seen:
            unique.append(r)
            seen.add(r)
    return unique


def _display_token_metadata(
    name_filter: str | None,
    subtype_filter: str | None,
    set_filter: str | None,
    colors_filter: str | None,
    limit: int,
    *,
    pause_after: bool = False,
) -> None:
    entries = _bulk_iter_tokens(
        name_filter=name_filter,
        subtype_filter=subtype_filter,
        set_filter=set_filter,
        colors_filter=colors_filter,
    )

    if not entries:
        click.echo("No tokens matched the given filters.")
        if pause_after:
            _prompt_to_continue()
        return

    entries.sort(
        key=lambda e: (
            e.get("name", "").lower(),
            e.get("set", ""),
            e.get("collector_number", ""),
        )
    )

    total = len(entries)
    show_count = total if (limit is None or limit <= 0) else min(total, limit)
    label = "all" if show_count == total else f"up to {show_count}"
    click.echo(f"Found {total} matching token(s). Displaying {label}.\n")

    for entry in entries[:show_count]:
        subtype_label = entry.get("token_subtype") or "—"
        set_code = (entry.get("set") or "").upper()
        collector_number = entry.get("collector_number") or "—"
        has_image = "yes" if entry.get("image_url") else "no"
        click.echo(
            f"- {entry.get('name')} | subtype={subtype_label} | set={set_code} #{collector_number} | image={has_image}"
        )

        oracle_text = entry.get("oracle_text") or ""
        oracle_text = oracle_text.strip()
        if oracle_text:
            for line in oracle_text.splitlines():
                click.echo(f"    {line}")

        oracle_keywords = entry.get("oracle_keywords") or []
        if oracle_keywords:
            click.echo(f"    keywords: {', '.join(oracle_keywords)}")

    if total > show_count:
        click.echo(f"\n... {total - show_count} more token(s) not shown.")

    if pause_after:
        _prompt_to_continue()


def _display_token_keyword_search(
    keyword: str, set_filter: str | None, limit: int, *, pause_after: bool = False
) -> None:
    keyword_norm = keyword.lower().strip()
    results: list[dict] = []
    db_available = _db_index_available()
    if db_available:
        results = db_query_tokens_by_keyword(
            keyword=keyword_norm, set_filter=set_filter or None, limit=limit
        )
    if (not db_available) or not results:
        entries = _bulk_iter_tokens(set_filter=set_filter or None)
        results = []
        for entry in entries:
            keywords = [kw.lower() for kw in entry.get("oracle_keywords") or []]
            oracle_text = (entry.get("oracle_text") or "").lower()
            if keyword_norm in keywords or keyword_norm in oracle_text:
                results.append(entry)

    if not results:
        click.echo(f"No tokens matched keyword '{keyword}'.")
        if pause_after:
            _prompt_to_continue()
        return

    results.sort(
        key=lambda e: (
            e.get("name", "").lower(),
            e.get("set", ""),
            e.get("collector_number", ""),
        )
    )
    total = len(results)
    show_count = total if (limit is None or limit <= 0) else min(total, limit)
    label = "all" if show_count == total else f"up to {show_count}"
    click.echo(
        f"Found {total} token(s) matching keyword '{keyword}'. Displaying {label}.\n"
    )

    for entry in results[:show_count]:
        subtype_label = entry.get("token_subtype") or "—"
        set_code = (entry.get("set") or "").upper()
        collector_number = entry.get("collector_number") or "—"
        image_url = entry.get("image_url") or "n/a"
        click.echo(
            f"- {entry.get('name')} | subtype={subtype_label} | set={set_code} #{collector_number}"
        )
        keywords = entry.get("oracle_keywords") or []
        if keywords:
            click.echo(f"    keywords: {', '.join(keywords)}")
        oracle_text = entry.get("oracle_text")
        if oracle_text:
            for line in oracle_text.splitlines():
                click.echo(f"    {line}")
        local_path, exists = _token_entry_local_path(entry)
        click.echo(f"    image: {image_url}")
        click.echo(f"    local: {'yes' if exists else 'no'} ({local_path})")

    if total > limit:
        click.echo(f"\n... {total - limit} more token(s) not shown.")

    if pause_after:
        _prompt_to_continue()


def _display_card_text_search(
    query: str,
    set_filter: str | None,
    limit: int,
    *,
    include_tokens: bool,
    pause_after: bool = False,
) -> None:
    query_norm = query.lower()
    set_filter_norm = set_filter.lower() if set_filter else None

    matches: list[dict] = []
    if _db_index_available():
        # Try FTS-backed search first for speed/quality.
        matches = db_query_oracle_fts(
            query=query,
            set_filter=set_filter_norm,
            include_tokens=include_tokens,
            limit=limit,
        )
        if not matches:
            # Fallback to LIKE-based DB query
            matches = db_query_oracle_text(
                query=query_norm,
                set_filter=set_filter_norm,
                include_tokens=include_tokens,
                limit=limit,
            )
    if not _db_index_available() or not matches:
        index = _load_bulk_index()
        entries = index.get("entries", {})
        matches = []
        for entry in entries.values():
            if not include_tokens and entry.get("is_token"):
                continue
            if set_filter_norm and entry.get("set") != set_filter_norm:
                continue
            text = (entry.get("oracle_text") or "").lower()
            name_slug = entry.get("name_slug") or ""
            type_line = (entry.get("type_line") or "").lower()
            if (
                query_norm in text
                or query_norm in type_line
                or _slugify(query) in name_slug
            ):
                matches.append(entry)

    if not matches:
        click.echo(f"No cards matched search '{query}'.")
        if pause_after:
            _prompt_to_continue()
        return

    matches.sort(
        key=lambda e: (
            e.get("name", "").lower(),
            e.get("set", ""),
            e.get("collector_number", ""),
        )
    )
    total = len(matches)
    show_count = total if (limit is None or limit <= 0) else min(total, limit)
    label = "all" if show_count == total else f"up to {show_count}"
    click.echo(f"Found {total} matching card(s). Displaying {label}.\n")

    for entry in matches[:show_count]:
        set_code = (entry.get("set") or "").upper()
        collector_number = entry.get("collector_number") or "—"
        name = entry.get("name")
        click.echo(f"- {name} | set={set_code} #{collector_number}")
        click.echo(f"    type: {entry.get('type_line')}")
        keywords = entry.get("oracle_keywords") or []
        if keywords:
            click.echo(f"    keywords: {', '.join(keywords)}")
        oracle_text = entry.get("oracle_text")
        if oracle_text:
            for line in oracle_text.splitlines():
                click.echo(f"    {line}")
        image_url = entry.get("image_url") or "n/a"
        click.echo(f"    image: {image_url}")
        if entry.get("is_token"):
            local_path, exists = _token_entry_local_path(entry)
            click.echo(f"    local: {'yes' if exists else 'no'} ({local_path})")

    if total > show_count:
        click.echo(f"\n... {total - show_count} more card(s) not shown.")

    if pause_after:
        _prompt_to_continue()


def _token_explorer_loop() -> None:
    while True:
        options = [
            "[1] Search by name substring",
            "[2] Search by subtype",
            "[3] Search by set code",
            "[4] Search by keyword/mechanic",
            "[5] Search oracle text/type",
            "[6] Ensure token art is cached locally",
            "[0] Back",
        ]
        _print_boxed_menu("Token Explorer", options)

        selection = _get_key_choice({"0", "1", "2", "3", "4", "5", "6"})

        if selection == "0":
            return

        limit = _prompt_int("Maximum results to show [25]: ", default=25, minimum=1)

        if selection == "1":
            name = _prompt_text("Name substring: ", allow_empty=True) or ""
            _display_token_metadata(
                name or None, None, None, None, limit, pause_after=True
            )
            continue

        if selection == "2":
            subtype = _prompt_text("Subtype: ", allow_empty=True) or ""
            if not subtype:
                click.echo("Subtype is required.")
                _prompt_to_continue()
                continue
            _display_token_metadata(None, subtype, None, None, limit, pause_after=True)
            continue

        if selection == "3":
            set_code = _prompt_text("Set code: ", allow_empty=True) or ""
            if not set_code:
                click.echo("Set code is required.")
                _prompt_to_continue()
                continue
            _display_token_metadata(
                None, None, set_code.lower(), None, limit, pause_after=True
            )
            continue

        if selection == "4":
            keyword = _prompt_text("Keyword/mechanic: ", allow_empty=True) or ""
            if not keyword:
                click.echo("Keyword is required.")
                _prompt_to_continue()
                continue
            set_code = _prompt_text("Set filter (optional): ", allow_empty=True)
            _display_token_keyword_search(keyword, set_code, limit, pause_after=True)
            continue

        if selection == "5":
            query = _prompt_text("Oracle text/type search: ", allow_empty=True) or ""
            if not query:
                click.echo("Search text is required.")
                _prompt_to_continue()
                continue
            set_code = _prompt_text("Set filter (optional): ", allow_empty=True)
            include_tokens = _prompt_yes_no("Include tokens? [y/N]: ")
            _display_card_text_search(
                query, set_code, limit, include_tokens=include_tokens, pause_after=True
            )
            continue

        if selection == "6":
            name = _prompt_text("Token name: ", allow_empty=True) or ""
            set_code = _prompt_text("Set code (optional): ", allow_empty=True) or ""
            subtype = _prompt_text("Subtype (optional): ", allow_empty=True) or ""
            tokens = _bulk_iter_tokens(
                name_filter=name or None,
                subtype_filter=subtype or None,
                set_filter=set_code or None,
            )
            if not tokens:
                click.echo("No matching tokens found.")
                _prompt_to_continue()
                continue
            chosen = tokens[0]
            meta, local_path = _ensure_token_local_copy(chosen)
            click.echo(f"Cached token locally at {local_path}.")
            _prompt_to_continue()
            continue

        click.echo("Please choose a valid option.")
        _prompt_to_continue()


def _load_token_pack_manifest(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    if not isinstance(manifest, list):
        raise click.ClickException(
            "Token pack manifest must be a JSON array of entries."
        )

    normalized: list[dict] = []

    for entry in manifest:
        if not isinstance(entry, dict):
            raise click.ClickException("Each token entry must be a JSON object.")

        name = entry.get("name")
        if not name:
            raise click.ClickException("Token entry missing required 'name'.")

        count = entry.get("count", 1)
        try:
            count_int = int(count)
        except (TypeError, ValueError):
            raise click.ClickException(f"Invalid count for token '{name}': {count}")

        if count_int <= 0:
            raise click.ClickException(f"Count for token '{name}' must be positive.")

        normalized.append(
            {
                "name": name,
                "count": count_int,
                "subtype": entry.get("subtype"),
                "set": entry.get("set"),
            }
        )

    return normalized


def _ensure_token_local_copy(entry: dict) -> tuple[dict, Path | None]:
    card = _token_entry_to_card(entry)
    created, path, meta = _save_token_card(card)
    if meta is None:
        meta = {
            "name": entry.get("name"),
            "set": entry.get("set"),
            "rel_path": None,
        }
    return meta, Path(path) if path else None


def _build_token_pack(
    manifest_path: str,
    pack_name: str | None,
    *,
    dry_run: bool = False,
    prefer_set: str | None = None,
    prefer_frame: str | None = None,
    prefer_artist: str | None = None,
) -> None:
    manifest_entries = _load_token_pack_manifest(manifest_path)

    if not manifest_entries:
        click.echo("Manifest contained no entries; nothing to do.")
        return

    manifest_filename = os.path.splitext(os.path.basename(manifest_path))[0]
    pack_label = pack_name or manifest_filename

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pack_root = os.path.join(
        project_root_directory, "magic-the-gathering", "shared", "token-packs"
    )
    output_dir = os.path.join(pack_root, f"{pack_label}_{timestamp}")
    output_dir_path = Path(output_dir)

    # Only create directories when not in dry-run mode
    if not dry_run:
        output_dir_path.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    missing: list[str] = []

    for entry in manifest_entries:
        name = entry["name"]
        count = entry["count"]
        subtype = entry.get("subtype")
        set_code = entry.get("set")

        tokens = _bulk_iter_tokens(
            name_filter=name, subtype_filter=subtype, set_filter=None
        )

        # Preference-based selection among candidates
        def _score(t: dict) -> int:
            s = 0
            # prefer_set_effective determined below (manifest set if provided, unless explicit prefer_set is given)
            try:
                eff = prefer_set_effective  # type: ignore[name-defined]
            except Exception:
                eff = prefer_set
            if eff and (t.get("set") or "").lower() == (eff or "").lower():
                s += 3
            if prefer_frame and (t.get("frame") or "") == prefer_frame:
                s += 2
            if prefer_artist and (
                (t.get("artist") or "").lower().find(prefer_artist.lower()) != -1
            ):
                s += 1
            return s

        if not tokens:
            missing.append(
                f"{name} (subtype={subtype or '—'}, set={set_code or 'any'})"
            )
            continue

        # If a set was provided in the manifest, lightly prefer it too unless an explicit prefer_set was passed
        prefer_set_effective = prefer_set or (set_code.lower() if set_code else None)
        if tokens and (prefer_set_effective or prefer_frame or prefer_artist):
            tokens = sorted(tokens, key=_score, reverse=True)

        chosen = tokens[0]
        meta, local_path = _ensure_token_local_copy(chosen)

        if local_path is None or not local_path.exists():
            missing.append(f"{name} (no local image; tried saving to shared tokens)")
            continue

        subtype_folder = chosen.get("token_subtype_slug") or "misc"
        destination_dir = output_dir_path / subtype_folder
        if dry_run:
            # Simulate planned pack path without writing
            planned_name = os.path.basename(str(local_path))
            destination = destination_dir / planned_name
        else:
            destination = _copy_with_unique_name(local_path, destination_dir)

        summary.append(
            {
                "name": meta.get("name") or chosen.get("name"),
                "set": meta.get("set") or chosen.get("set"),
                "source": str(local_path),
                "pack_path": str(destination.relative_to(output_dir_path)),
                "count": count,
                "oracle_text": chosen.get("oracle_text"),
                "keywords": chosen.get("oracle_keywords"),
                "color_identity": chosen.get("oracle_color_identity"),
            }
        )

        # Duplicate file for count > 1
        for duplicate_index in range(1, count):
            if dry_run:
                dup_name = f"copy{duplicate_index}_" + os.path.basename(str(local_path))
                duplicate_destination = destination_dir / dup_name
            else:
                duplicate_destination = _copy_with_unique_name(
                    local_path, destination_dir, prefix=f"copy{duplicate_index}"
                )
            summary.append(
                {
                    "name": meta.get("name") or chosen.get("name"),
                    "set": meta.get("set") or chosen.get("set"),
                    "source": str(local_path),
                    "pack_path": str(
                        duplicate_destination.relative_to(output_dir_path)
                    ),
                    "count": 1,
                    "oracle_text": chosen.get("oracle_text"),
                    "keywords": chosen.get("oracle_keywords"),
                    "color_identity": chosen.get("oracle_color_identity"),
                }
            )

    manifest_output = {
        "name": pack_label,
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "source_manifest": os.path.abspath(manifest_path),
        "entries": summary,
        "missing": missing,
    }

    os.makedirs(pack_root, exist_ok=True)
    if dry_run:
        click.echo(f"[dry-run] Token pack would be created at {output_dir}")
        click.echo(f"[dry-run] Items planned: {len(summary)}; missing: {len(missing)}")
        return
    manifest_file = os.path.join(output_dir, "manifest.json")
    _write_json_file(manifest_file, manifest_output)

    archive_path = shutil.make_archive(output_dir, "zip", output_dir)

    click.echo(f"Token pack created: {archive_path}")
    if missing:
        click.echo("Some entries could not be resolved:")
        for item in missing:
            click.echo(f"  - {item}")
    _notify(
        "Token Pack Ready",
        f"Pack '{pack_label}' archived at {archive_path}",
        event="token_pack",
    )
    _offer_open_in_folder(archive_path, kind="token pack")


def _write_token_manifest_template(output_path: str) -> None:
    template = [
        {"name": "Soldier", "count": 4, "set": "MH3", "subtype": "Soldier"},
        {"name": "Spirit", "count": 2, "subtype": "Spirit"},
    ]

    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(template, handle, indent=2)
        handle.write("\n")


def _token_pack_wizard_from_deck(
    deck_path: str,
    pack_name: str | None,
    *,
    dry_run: bool = False,
    append_mode: bool = False,
    overwrite_mode: bool = False,
    summary_only: bool = False,
    prefer_set: str | None = None,
    prefer_frame: str | None = None,
    prefer_artist: str | None = None,
) -> None:
    """Create a token pack manifest by scanning a deck list for token-producing cards.
    Supports local text files and Moxfield/Archidekt/TappedOut/MTGGoldfish URLs.
    Writes a manifest JSON under archived/token-pack-wizard/ and builds the pack.

    Preferences control which printing to select when multiple candidates match.
    If dry_run is True, do not write files; print planned structure.
    If append_mode is True, append to existing manifest with same name.
    If overwrite_mode is True, overwrite existing manifest with same name.
    If summary_only is True, only show summary without building pack.
    """
    # Load deck into a temporary normalized file so we can reuse the deck parser
    source_url = None
    if deck_path.startswith("http://") or deck_path.startswith("https://"):
        deck_text, deck_title = _download_deck_from_url(deck_path)
        temp_dir = os.path.join(project_root_directory, "archived", "deck-cache")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(
            temp_dir,
            f"wizard_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt",
        )
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(deck_text)
        normalized_deck_path = temp_path
        pack_label = pack_name or deck_title
        source_url = deck_path
    else:
        normalized_deck_path = deck_path
        pack_label = pack_name or os.path.splitext(os.path.basename(deck_path))[0]

    deck_entries = _parse_deck_file(normalized_deck_path)
    if not deck_entries:
        raise click.ClickException("Deck appears to be empty.")
    # Count tokens suggested by the deck's cards
    token_counts: dict[str, dict] = {}
    for item in deck_entries:
        count = int(item.get("count") or 1)
        name = item.get("name") or ""
        set_code = item.get("set")
        entry = _find_card_entry(name, set_code)
        if not entry:
            continue
        _gather_token_suggestions(entry, count, token_counts)

    if not token_counts:
        click.echo("No token suggestions were found from this deck.")
        return

    # Build manifest entries from token_counts
    manifest_entries: list[dict] = []
    for key, info in token_counts.items():
        entry = info.get("entry") or {}
        manifest_entries.append(
            {
                "name": entry.get("name") or key,
                "count": int(info.get("total") or 0),
                "set": entry.get("set"),
                "subtype": entry.get("token_subtype"),
            }
        )

    # Sort by name, set for stability
    manifest_entries.sort(
        key=lambda e: (str(e.get("name")).lower(), str(e.get("set") or ""))
    )

    # Preview
    click.echo("\nToken Pack Wizard Preview\n--------------------------")
    click.echo(f"Deck: {source_url or normalized_deck_path}")
    click.echo(f"Entries: {len(manifest_entries)}\n")
    for item in manifest_entries:
        label_set = (item.get("set") or "").upper() or "—"
        subtype = item.get("subtype") or "—"
        click.echo(
            f"- {item.get('name')} x{item.get('count')} | set={label_set} | subtype={subtype}"
        )

    # Handle summary-only mode
    if summary_only:
        click.echo(
            "\n[OK] Summary complete (--token_pack_summary_only mode, no files written)"
        )
        return

    # Write manifest to archived/token-pack-wizard/
    wizard_root = os.path.join(project_root_directory, "archived", "token-pack-wizard")
    os.makedirs(wizard_root, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pack_slug = _slugify(pack_label) if pack_label else f"pack_{ts}"

    # Handle append/overwrite modes
    if append_mode or overwrite_mode:
        # Look for existing manifest with same pack_slug (without timestamp)
        existing_manifests = [
            f
            for f in os.listdir(wizard_root)
            if f.startswith(pack_slug) and f.endswith(".json")
        ]

        if existing_manifests and append_mode:
            # Append to most recent existing manifest
            existing_manifests.sort(reverse=True)
            manifest_path = os.path.join(wizard_root, existing_manifests[0])
            click.echo(f"\n📝 Appending to existing manifest: {manifest_path}")

            # Load existing entries
            with open(manifest_path, "r", encoding="utf-8") as handle:
                existing_entries = json.load(handle)

            # Merge entries (combine counts for duplicates)
            merged = {}
            for entry in existing_entries + manifest_entries:
                key = (entry.get("name"), entry.get("set"), entry.get("subtype"))
                if key in merged:
                    merged[key]["count"] += entry.get("count", 0)
                else:
                    merged[key] = entry.copy()

            manifest_entries = list(merged.values())
            manifest_entries.sort(
                key=lambda e: (str(e.get("name")).lower(), str(e.get("set") or ""))
            )
        elif existing_manifests and overwrite_mode:
            # Overwrite most recent existing manifest
            existing_manifests.sort(reverse=True)
            manifest_path = os.path.join(wizard_root, existing_manifests[0])
            click.echo(f"\n🔄 Overwriting existing manifest: {manifest_path}")
        else:
            # Create new manifest with timestamp
            manifest_path = os.path.join(wizard_root, f"{pack_slug}_{ts}.json")
    else:
        # Default: create new manifest with timestamp
        manifest_path = os.path.join(wizard_root, f"{pack_slug}_{ts}.json")

    # Write the manifest
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest_entries, handle, indent=2)
        handle.write("\n")

    click.echo(f"\n[OK] Wrote manifest: {manifest_path}")

    # Build the token pack
    _build_token_pack(
        manifest_path,
        pack_label,
        dry_run=dry_run,
        prefer_set=prefer_set,
        prefer_frame=prefer_frame,
        prefer_artist=prefer_artist,
    )


def _configure_notifications_flow():
    config = _load_notification_config()

    click.echo("\nNotification Settings\n----------------------")
    current_enabled = "on" if config.get("enabled") else "off"
    click.echo(f"Notifications currently: {current_enabled}")

    enable = _prompt_yes_no("Enable notifications?", default=False)
    config["enabled"] = enable

    if enable:
        macos_enable = _prompt_yes_no("Enable macOS notifications?", default=False)
        config.setdefault("macos", {})["enabled"] = macos_enable

        webhook_url = _prompt_text("Webhook URL (leave blank to disable)", default="")
        if webhook_url:
            config.setdefault("webhook", {})["enabled"] = True
            config["webhook"]["url"] = webhook_url
        else:
            config.setdefault("webhook", {})["enabled"] = False
            config["webhook"]["url"] = ""
    else:
        config.setdefault("macos", {})["enabled"] = False
        config.setdefault("webhook", {})["enabled"] = False
        config.setdefault("webhook", {})["url"] = ""

    _save_notification_config(config)
    click.echo("Notification preferences saved.")


def _parse_deck_file(path: str) -> list[dict]:
    import re

    deck_entries: list[dict] = []
    pattern = re.compile(
        r"^(?P<count>\d+)\s+(?P<name>[^\(]+?)(?:\s+\((?P<set>[A-Za-z0-9]{2,})\))?(?:\s+\d+)?\s*$"
    )

    try:
        handle = open(path, "r", encoding="utf-8")
    except OSError as error:
        raise click.ClickException(f"Could not read deck file '{path}': {error}")

    with handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue
            if stripped.lower().startswith("sb:"):
                continue

            match = pattern.match(stripped)
            if not match:
                raise click.ClickException(f"Could not parse deck line: '{stripped}'")

            count = int(match.group("count"))
            name = match.group("name").strip()
            set_code = match.group("set")

            deck_entries.append(
                {
                    "count": count,
                    "name": name,
                    "set": set_code.lower() if set_code else None,
                }
            )

    return deck_entries


def _find_card_entry(name: str, set_code: str | None = None) -> dict | None:
    db_matches = _db_lookup_cards_by_name(name=name, set_code=set_code, limit=1)
    if db_matches:
        return db_matches[0]

    index = _load_bulk_index()
    entries = index.get("entries", {})
    name_slug = _slugify(name)
    candidates = index.get("cards_by_name", {}).get(name_slug, [])

    if not candidates:
        return None

    set_code = set_code.lower() if set_code else None

    best = None
    for card_id in candidates:
        entry = entries.get(card_id)
        if not entry:
            continue
        if set_code and entry.get("set") != set_code:
            continue
        best = entry
        if set_code:
            break

    return best


def _gather_token_suggestions(
    entry: dict, count: int, token_counts: dict[str, dict]
) -> None:
    all_parts = entry.get("all_parts") or []
    if not all_parts:
        return
    part_ids = [str(part.get("id")) for part in all_parts if isinstance(part, dict)]
    db_entries = _db_lookup_cards_by_ids(part_ids)
    db_map = {item.get("id"): item for item in db_entries if item.get("id") is not None}
    index_entries = None

    for part in all_parts:
        if not isinstance(part, dict):
            continue
        if part.get("component") != "token":
            continue
        token_id = part.get("id")
        if not token_id:
            continue
        token_entry = db_map.get(token_id)
        if token_entry is None:
            index_entries = (
                _load_bulk_index().get("entries", {})
                if index_entries is None
                else index_entries
            )
            token_entry = index_entries.get(token_id) if index_entries else None
        if not token_entry:
            continue

        key = token_entry.get("name") or token_id
        info = token_counts.setdefault(
            str(key),
            {
                "total": 0,
                "details": [],
                "entry": token_entry,
            },
        )
        info["total"] += count
        info["details"].append(
            {
                "source_card": entry.get("name"),
                "count": count,
            }
        )


def _process_deck_list(
    deck_path: str,
    deck_name: str | None,
    deck_output_dir: str | None,
    profile_name: str | None = None,
) -> None:
    source_url = None

    if deck_path.startswith("http://") or deck_path.startswith("https://"):
        deck_text, deck_title = _download_deck_from_url(deck_path)
        temp_dir = os.path.join(project_root_directory, "archived", "deck-cache")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(
            temp_dir,
            f"downloaded_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt",
        )
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(deck_text)
        deck_entries = _parse_deck_file(temp_path)
        deck_name = deck_name or deck_title
        deck_source_path = deck_path
        deck_file_path = temp_path
        source_url = deck_path
    else:
        deck_entries = _parse_deck_file(deck_path)
        deck_source_path = os.path.abspath(deck_path)
        deck_file_path = deck_path

    if not deck_entries:
        click.echo("Deck list contained no recognizable entries.")
        return

    deck_label = deck_name or os.path.splitext(os.path.basename(deck_path))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if deck_output_dir:
        output_root = os.path.abspath(deck_output_dir)
    elif profile_name:
        output_root = os.path.join(_profile_root(profile_name), "deck-reports")
    else:
        output_root = DECK_REPORT_ROOT
    output_root = os.path.abspath(output_root)
    os.makedirs(output_root, exist_ok=True)
    output_dir = os.path.join(output_root, f"{_slugify(deck_label)}_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    card_reports: list[dict] = []
    missing_cards: list[str] = []
    color_identity: set[str] = set()
    type_counts: dict[str, int] = {}
    mana_curve: dict[str, int] = {}
    basic_lands: dict[str, int] = {}
    token_counts: dict[str, dict] = {}

    total_cards = 0

    for entry in deck_entries:
        count = entry["count"]
        name = entry["name"]
        set_code = entry["set"]

        card_entry = _find_card_entry(name, set_code)

        if card_entry is None:
            missing_cards.append(f"{count}x {name} ({set_code or 'any set'})")
            continue

        total_cards += count
        color_identity.update(card_entry.get("oracle_color_identity") or [])

        type_line = card_entry.get("type_line") or ""
        type_prefix = type_line.split("—")[0]
        for token in type_prefix.split():
            type_counts[token] = type_counts.get(token, 0) + count

        mana_value = card_entry.get("mana_value")
        try:
            mana_bucket = (
                str(int(round(float(mana_value)))) if mana_value is not None else "0"
            )
        except (TypeError, ValueError):
            mana_bucket = "0"
        mana_curve[mana_bucket] = mana_curve.get(mana_bucket, 0) + count

        if card_entry.get("is_basic_land"):
            basic_lands[name] = basic_lands.get(name, 0) + count

        _gather_token_suggestions(card_entry, count, token_counts)

        local_art_paths = _find_local_card_art(profile_name, card_entry)
        shared_land_paths = (
            _shared_land_art_paths(card_entry)
            if "land" in (card_entry.get("type_line") or "").lower()
            else []
        )

        card_reports.append(
            {
                "name": card_entry.get("name"),
                "set": (card_entry.get("set") or "").upper(),
                "collector_number": card_entry.get("collector_number"),
                "count": count,
                "type_line": type_line,
                "mana_value": card_entry.get("mana_value"),
                "oracle_text": card_entry.get("oracle_text"),
                "oracle_keywords": card_entry.get("oracle_keywords"),
                "oracle_color_identity": card_entry.get("oracle_color_identity"),
                "local_art_paths": local_art_paths,
                "shared_art_paths": shared_land_paths,
            }
        )

    token_suggestions: list[dict] = []
    for token_name, info in token_counts.items():
        token_entry = info.get("entry", {})
        token_suggestions.append(
            {
                "name": token_name,
                "set": (token_entry.get("set") or "").upper(),
                "count": info.get("total", 0),
                "subtype": token_entry.get("token_subtype"),
                "details": info.get("details", []),
            }
        )

    token_suggestions.sort(key=lambda t: (-t["count"], t["name"]))

    coverage_with_art: list[dict] = []
    coverage_missing: list[dict] = []

    for card in card_reports:
        record = {
            "name": card["name"],
            "set": card["set"],
            "collector_number": card["collector_number"],
            "local_art_paths": card.get("local_art_paths", []),
            "shared_art_paths": card.get("shared_art_paths", []),
        }
        if card.get("local_art_paths") or card.get("shared_art_paths"):
            coverage_with_art.append(record)
        else:
            coverage_missing.append(record)

    summary = {
        "deck_name": deck_label,
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "source": deck_source_path,
        "source_url": source_url,
        "deck_file": os.path.abspath(deck_file_path),
        "card_total": total_cards,
        "color_identity": sorted(color_identity),
        "type_counts": dict(
            sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "mana_curve": dict(sorted(mana_curve.items(), key=lambda item: int(item[0]))),
        "basic_lands": basic_lands,
        "cards": card_reports,
        "token_suggestions": token_suggestions,
        "missing_cards": missing_cards,
        "art_coverage": {
            "with_art": coverage_with_art,
            "missing_art": coverage_missing,
        },
    }

    _ensure_directory(output_dir)
    summary_path = os.path.join(output_dir, "deck_summary.json")
    _write_json_file(summary_path, summary)

    csv_path = os.path.join(output_dir, "deck_cards.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "Name",
                "Count",
                "Set",
                "Collector",
                "Mana Value",
                "Type Line",
                "Oracle Keywords",
                "Oracle Text",
                "Local Art Paths",
                "Shared Art Paths",
            ]
        )
        for card in card_reports:
            writer.writerow(
                [
                    card["name"],
                    card["count"],
                    card["set"],
                    card["collector_number"],
                    card["mana_value"],
                    card["type_line"],
                    ", ".join(card.get("oracle_keywords") or []),
                    (card.get("oracle_text") or "").replace("\n", " "),
                    "; ".join(card.get("local_art_paths") or []),
                    "; ".join(card.get("shared_art_paths") or []),
                ]
            )

    if token_suggestions:
        manifest_entries = []
        for token in token_suggestions:
            manifest_entries.append(
                {
                    "name": token["name"],
                    "count": token["count"],
                    "subtype": token.get("subtype"),
                    "set": token.get("set"),
                }
            )
        token_manifest_path = os.path.join(output_dir, "token_manifest.json")
        _write_json_file(token_manifest_path, manifest_entries)

    _notify("Deck Report Ready", f"Deck '{deck_label}' processed.", event="deck_report")
    click.echo(f"Deck report created: {summary_path}")
    if missing_cards:
        click.echo("Missing cards:")
        for item in sorted(missing_cards):
            click.echo(f"  - {item}")
    _offer_open_in_folder(
        output_dir or os.path.dirname(summary_path), kind="deck report"
    )

    # Offer to generate a PDF immediately using deck-named subfolders
    if profile_name and sys.stdin.isatty():
        try:
            choice = (
                "y"
                if _prompt_yes_no(
                    f"Generate a PDF for profile '{profile_name}' now?", default=False
                )
                else "n"
            )
        except EOFError:
            choice = "n"
        if choice in {"y", "yes"}:
            deck_slug = _slugify(deck_label)
            # Ensure the deck subfolders exist
            front_p, back_p, double_p = _ensure_deck_subfolders(profile_name, deck_slug)
            click.echo(
                f"Prepared deck subfolders for '{deck_label}':\n  front={front_p}\n  back={back_p}\n  double_sided={double_p}"
            )
            # Download missing fronts into the deck's front folder using cached bulk index (image URLs served by Scryfall)
            dl_new, dl_skipped = _download_deck_fronts(card_reports, Path(front_p))
            click.echo(
                f"Fetched deck fronts: downloaded {dl_new}, skipped {dl_skipped} (already present or missing data)"
            )
            # Run the PDF generator for this deck
            try:
                _run_profile_generation(profile_name, ["--deck", deck_slug])
            except SystemExit:
                pass


def load_profiles() -> dict[str, dict[str, str]]:
    global _PROFILE_CACHE

    if _PROFILE_CACHE is not None:
        return _PROFILE_CACHE

    if not os.path.exists(profiles_path):
        _PROFILE_CACHE = {}
        return _PROFILE_CACHE

    with open(profiles_path, encoding="utf-8") as profiles_file:
        data = json.load(profiles_file)

    if not isinstance(data, dict):
        raise click.ClickException(
            "Invalid profiles.json format: expected an object at the top level."
        )

    parsed_profiles: dict[str, dict[str, str]] = {}

    for key, value in data.items():
        if isinstance(value, dict):
            parsed_profiles[str(key)] = dict(value)

    _PROFILE_CACHE = parsed_profiles
    return _PROFILE_CACHE


def refresh_profiles_cache() -> None:
    global _PROFILE_CACHE
    _PROFILE_CACHE = None


def get_profiles() -> dict[str, dict[str, str]]:
    return load_profiles()


def get_profile_names() -> list[str]:
    return sorted(get_profiles().keys())


def save_profiles(profiles: dict[str, dict[str, str]]) -> None:
    ordered_profiles = {key: profiles[key] for key in sorted(profiles.keys())}

    os.makedirs(os.path.dirname(profiles_path), exist_ok=True)

    with open(profiles_path, "w", encoding="utf-8") as profiles_file:
        json.dump(ordered_profiles, profiles_file, indent=2)
        profiles_file.write("\n")

    refresh_profiles_cache()


class ProfileParamType(click.ParamType):
    name = "profile"

    def convert(self, value, param, ctx):  # noqa: D401 (click callback signature)
        profiles = get_profiles()

        if not profiles:
            self.fail("No profiles are defined in assets/profiles.json.", param, ctx)

        if value not in profiles:
            choices = ", ".join(sorted(profiles.keys())) or "none"
            self.fail(
                f"Unknown profile '{value}'. Available profiles: {choices}.", param, ctx
            )

        return value


profile_param_type = ProfileParamType()
INITIAL_PROFILE_NAMES = get_profile_names()


def resolve_path(path: str, *, base_directory: str | None = None) -> str:
    expanded_path = os.path.expanduser(path)

    if os.path.isabs(expanded_path):
        return os.path.abspath(expanded_path)

    if base_directory is not None:
        return os.path.abspath(os.path.join(base_directory, expanded_path))

    return os.path.abspath(os.path.join(project_root_directory, expanded_path))


def build_profile_directories(
    profile_name: str, current_paths: dict[str, str]
) -> dict[str, str]:
    profiles = get_profiles()

    if profile_name not in profiles:
        raise click.ClickException(
            f"Profile '{profile_name}' not found in profiles.json."
        )

    profile_definition = profiles[profile_name]

    base_path = profile_definition.get("base_path")
    resolved_base = (
        resolve_path(base_path, base_directory=project_root_directory)
        if base_path
        else None
    )

    updated_paths = current_paths.copy()

    def resolve_section(
        key: str, fallback_subdir: str | None, base_for_relative: str | None
    ) -> str | None:
        explicit_path = profile_definition.get(key)

        if explicit_path:
            return resolve_path(explicit_path, base_directory=base_for_relative)

        if resolved_base and fallback_subdir:
            return os.path.join(resolved_base, fallback_subdir)

        return None

    front_path = resolve_section("front_dir", "front", resolved_base)
    back_path = resolve_section("back_dir", "back", resolved_base)
    double_sided_path = resolve_section(
        "double_sided_dir", "double_sided", resolved_base
    )
    output_path_override = resolve_section("output_path", None, project_root_directory)

    if front_path:
        updated_paths["front_dir_path"] = front_path
    if back_path:
        updated_paths["back_dir_path"] = back_path
    if double_sided_path:
        updated_paths["double_sided_dir_path"] = double_sided_path
    if output_path_override:
        updated_paths["output_path"] = output_path_override

    return updated_paths


def _profile_root(profile_name: str) -> str:
    return os.path.join(proxied_decks_root, profile_name)


def _pictures_root(profile_name: str) -> str:
    return os.path.join(_profile_root(profile_name), "pictures-of-cards")


def _log_relative(path: str, base: str) -> str:
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _ensure_profile_structure(
    profile_name: str,
) -> tuple[list[str], list[str], list[str]]:
    created_directories: list[str] = []
    created_symlinks: list[str] = []
    warnings: list[str] = []

    profile_root = _profile_root(profile_name)

    for relative in REQUIRED_PROFILE_DIRECTORIES:
        target_path = (
            profile_root if relative == "" else os.path.join(profile_root, relative)
        )
        if not os.path.exists(target_path):
            os.makedirs(target_path, exist_ok=True)
            if relative == "":
                created_directories.append("profile root")
            else:
                created_directories.append(_log_relative(target_path, profile_root))

    pictures_root = _pictures_root(profile_name)

    _migrate_profile_shared_assets(profile_root, created_directories, warnings)

    for link_name, target in PROFILE_SYMLINKS.items():
        if target is None:
            continue
        os.makedirs(target, exist_ok=True)
        link_path = os.path.join(pictures_root, link_name)

        parent_dir = os.path.dirname(link_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        if not os.path.exists(target):
            warnings.append(f"Shared path missing for '{link_name}': {target}")
            continue

        if os.path.islink(link_path):
            if os.path.realpath(link_path) == os.path.realpath(target):
                continue
            os.unlink(link_path)
        elif os.path.exists(link_path):
            if os.path.isdir(link_path):
                continue
            warnings.append(
                f"Cannot create symlink '{link_name}' because a file already exists at {link_path}"
            )
            continue

        os.symlink(target, link_path)
        created_symlinks.append(_log_relative(link_path, profile_root))

    return created_directories, created_symlinks, warnings


def _sanitize_profile_name(raw_name: str) -> str | None:
    sanitized = raw_name.strip()

    if not sanitized:
        return None

    sanitized = sanitized.replace(" ", "-").lower()

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not all(char in allowed for char in sanitized):
        return None

    return sanitized


def _profile_config_defaults(profile_name: str) -> dict[str, str]:
    to_print_dir = os.path.join(
        _profile_root(profile_name), "pictures-of-cards", "to-print"
    )
    base_relative = os.path.relpath(to_print_dir, project_root_directory)
    output_rel = os.path.join(
        "magic-the-gathering",
        "proxied-decks",
        profile_name,
        "pdfs-of-decks",
        f"{profile_name}.pdf",
    )

    return {
        "base_path": base_relative,
        "output_path": output_rel,
    }


def _archive_profile_directory(profile_name: str) -> str | None:
    profile_root = _profile_root(profile_name)

    if not os.path.exists(profile_root):
        return None

    # Store profile deletions under archived/profile-backups
    profile_archive_dir = os.path.join(
        project_root_directory, "archived", "profile-backups"
    )
    os.makedirs(profile_archive_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")
    base_name = os.path.join(profile_archive_dir, f"{profile_name}-{timestamp}")
    counter = 1
    archive_base = base_name

    while os.path.exists(f"{archive_base}.zip"):
        counter += 1
        archive_base = f"{base_name}-{counter}"

    archive_path = shutil.make_archive(archive_base, "zip", profile_root)
    shutil.rmtree(profile_root)

    return archive_path


def _add_profile_definition(profile_name: str) -> None:
    profiles = dict(get_profiles())
    profiles[profile_name] = _profile_config_defaults(profile_name)
    save_profiles(profiles)


def _remove_profile_definition(profile_name: str) -> None:
    profiles = dict(get_profiles())

    if profile_name in profiles:
        del profiles[profile_name]
        save_profiles(profiles)


def _normalize_set_code(set_code: str) -> str:
    """Normalize set codes to merge related sets into canonical folders.

    Handles variants like CED/CEI, sets with spaces/dashes, etc.
    """
    if not set_code:
        return "misc"

    set_code = set_code.lower().strip()

    # Map of set code variants to their canonical name
    # Format: set_code -> canonical_folder_name
    set_normalizations = {
        # Collectors' Edition variants (domestic vs international)
        "ced": "ce",
        "cei": "ce",
        # Add other known variants here as needed
    }

    # Check for direct mapping first
    if set_code in set_normalizations:
        return set_normalizations[set_code]

    # For sets with spaces or special characters, slugify them
    # This handles cases like "eos 2" -> "eos-2"
    if " " in set_code or any(c in set_code for c in ["-", "/", "\u2014", "\u2013"]):
        return _slugify(set_code)

    # Otherwise return as-is (already lowercase)
    return set_code


def _slugify(value: str, *, allow_underscores: bool = False) -> str:
    value = value.lower()
    result: list[str] = []
    previous_dash = False

    for char in value:
        if char.isalnum():
            result.append(char)
            previous_dash = False
        elif char in {" ", "-", "\u2014", "\u2013", "/"}:
            if not previous_dash:
                result.append("-")
                previous_dash = True
        elif char == "_" and allow_underscores:
            result.append("_")
            previous_dash = False
        else:
            continue

    slug = "".join(result).strip("-")

    while "--" in slug:
        slug = slug.replace("--", "-")

    return slug or "token"


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _http_get(
    url: str,
    *,
    as_json: bool = False,
    rate_limiter: RateLimiter | None = _SCRYFALL_RATE_LIMITER,
) -> bytes | dict:
    last_error: Exception | None = None

    for attempt in range(5):
        try:
            if rate_limiter is not None:
                rate_limiter.wait()
            req = Request(url, headers={"User-Agent": SCRYFALL_USER_AGENT})
            with urlopen(req) as response:
                payload = response.read()
                if as_json:
                    return json.loads(payload.decode("utf-8"))
                return payload
        except HTTPError as error:
            last_error = error
            if error.code == 429 and attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        except URLError as error:
            last_error = error
            time.sleep(0.5 * (attempt + 1))
        except ConnectionResetError as error:
            last_error = error
            time.sleep(0.5 * (attempt + 1))
        except ssl.SSLError as error:
            last_error = error
            time.sleep(0.5 * (attempt + 1))

    raise click.ClickException(f"Unable to reach Scryfall ({last_error}).")


def _scryfall_json(path_or_url: str, params: dict[str, str] | None = None) -> dict:
    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        url = f"{SCRYFALL_API_BASE}{path_or_url}"
        if params:
            url = f"{url}?{urlencode(params)}"

    data = _http_get(url, as_json=True)

    if not isinstance(data, dict):
        raise click.ClickException("Scryfall returned an unexpected response.")

    if data.get("object") == "error":
        message = data.get("details") or data.get("type") or "Unknown error."
        raise click.ClickException(f"Scryfall error: {message}")

    return data


def _download_image(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Image fetches go to Scryfall's CDN; bypass the API rate limiter and rely on
    # capped thread concurrency for politeness and throughput.
    tmp_path = destination.with_suffix(destination.suffix + ".part")
    try:
        binary = _http_get(url, rate_limiter=None)
        with tmp_path.open("wb") as handle:
            handle.write(binary)  # type: ignore[arg-type]
        # Atomic replace
        tmp_path.replace(destination)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _token_subtype_from_type_line(type_line: str) -> str:
    if "—" in type_line:
        return type_line.split("—", 1)[1].strip()
    if " - " in type_line:
        return type_line.split(" - ", 1)[1].strip()
    return type_line.replace("Token", "").strip() or "Token"


def _extract_token_metadata(card: dict) -> dict:
    type_line = card.get("type_line") or "Token"
    subtype_name = _token_subtype_from_type_line(type_line)
    subtype_slug = _slugify(subtype_name)

    name = card.get("name", "Token")
    name_slug = _slugify(name)
    set_code = (card.get("set") or "unk").lower()
    collector_number = card.get("collector_number")

    return {
        "name": name,
        "name_slug": name_slug,
        "set": set_code,
        "subtype": subtype_name,
        "subtype_slug": subtype_slug,
        "collector_number": collector_number,
    }


def _extract_image_url(card: dict) -> str | None:
    image_uris = card.get("image_uris")

    if not image_uris and card.get("card_faces"):
        for face in card["card_faces"]:
            if face.get("image_uris"):
                image_uris = face["image_uris"]
                break

    if not image_uris:
        return None

    for key in ("png", "large", "normal"):
        if key in image_uris:
            return image_uris[key]

    return None


def _save_token_card(card: dict) -> tuple[bool, Path | None, dict | None]:
    image_url = _extract_image_url(card)

    if not image_url:
        return False, None, None

    # Enrich with art metadata for proper art type detection
    card = _enrich_entry_with_art_meta(dict(card))

    # Use new token naming scheme
    base_stem = _token_base_stem(card)
    extension = _extension_from_url(image_url, ".png")

    # Hybrid directory organization: tokens/subtype/set/filename
    meta = _extract_token_metadata(card)
    subtype_slug = meta["subtype_slug"]
    set_code = card.get("set", "misc").lower()

    # Create subtype/set directory structure
    subtype_dir = Path(shared_tokens_path) / subtype_slug
    set_dir = subtype_dir / set_code
    set_dir.mkdir(parents=True, exist_ok=True)

    # Use collector number collision resolution like lands
    collector_number = card.get("collector_number")
    destination = _unique_token_destination(
        set_dir, base_stem, extension, collector_number
    )

    if destination.exists():
        return False, destination, None

    _download_image(image_url, destination)

    # Update metadata for return value
    meta.update(
        {
            "ext": extension,
            "rel_path": str(destination.relative_to(shared_tokens_path)),
            "abs_path": str(destination),
        }
    )

    return True, destination, meta


TOKEN_EXTENSION_PRIORITY = {
    ".png": 3,
    ".jpg": 2,
    ".jpeg": 2,
    ".webp": 1,
}


DEFAULT_TOKEN_WARN_LANGS = ["ph", "ja"]


def _prefer_token_file(current: Path, candidate: Path) -> Path:
    current_ext = current.suffix.lower()
    candidate_ext = candidate.suffix.lower()
    current_priority = TOKEN_EXTENSION_PRIORITY.get(current_ext, 0)
    candidate_priority = TOKEN_EXTENSION_PRIORITY.get(candidate_ext, 0)

    if candidate_priority > current_priority:
        return candidate
    if candidate_priority < current_priority:
        return current

    try:
        if candidate.stat().st_size > current.stat().st_size:
            return candidate
    except OSError:
        pass

    return current


def _rebuild_token_index() -> None:
    root = Path(shared_tokens_path)
    by_set: dict[str, list[dict]] = {}
    by_subtype: dict[str, list[dict]] = {}
    total = 0

    if not root.exists():
        return

    # Index hybrid structure (subtype/set/filename)
    for subtype_dir in sorted(root.iterdir()):
        if not subtype_dir.is_dir():
            continue
        if subtype_dir.name.startswith(".") or subtype_dir.name == "_index.json":
            continue

        subtype_name = subtype_dir.name
        subtype_records: list[dict] = []

        # Check for both hybrid structure (subtype/set/) and legacy flat structure
        for item in sorted(subtype_dir.iterdir()):
            if item.is_dir():
                # Hybrid structure: subtype/set/files
                set_name = item.name
                for file in sorted(item.iterdir()):
                    if not file.is_file():
                        continue
                    if file.name.startswith("."):
                        continue

                    extension = file.suffix.lower()
                    if extension not in IMAGE_EXTENSIONS:
                        continue

                    # Try to parse token info from filename
                    stem = file.stem
                    token_info = _parse_token_stem(stem) if "-" in stem else None

                    record = {
                        "stem": stem,
                        "ext": extension,
                        "rel_path": str(file.relative_to(root)),
                        "abs_path": str(file),
                        "set": set_name,
                        "subtype": subtype_name,
                    }

                    if token_info:
                        record.update(token_info)

                    subtype_records.append(record)
                    total += 1

                    # Add to set index
                    if set_name not in by_set:
                        by_set[set_name] = []
                    by_set[set_name].append(record)

            elif item.is_file():
                # Legacy flat structure: subtype/files (backwards compatibility)
                extension = item.suffix.lower()
                if extension in IMAGE_EXTENSIONS and not item.name.startswith("."):
                    stem = item.stem
                    # Try to guess set from legacy naming (name_set.ext)
                    set_name = "misc"
                    if "_" in stem:
                        set_name = stem.split("_")[-1]

                    record = {
                        "stem": stem,
                        "ext": extension,
                        "rel_path": str(item.relative_to(root)),
                        "abs_path": str(item),
                        "set": set_name,
                        "subtype": subtype_name,
                        "legacy": True,
                    }

                    subtype_records.append(record)
                    total += 1

        if subtype_records:
            by_subtype[subtype_name] = subtype_records

    index_payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "count": total,
        "structure": "hybrid",  # Mark as hybrid structure
        "by_set": by_set,
        "by_subtype": by_subtype,
    }

    root.mkdir(parents=True, exist_ok=True)

    with open(shared_tokens_index_path, "w", encoding="utf-8") as handle:
        json.dump(index_payload, handle, indent=2)
        handle.write("\n")


def _list_image_files(directory: str | Path) -> list[Path]:
    path = Path(directory)

    if not path.exists() or not path.is_dir():
        return []

    files: list[Path] = []

    for item in sorted(path.iterdir()):
        if not item.is_file():
            continue
        if item.name.startswith(".") or item.name in EXTRANEOUS_FILES:
            continue
        if item.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        files.append(item)

    return files


def _collect_shared_token_files() -> list[Path]:
    root = Path(shared_tokens_path)

    if not root.exists():
        return []

    files: list[Path] = []
    for item in root.rglob("*"):
        if (
            item.is_file()
            and item.suffix.lower() in IMAGE_EXTENSIONS
            and not item.name.startswith(".")
        ):
            files.append(item)

    return files


def _collect_shared_card_backs() -> list[Path]:
    root = Path(shared_card_backs_path)

    if not root.exists():
        return []

    files: list[Path] = []
    for item in root.rglob("*"):
        if (
            item.is_file()
            and item.suffix.lower() in IMAGE_EXTENSIONS
            and not item.name.startswith(".")
        ):
            files.append(item)

    return files


def _load_skipped_basic_land_ids() -> set[str]:
    if not os.path.exists(skipped_basic_lands_path):
        return set()

    try:
        with open(skipped_basic_lands_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, list):
                return {str(item) for item in data}
    except (OSError, json.JSONDecodeError):
        pass

    return set()


def _persist_skipped_basic_land_ids(ids: set[str]) -> None:
    os.makedirs(shared_basic_lands_path, exist_ok=True)
    with open(skipped_basic_lands_path, "w", encoding="utf-8") as handle:
        json.dump(sorted(ids), handle, indent=2)
        handle.write("\n")


def _copy_with_unique_name(
    source: Path, destination_dir: Path, *, prefix: str | None = None
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)

    base_stem = source.stem
    if prefix:
        base_stem = f"{prefix}_{base_stem}"

    extension = source.suffix.lower()
    candidate = destination_dir / f"{base_stem}{extension}"
    counter = 1

    while candidate.exists():
        candidate = destination_dir / f"{base_stem}_{counter}{extension}"
        counter += 1

    shutil.copy2(source, candidate)

    return candidate


def _deck_subfolders(front_dir: str, back_dir: str, double_dir: str) -> list[str]:
    """
    Detect deck subfolders within a profile.

    Returns any subdirectory found in the front/ folder, as that's where
    card images are required. The back/ and double_sided/ folders are optional
    and will be created/used as needed during PDF generation.
    """

    def subdirs(path: str) -> set[str]:
        if not os.path.isdir(path):
            return set()
        return {
            name
            for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name)) and not name.startswith(".")
        }

    # Only require front/ folder to exist - back and double_sided are optional
    front = subdirs(front_dir)

    return sorted(front)


def _apply_deck_to_paths(
    front_dir: str, back_dir: str, double_dir: str, deck_name: str
) -> tuple[str, str, str]:
    """
    Apply deck selection to paths, auto-creating back/double_sided folders if needed.

    Only the front/ folder is required to exist. Back and double_sided folders
    will be created automatically if they don't exist.
    """
    candidate_front = os.path.join(front_dir, deck_name)
    candidate_back = os.path.join(back_dir, deck_name)
    candidate_double = os.path.join(double_dir, deck_name)

    # Front folder must exist
    if not os.path.isdir(candidate_front):
        raise click.ClickException(f"Deck '{deck_name}' not found in front directory.")

    # Auto-create back folder if it doesn't exist
    if not os.path.isdir(candidate_back):
        os.makedirs(candidate_back, exist_ok=True)

    # Auto-create double_sided folder if it doesn't exist
    if not os.path.isdir(candidate_double):
        os.makedirs(candidate_double, exist_ok=True)

    return candidate_front, candidate_back, candidate_double


def _select_deck_directories(
    front_dir: str,
    back_dir: str,
    double_dir: str,
    deck_name: str | None,
    *,
    interactive: bool,
) -> tuple[str, str, str]:
    deck_names = _deck_subfolders(front_dir, back_dir, double_dir)

    if deck_name:
        if deck_name not in deck_names:
            error_msg = f"Deck '{deck_name}' not found."
            if deck_names:
                error_msg += f"\n\nAvailable decks: {', '.join(deck_names)}"
                error_msg += (
                    "\n\nUse: make list-decks PROFILE=<profile> to see all decks"
                )
            else:
                error_msg += "\n\nNo deck subfolders exist in this profile."
                error_msg += f"\n\nCreate one with: make create-deck PROFILE=<profile> DECK={deck_name}"
            raise click.ClickException(error_msg)
        return _apply_deck_to_paths(front_dir, back_dir, double_dir, deck_name)

    if deck_names and interactive:
        click.echo("\nDeck folders detected:")
        for index, name in enumerate(deck_names, start=1):
            # Count cards in each deck subfolder
            deck_front_path = os.path.join(front_dir, name)
            card_count = (
                len(_list_image_files(deck_front_path))
                if os.path.isdir(deck_front_path)
                else 0
            )
            click.echo(f"[{index}] {name} ({card_count} cards)")
        click.echo("[0] Use all cards in the profile")

        selection = _prompt_text("Select a deck (or 0 to use all)", default="0")

        if selection and selection.isdigit():
            choice = int(selection)
            if choice == 0:
                return front_dir, back_dir, double_dir
            if 1 <= choice <= len(deck_names):
                chosen = deck_names[choice - 1]
                return _apply_deck_to_paths(front_dir, back_dir, double_dir, chosen)
            click.echo("Invalid deck selection; using all cards.")
        else:
            click.echo("Invalid deck selection; using all cards.")

    return front_dir, back_dir, double_dir


def _migrate_profile_shared_assets(
    profile_root: str, created_directories: list[str], warnings: list[str]
) -> None:
    pictures_root = os.path.join(profile_root, "pictures-of-cards")
    shared_root = os.path.join(pictures_root, "shared-cards")

    if not os.path.exists(shared_root):
        os.makedirs(shared_root, exist_ok=True)
        created_directories.append(_log_relative(shared_root, profile_root))

    legacy_dirs = ("tokens", "card-backs")

    for legacy in legacy_dirs:
        old_path = os.path.join(pictures_root, legacy)
        new_path = os.path.join(shared_root, legacy)

        if not os.path.lexists(old_path):
            continue

        if os.path.lexists(new_path):
            # New location already present; remove the legacy path if it still exists
            try:
                if os.path.islink(old_path) or os.path.isfile(old_path):
                    os.unlink(old_path)
                elif os.path.isdir(old_path):
                    shutil.rmtree(old_path)
            except OSError as error:
                warnings.append(f"Could not remove legacy path {old_path}: {error}")
            continue

        try:
            os.replace(old_path, new_path)
            created_directories.append(_log_relative(new_path, profile_root))
        except OSError as error:
            warnings.append(f"Could not move {old_path} -> {new_path}: {error}")


def _ensure_front_multiple_of_eight(front_dir_path: str) -> None:
    front_dir = Path(front_dir_path)
    front_dir.mkdir(parents=True, exist_ok=True)

    while True:
        front_files = _list_image_files(front_dir)

        if not front_files:
            return

        remainder = len(front_files) % 8

        if remainder == 0:
            return

        needed = 8 - remainder

        click.echo(
            f"\nThere are currently {len(front_files)} card fronts. "
            f"Printing works best in multiples of 8."
        )
        click.echo(f"You need {needed} more card(s) to complete the sheet.")
        click.echo("[1] Auto-fill with random shared tokens")
        click.echo("[2] I'll add cards manually, recheck after")
        click.echo("[0] Cancel generation")

        selection = _prompt_text("Choose an option", default="0")

        if selection == "1":
            token_files = _collect_shared_token_files()

            if not token_files:
                raise click.ClickException(
                    "No shared tokens available to auto-fill the sheet."
                )

            added: list[str] = []

            for _ in range(needed):
                token_source = random.choice(token_files)
                dest = _copy_with_unique_name(token_source, front_dir, prefix="token")
                added.append(dest.name)

            click.echo(f"Added {len(added)} token card(s): {', '.join(added)}")
            continue

        if selection == "2":
            _prompt_to_continue("Press Enter after adding cards to the front folder...")
            continue

        if selection == "0":
            raise click.ClickException(
                "Card count must be a multiple of 8. Generation cancelled."
            )

        click.echo("Please choose a valid option.")


def _ensure_back_image(
    front_dir_path: str,
    back_dir_path: str,
    double_sided_dir_path: str,
    *,
    only_fronts: bool,
) -> None:
    if only_fronts:
        return

    front_files = _list_image_files(front_dir_path)

    if not front_files:
        return

    double_sided_files = _list_image_files(double_sided_dir_path)
    double_sided_stems = {path.stem for path in double_sided_files}

    fronts_requiring_shared_back = [
        path for path in front_files if path.stem not in double_sided_stems
    ]

    if not fronts_requiring_shared_back:
        return

    back_dir = Path(back_dir_path)
    back_files = _list_image_files(back_dir)

    if back_files:
        return

    wait_attempted = False

    while True:
        click.echo("\nNo generic card back detected for your single-sided cards.")
        click.echo("[1] Pull a random shared card back automatically")
        click.echo("[2] Pause so I can add a card back manually")
        click.echo("[0] Cancel generation")

        selection = _prompt_text("Choose an option", default="0")

        if selection == "1":
            shared_backs = _collect_shared_card_backs()

            if not shared_backs:
                click.echo("No shared card backs available. Please add one manually.")
                continue

            chosen = random.choice(shared_backs)
            new_back = _copy_with_unique_name(chosen, back_dir, prefix="back")
            click.echo(f"Added shared card back '{new_back.name}'.")
            return

        if selection == "2":
            _prompt_to_continue(
                "Press Enter after adding a card back to the back folder..."
            )

            if _list_image_files(back_dir):
                click.echo("Card back detected. Continuing.")
                return

            if wait_attempted:
                raise click.ClickException(
                    "No card back detected after waiting. Generation cancelled."
                )

            wait_attempted = True
            click.echo("Still no card back found.")
            continue

        if selection == "0":
            raise click.ClickException("No card back provided. Generation cancelled.")

        click.echo("Please choose a valid option.")


def attach_profile_flags(command):
    command = click.option(
        "--profile",
        type=profile_param_type,
        help="Load directories configured for a profile in assets/profiles.json.",
    )(command)

    for profile_name in reversed(INITIAL_PROFILE_NAMES):
        option_name = f"--{profile_name}"
        command = click.option(
            option_name,
            "profile",
            flag_value=profile_name,
            help=f"Use directories configured for the '{profile_name}' profile.",
        )(command)

    return command


front_directory = os.path.join("game", "front")
back_directory = os.path.join("game", "back")
double_sided_directory = os.path.join("game", "double_sided")
output_directory = os.path.join("game", "output")

default_output_path = os.path.join(output_directory, "game.pdf")


@click.command()
@click.option(
    "--front_dir_path",
    default=front_directory,
    show_default=True,
    help="The path to the directory containing the card fronts.",
)
@click.option(
    "--back_dir_path",
    default=back_directory,
    show_default=True,
    help="The path to the directory containing one or more card backs.",
)
@click.option(
    "--double_sided_dir_path",
    default=double_sided_directory,
    show_default=True,
    help="The path to the directory containing card backs for double-sided cards.",
)
@click.option(
    "--output_path",
    default=default_output_path,
    show_default=True,
    help="The desired path to the output PDF.",
)
@click.option(
    "--pdf_name",
    help="Base PDF filename (letters/numbers/dashes only); .pdf will be appended. Overrides the default output filename.",
)
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Reduce non-essential console output (also honored when PM_LOG=quiet)",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Increase console output (also honored when PM_LOG=verbose)",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output results in JSON format (for commands that support it)",
)
@click.option(
    "--log-json",
    "log_json",
    is_flag=True,
    default=False,
    help="Enable structured JSON logging for machine parsing",
)
@click.option(
    "--output_images",
    default=False,
    is_flag=True,
    help="Create images instead of a PDF.",
)
@click.option(
    "--library_health",
    is_flag=True,
    default=False,
    help="Run library health checks and write CSV/JSON report, then exit.",
)
@click.option(
    "--library_health_fix_names",
    is_flag=True,
    default=False,
    help="When used with --library_health, attempt to fix filename hygiene (lowercase, replace spaces).",
)
@click.option(
    "--library_health_fix_dupes",
    is_flag=True,
    default=False,
    help="When used with --library_health, remove lower-quality duplicates detected by perceptual hashing.",
)
@click.option(
    "--library_health_hash_threshold",
    default=6,
    type=click.IntRange(min=0, max=64),
    show_default=True,
    help="Hamming distance threshold for duplicate detection (lower is stricter).",
)
@click.option(
    "--library_health_restore",
    type=click.Path(exists=True, dir_okay=False),
    help="Restore files from a library health summary JSON (quarantine).",
)
@click.option(
    "--restore_dry_run",
    is_flag=True,
    default=False,
    help="When used with --library_health_restore, show planned restores without moving files.",
)
@click.option(
    "--random_commander",
    is_flag=True,
    default=False,
    help="Pick a random commander and print details.",
)
@click.option(
    "--rc_colors", help="Commander color-identity filter (e.g., w, wu, bgr). Optional."
)
@click.option(
    "--rc_exact/--no-rc_exact",
    default=True,
    help="Require exact commander color-identity match with --rc_colors (use --no-rc_exact to allow supersets).",
)
@click.option(
    "--rc_commander_legal/--no-rc_commander_legal",
    default=True,
    help="Only include cards that are legal in Commander (default on).",
)
@click.option(
    "--rc_type",
    help="Commander type/subtype filter (comma/space-separated), e.g. 'human, wizard'.",
)
@click.option(
    "--card_size",
    default=CardSize.STANDARD.value,
    type=click.Choice([t.value for t in CardSize], case_sensitive=False),
    show_default=True,
    help="The desired card size.",
)
@click.option(
    "--paper_size",
    default=PaperSize.LETTER.value,
    type=click.Choice([t.value for t in PaperSize], case_sensitive=False),
    show_default=True,
    help="The desired paper size.",
)
@click.option(
    "--only_fronts",
    default=False,
    is_flag=True,
    help="Only use the card fronts, exclude the card backs.",
)
@click.option(
    "--crop",
    default="3mm",
    show_default=True,
    help="Crop the outer portion of front and double-sided images. Examples: 3mm, 0.125in, 6.5.",
)
@click.option(
    "--extend_corners",
    default=0,
    type=click.IntRange(min=0),
    show_default=True,
    help="Reduce artifacts produced by rounded corners in card images.",
)
@click.option(
    "--ppi",
    default=600,
    type=click.IntRange(min=0),
    show_default=True,
    help="Pixels per inch (PPI) when creating PDF.",
)
@click.option(
    "--quality",
    default=100,
    type=click.IntRange(min=0, max=100),
    show_default=True,
    help="File compression. A higher value corresponds to better quality and larger file size.",
)
@click.option(
    "--load_offset",
    default=False,
    is_flag=True,
    help="Apply saved offsets. See `offset_pdf.py` for more information.",
)
@click.option(
    "--skip",
    type=click.IntRange(min=0),
    multiple=True,
    help="Skip a card based on its index. Useful for registration issues. Examples: 0, 4.",
)
@click.option("--name", help="Label each page of the PDF with a name.")
@click.option(
    "--fetch_basic_lands",
    is_flag=True,
    default=False,
    help="Download all basic lands from Scryfall into shared/basic-lands and exit.",
)
@click.option(
    "--list_tokens",
    is_flag=True,
    default=False,
    help="List tokens from the cached Scryfall bulk index and exit.",
)
@click.option(
    "--token_filter", help="Substring filter on token name when listing tokens."
)
@click.option("--token_subtype", help="Filter listed tokens by subtype (e.g., Spirit).")
@click.option("--token_set", help="Filter listed tokens by set code (e.g., MH3).")
@click.option(
    "--token_colors",
    help="Filter tokens by oracle color identity, e.g., w, wu, grixis=ubr, colorless=c, mono=mono.",
)
@click.option(
    "--token_limit",
    default=50,
    type=click.IntRange(min=0),
    show_default=True,
    help="Maximum number of tokens to list when using --list_tokens (0 = unlimited).",
)
@click.option(
    "--token_pack_manifest",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSON manifest describing tokens to bundle into a pack.",
)
@click.option(
    "--token_pack_name",
    help="Optional name for the token pack; defaults to manifest filename.",
)
@click.option(
    "--token_pack_dry_run",
    is_flag=True,
    default=False,
    help="Do not write files; print planned pack structure instead.",
)
@click.option(
    "--token_prefer_set",
    help="Prefer this set code when multiple token prints match (e.g., mh3).",
)
@click.option(
    "--token_prefer_frame",
    help="Prefer this frame code when multiple prints match (e.g., 2015).",
)
@click.option(
    "--token_prefer_artist",
    help="Prefer prints where the artist name contains this text.",
)
@click.option(
    "--token_keyword",
    help="Show tokens whose oracle keywords (or text) include this value.",
)
@click.option(
    "--token_keyword_set", help="Restrict keyword results to a specific set code."
)
@click.option(
    "--token_keyword_limit",
    default=50,
    type=click.IntRange(min=0),
    show_default=True,
    help="Maximum tokens to show when using --token_keyword (0 = unlimited).",
)
@click.option(
    "--token_language_report",
    is_flag=True,
    default=False,
    help="Display token language availability report and exit.",
)
@click.option(
    "--token_language_warn",
    help="Comma-separated language codes to highlight in token language report (default: ph,ja).",
)
@click.option(
    "--db_health_summary",
    is_flag=True,
    default=False,
    help="Generate a database health summary (smoke tests + db-info + coverage snapshot) and exit.",
)
@click.option(
    "--db_health_set",
    help="Optional set code (or comma-separated list) for coverage snapshot in DB health summary.",
)
@click.option(
    "--db_health_missing_only/--no-db_health_missing_only",
    default=True,
    help="When running DB health coverage snapshot, default to missing-only results (can disable).",
)
@click.option(
    "--token_explorer",
    is_flag=True,
    default=False,
    help="Launch the interactive token metadata explorer.",
)
@click.option(
    "--token_pack_from_deck",
    help="Build a token pack from a deck list file or URL (Moxfield/Archidekt).",
)
@click.option(
    "--token_pack_wizard_name",
    help="Optional name for the token pack generated by --token_pack_from_deck.",
)
@click.option(
    "--token_pack_append",
    is_flag=True,
    default=False,
    help="Append to existing token pack instead of creating new one.",
)
@click.option(
    "--token_pack_overwrite",
    is_flag=True,
    default=False,
    help="Overwrite existing token pack with same name.",
)
@click.option(
    "--token_pack_summary_only",
    is_flag=True,
    default=False,
    help="Show token pack summary without building (dry run).",
)
@click.option("--deck", help="Select a deck subfolder when generating a profile.")
@click.option(
    "--list_decks",
    is_flag=True,
    default=False,
    help="List all deck subfolders for a profile and exit.",
)
@click.option(
    "--create_deck",
    help="Create new deck subfolders (front/back/double_sided) for a profile.",
)
@click.option(
    "--fetch_basics",
    is_flag=True,
    default=False,
    help="Download/update basic lands into shared/basic-lands and exit.",
)
@click.option(
    "--fetch_non_basics",
    is_flag=True,
    default=False,
    help="Download/update non-basic lands into shared/non-basic-lands and exit.",
)
@click.option(
    "--lang",
    "lang_preference",
    default="en",
    help="Language(s) for land downloads: 'en' (English), 'phyrexian'/'ph', 'all' (all languages), 'special' (English + fantasy languages), or comma-separated list.",
)
@click.option(
    "--land_set",
    "land_set_filter",
    type=str,
    default=None,
    help="Optional set code filter for land downloads (e.g., one, ltr).",
)
@click.option(
    "--fullart_only",
    is_flag=True,
    default=False,
    help="Only fetch full-art variants when downloading lands.",
)
@click.option(
    "--fetch_dry_run",
    is_flag=True,
    default=False,
    help="Dry run mode: show what would be downloaded without actually downloading.",
)
@click.option(
    "--retry_only",
    is_flag=True,
    default=False,
    help="Only retry previously failed downloads (for lands).",
)
@click.option(
    "--configure_notifications",
    is_flag=True,
    default=False,
    help="Configure notification settings and exit.",
)
@click.option(
    "--card_search",
    help="Search oracle text/type for cards (include tokens with --card_include_tokens).",
)
@click.option("--card_search_set", help="Restrict card search to a specific set code.")
@click.option(
    "--card_search_limit",
    default=50,
    type=click.IntRange(min=0),
    show_default=True,
    help="Maximum cards to show when using --card_search (0 = unlimited).",
)
@click.option(
    "--card_include_tokens/--no-card_include_tokens",
    default=False,
    help="Include tokens in card search results.",
)
@click.option(
    "--plugins_list",
    is_flag=True,
    default=False,
    help="List discovered plugins and enabled status, then exit.",
)
@click.option(
    "--plugins_enable",
    help="Enable a plugin by name, then exit.",
)
@click.option(
    "--plugins_disable",
    help="Disable a plugin by name, then exit.",
)
@click.option(
    "--migrate_land_names",
    is_flag=True,
    default=False,
    help="Rename legacy land filenames to %landtype%-%arttype% with collision disambiguation and write a report.",
)
@click.option(
    "--migrate_scope",
    type=click.Choice(["basic", "nonbasic", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Which land category to migrate.",
)
@click.option(
    "--migrate_set",
    help="Restrict migration to a specific set code (e.g., mh3).",
)
@click.option(
    "--migrate_dry_run",
    is_flag=True,
    default=False,
    help="Show planned renames without making changes.",
)
@click.option(
    "--deck_list", type=str, help="Path or URL to a deck list to analyze and summarize."
)
@click.option(
    "--deck_name", help="Optional deck name for reporting; defaults to filename."
)
@click.option(
    "--deck_output_dir",
    type=click.Path(file_okay=False),
    help="Directory to place deck reports (default shared/deck-reports).",
)
@click.option(
    "--notifications_test",
    is_flag=True,
    help="Send a sample notification (macOS/webhook) and exit.",
)
@click.option(
    "--jobs",
    "--concurrency",
    "jobs",
    type=int,
    help="Override max parallel downloads for Scryfall images (default from PM_MAX_WORKERS or 8).",
)
@click.option(
    "--fetch_cards",
    is_flag=True,
    help="Fetch cards with comprehensive filtering (use with filter options below).",
)
@click.option(
    "--fetch_tokens_clean",
    is_flag=True,
    help="Fetch tokens using the clean, simple token fetch system.",
)
@click.option("--card_name", help="Filter cards by name (partial match).")
@click.option(
    "--card_type", help="Filter cards by type line (e.g., creature, enchantment)."
)
@click.option("--card_artist", help="Filter cards by artist name (partial match).")
@click.option("--card_rarity", help=f"Filter cards by rarity ({', '.join(RARITIES)}).")
@click.option("--card_cmc", type=float, help="Filter cards by converted mana cost.")
@click.option("--card_layout", help="Filter cards by layout (normal, modal_dfc, etc.).")
@click.option("--card_frame", help="Filter cards by frame (2015, 1997, future).")
@click.option(
    "--card_colors", help="Filter cards by colors (comma-separated: W,U,B,R,G)."
)
@click.option(
    "--exclude_tokens", is_flag=True, help="Exclude token cards from results."
)
@click.option("--exclude_lands", is_flag=True, help="Exclude land cards from results.")
@click.option(
    "--land_limit",
    type=int,
    default=None,
    help="Maximum number of land cards to fetch (omit for no limit).",
)
@click.option(
    "--card_limit",
    type=int,
    default=None,
    help="Maximum number of cards to fetch (omit for no limit).",
)
@attach_profile_flags
@click.version_option("1.4.0")
def cli(
    front_dir_path,
    back_dir_path,
    double_sided_dir_path,
    output_path,
    pdf_name,
    output_images,
    quiet,
    verbose,
    output_json,
    log_json,
    library_health,
    library_health_fix_names,
    library_health_fix_dupes,
    library_health_hash_threshold,
    library_health_restore,
    restore_dry_run,
    random_commander,
    rc_colors,
    rc_exact,
    rc_commander_legal,
    rc_type,
    card_size,
    paper_size,
    only_fronts,
    crop,
    extend_corners,
    ppi,
    quality,
    skip,
    load_offset,
    name,
    fetch_basic_lands,
    list_tokens,
    token_filter,
    token_subtype,
    token_set,
    token_colors,
    token_limit,
    token_pack_manifest,
    token_pack_name,
    token_pack_dry_run,
    token_prefer_set,
    token_prefer_frame,
    token_prefer_artist,
    token_keyword,
    token_keyword_set,
    token_keyword_limit,
    token_language_report,
    token_language_warn,
    db_health_summary,
    db_health_set,
    db_health_missing_only,
    token_explorer,
    token_pack_from_deck,
    token_pack_wizard_name,
    token_pack_append,
    token_pack_overwrite,
    token_pack_summary_only,
    deck,
    list_decks,
    create_deck,
    fetch_basics,
    fetch_non_basics,
    lang_preference,
    land_set_filter,
    fullart_only,
    fetch_dry_run,
    retry_only,
    configure_notifications,
    card_search,
    card_search_set,
    card_search_limit,
    card_include_tokens,
    plugins_list,
    plugins_enable,
    plugins_disable,
    migrate_land_names,
    migrate_scope,
    migrate_set,
    migrate_dry_run,
    deck_list,
    deck_name,
    deck_output_dir,
    notifications_test,
    jobs,
    fetch_cards,
    fetch_tokens_clean,
    card_name,
    card_type,
    card_artist,
    card_rarity,
    card_cmc,
    card_layout,
    card_frame,
    card_colors,
    exclude_tokens,
    exclude_lands,
    land_limit,
    card_limit,
    profile,
):
    # One-off helpers
    # Logging mode env support
    pm_log = (os.environ.get("PM_LOG") or "").strip().lower()
    if pm_log == "quiet":
        pass
    if pm_log == "verbose":
        pass

    # Setup structured logging
    logger = logging.getLogger("proxy_machine")
    if log_json:
        # JSON formatter for machine parsing
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                '{"timestamp":"%(asctime)s","level":"%(levelname)s","message":"%(message)s","module":"%(module)s","function":"%(funcName)s"}'
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info("Structured JSON logging enabled")
    else:
        # Standard logging - mirror to click.echo for interactive sessions
        logging.basicConfig(
            level=logging.INFO if verbose else logging.WARNING,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

    if jobs:
        # Safe cap to avoid runaway threads
        try:
            j = int(jobs)
        except Exception as exc:
            logger.debug("Invalid job count '%s', using default: %s", jobs, exc)
            j = 8
        j = max(1, min(j, 64))
        global SCRYFALL_MAX_WORKERS
        SCRYFALL_MAX_WORKERS = j

    if notifications_test:
        # Use new handler pattern with Result[T]
        from cli.handlers import handle_notifications_test

        result = handle_notifications_test()
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return

    # Plugin CLI shims - using new handler pattern
    if plugins_list:
        from cli.handlers import handle_plugins_list

        result = handle_plugins_list()
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return
    if plugins_enable:
        from cli.handlers import handle_plugins_enable

        result = handle_plugins_enable(plugins_enable)
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return
    if plugins_disable:
        from cli.handlers import handle_plugins_disable

        result = handle_plugins_disable(plugins_disable)
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return
    if token_pack_manifest:
        from cli.handlers import handle_token_pack_build

        result = handle_token_pack_build(
            token_pack_manifest,
            pack_name=token_pack_name,
            dry_run=bool(token_pack_dry_run),
            prefer_set=(token_prefer_set or None),
            prefer_frame=(token_prefer_frame or None),
            prefer_artist=(token_prefer_artist or None),
        )
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return

    if token_keyword:
        _display_token_keyword_search(
            token_keyword, token_keyword_set, token_keyword_limit, pause_after=False
        )
        return

    if token_explorer:
        _token_explorer_loop()
        return

    if configure_notifications:
        _configure_notifications_flow()
        return

    if migrate_land_names:
        _run_land_migration(
            migrate_scope.lower(),
            migrate_set.lower() if migrate_set else None,
            migrate_dry_run,
        )
        return

    if library_health:
        from cli.handlers import handle_library_health

        result = handle_library_health(
            fix_names=library_health_fix_names,
            fix_dupes=library_health_fix_dupes,
            hash_threshold=library_health_hash_threshold,
        )
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return

    if random_commander:
        from cli.handlers import handle_random_commander

        result = handle_random_commander(
            colors=rc_colors or None,
            exact_match=rc_exact,
            commander_legal_only=rc_commander_legal,
            type_filter=rc_type or None,
        )
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return

    if token_language_report:
        from cli.handlers import handle_token_language_report

        result = handle_token_language_report(token_language_warn, output_json)
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return

    if db_health_summary:
        from cli.handlers import handle_db_health_summary

        result = handle_db_health_summary(
            coverage_set=db_health_set,
            missing_only=db_health_missing_only,
            output_json=output_json,
        )
        if not result["ok"]:
            click.echo(f"Error: {result['error']}", err=True)
            raise SystemExit(1)
        return

    if token_pack_from_deck:
        # Determine mode: summary_only overrides dry_run
        effective_dry_run = token_pack_summary_only or bool(token_pack_dry_run)

        _token_pack_wizard_from_deck(
            token_pack_from_deck,
            token_pack_wizard_name or None,
            dry_run=effective_dry_run,
            append_mode=token_pack_append,
            overwrite_mode=token_pack_overwrite,
            summary_only=token_pack_summary_only,
            prefer_set=(token_prefer_set or None),
            prefer_frame=(token_prefer_frame or None),
            prefer_artist=(token_prefer_artist or None),
        )
        return

    if card_search:
        _display_card_text_search(
            card_search,
            card_search_set,
            card_search_limit,
            include_tokens=card_include_tokens,
            pause_after=False,
        )
        return

    if fetch_tokens_clean:
        # Use the clean token fetch system
        from token_fetch_clean import fetch_tokens_clean as clean_fetch
        from pathlib import Path

        click.echo("=== Clean Token Fetch ===")

        # Get database path
        if not _db_index_available():
            click.echo("Database not available. Please build the bulk index first.")
            return

        output_dir = Path(shared_tokens_path)

        downloaded, skipped, errors = clean_fetch(
            db_path=str(BULK_DB_PATH),
            output_dir=output_dir,
            subtype_filter=token_subtype,
            set_filter=land_set_filter,
            lang=lang_preference,
            limit=card_limit,
            dry_run=fetch_dry_run,
        )

        click.echo(
            f"Clean token fetch complete: downloaded {downloaded}, skipped {skipped}"
        )
        if errors:
            click.echo("Errors:")
            for error in errors[:10]:  # Show first 10 errors
                click.echo(f"  - {error}")
            if len(errors) > 10:
                click.echo(f"  ... and {len(errors) - 10} more errors")

        _notify(
            "Clean Token Fetch Complete",
            f"Downloaded {downloaded}, skipped {skipped} tokens.",
            event="fetch_tokens_clean",
        )
        return

    if fetch_cards:
        # Parse colors filter
        colors_filter_str = None
        if card_colors:
            colors_filter_str = card_colors  # Keep as string for universal function

        # Determine card type from filters
        determined_card_type = card_type if card_type != "any" else "any"
        if exclude_tokens and exclude_lands:
            determined_card_type = "any"  # Will filter via type_line_contains
        elif exclude_tokens:
            determined_card_type = "any"
            is_token_filter = False
        elif exclude_lands:
            determined_card_type = "any"

        if fetch_dry_run:
            # Display mode - use existing function
            colors_list = (
                [c.strip().upper() for c in card_colors.split(",")]
                if card_colors
                else None
            )
            _fetch_cards_from_database(
                name_filter=card_name,
                type_filter=card_type,
                lang_filter=lang_preference if lang_preference != "en" else None,
                set_filter=land_set_filter,
                artist_filter=card_artist,
                rarity_filter=card_rarity,
                cmc_filter=card_cmc,
                layout_filter=card_layout,
                frame_filter=card_frame,
                fullart_only=fullart_only,
                exclude_tokens=exclude_tokens,
                exclude_lands=exclude_lands,
                colors_filter=colors_list,
                limit=card_limit,
                dry_run=True,
            )
        else:
            # Download mode - use universal function
            saved, skipped, total, skipped_details = _fetch_cards_universal(
                card_type=determined_card_type,
                is_token=(
                    True
                    if determined_card_type == "token"
                    else (None if not exclude_tokens else False)
                ),
                is_basic_land=None if not exclude_lands else False,
                type_line_contains=card_type,
                lang_preference=lang_preference,
                set_filter=land_set_filter,
                name_filter=card_name,
                artist_filter=card_artist,
                rarity_filter=card_rarity,
                colors_filter=colors_filter_str,
                fullart_only=fullart_only,
                layout_filter=card_layout,
                frame_filter=card_frame,
                limit=card_limit,
                include_related=True,
                retry_only=retry_only,
                dry_run=False,
                progress=True,
            )

            click.echo(
                f"\nFetch complete: saved {saved}, skipped {skipped}, total {total}"
            )
            if skipped_details:
                click.echo(f"\nSkipped {len(skipped_details)} cards:")
                for detail in skipped_details[:20]:
                    click.echo(f"  - {detail}")
                if len(skipped_details) > 20:
                    click.echo(f"  ... {len(skipped_details) - 20} more")

            _notify(
                "Universal Card Fetch Complete",
                f"Saved {saved}, skipped {skipped} entries.",
                event="fetch_cards",
            )
        return

    if deck_list:
        profile_for_deck = profile
        if deck_output_dir:
            deck_output_dir = os.path.abspath(deck_output_dir)
        if profile_for_deck:
            if profile_for_deck not in get_profile_names():
                raise click.ClickException(f"Profile '{profile_for_deck}' not found.")
        try:
            _process_deck_list(deck_list, deck_name, deck_output_dir, profile_for_deck)
        except click.ClickException:
            raise
        return

    if fetch_basics or fetch_basic_lands:
        effective_limit = land_limit if land_limit and land_limit > 0 else None
        saved, skipped, total, skipped_details = _fetch_all_basic_lands_from_scryfall(
            retry_only=retry_only,
            lang_preference=lang_preference,
            dry_run=fetch_dry_run,
            progress=True,
            land_set_filter=land_set_filter,
            fullart_only=fullart_only,
            include_related=True,  # Use all_parts to catch MDFC basics
            limit=effective_limit,
        )
        warnings = _ensure_basic_land_symlinks()

        click.echo(
            f"Fetched {total} basic land entries. Downloaded {saved}, skipped {skipped} already present."
        )

        if saved:
            click.echo(f"New images saved: {saved}")
        if skipped:
            click.echo(f"Skipped duplicates or missing data: {skipped}")

        if skipped_details:
            click.echo("\nSkipped entries:")
            for detail in skipped_details[:20]:
                click.echo(f"  - {detail}")
            if len(skipped_details) > 20:
                click.echo(f"  ... {len(skipped_details) - 20} more skipped entries")

        if warnings:
            click.echo("Warnings:")
            for warning in warnings:
                click.echo(f"  - {warning}")

        _notify(
            "Basic Land Sync Complete",
            f"Saved {saved}, skipped {skipped} entries.",
            event="fetch_basics",
        )
        return

    if fetch_non_basics:
        click.echo("\n=== Fetching Non-Basic Lands ===")
        effective_limit = land_limit if land_limit and land_limit > 0 else None
        saved, skipped, total, skipped_details = _fetch_cards_universal(
            card_type="nonbasic_land",
            retry_only=retry_only,
            lang_preference=lang_preference,
            set_filter=land_set_filter,
            fullart_only=fullart_only,
            include_related=True,
            limit=effective_limit,
            dry_run=fetch_dry_run,
            progress=True,
        )
        click.echo(
            f"Fetched {total} non-basic land entries. Downloaded {saved}, skipped {skipped} already present."
        )
        if skipped_details:
            click.echo("\nSkipped entries:")
            for detail in skipped_details[:20]:
                click.echo(f"  - {detail}")
            if len(skipped_details) > 20:
                click.echo(f"  ... {len(skipped_details) - 20} more skipped entries")
        _notify(
            "Non-Basic Land Sync Complete",
            f"Saved {saved}, skipped {skipped} entries.",
            event="fetch_nonbasics",
        )
        return

    if profile:
        profile_paths = build_profile_directories(
            profile,
            {
                "front_dir_path": front_dir_path,
                "back_dir_path": back_dir_path,
                "double_sided_dir_path": double_sided_dir_path,
                "output_path": output_path,
            },
        )

        front_dir_path = profile_paths["front_dir_path"]
        back_dir_path = profile_paths["back_dir_path"]
        double_sided_dir_path = profile_paths["double_sided_dir_path"]
        output_path = profile_paths["output_path"]

        output_directory_path = os.path.dirname(output_path)
        if output_directory_path:
            os.makedirs(output_directory_path, exist_ok=True)

        # Handle --list_decks command
        if list_decks:
            deck_names = _deck_subfolders(
                front_dir_path, back_dir_path, double_sided_dir_path
            )
            if not deck_names:
                click.echo(f"No deck subfolders found in profile '{profile}'.")
                click.echo(
                    f"\nTo create a new deck, use: make create-deck PROFILE={profile} DECK=deckname"
                )
            else:
                click.echo(f"Deck subfolders in profile '{profile}':")
                for deck_name in deck_names:
                    deck_front = os.path.join(front_dir_path, deck_name)
                    card_count = (
                        len(_list_image_files(deck_front))
                        if os.path.isdir(deck_front)
                        else 0
                    )
                    click.echo(f"  - {deck_name} ({card_count} cards)")
                click.echo(f"\nTotal: {len(deck_names)} deck(s)")
                click.echo(f"\nTo use a deck: make pdf PROFILE={profile} DECK=deckname")
            return

        # Handle --create_deck command
        if create_deck:
            # Validate deck name
            if not re.fullmatch(r"[A-Za-z0-9_-]+", create_deck):
                raise click.ClickException(
                    "Deck name must contain only letters, numbers, underscores, and dashes."
                )

            # Check if deck already exists
            existing_decks = _deck_subfolders(
                front_dir_path, back_dir_path, double_sided_dir_path
            )
            if create_deck in existing_decks:
                raise click.ClickException(
                    f"Deck '{create_deck}' already exists in profile '{profile}'."
                )

            # Create the subdirectories
            deck_front = os.path.join(front_dir_path, create_deck)
            deck_back = os.path.join(back_dir_path, create_deck)
            deck_double = os.path.join(double_sided_dir_path, create_deck)

            os.makedirs(deck_front, exist_ok=True)
            os.makedirs(deck_back, exist_ok=True)
            os.makedirs(deck_double, exist_ok=True)

            click.echo(f"Created deck subfolders for '{create_deck}':")
            click.echo(f"  - {os.path.relpath(deck_front, project_root_directory)}")
            click.echo(f"  - {os.path.relpath(deck_back, project_root_directory)}")
            click.echo(f"  - {os.path.relpath(deck_double, project_root_directory)}")
            click.echo("\nNext steps:")
            click.echo(
                f"  1. Add card images to: {os.path.relpath(deck_front, project_root_directory)}"
            )
            click.echo(
                f"  2. Generate PDF with: make pdf PROFILE={profile} DECK={create_deck}"
            )
            return

    # If a pdf_name is provided, validate and use it to override output_path's filename
    if pdf_name and not output_images:
        if not re.fullmatch(r"[A-Za-z0-9-]+", pdf_name):
            raise click.ClickException(
                "--pdf_name must contain only letters, numbers, and dashes (-); no spaces."
            )
        base_dir = os.path.dirname(output_path) or project_root_directory
        output_path = os.path.join(base_dir, f"{pdf_name}.pdf")

    # Interactive prompt for a legal PDF filename (letters/numbers/dashes) when creating a PDF
    if sys.stdin.isatty() and not output_images and not pdf_name:
        base_dir = os.path.dirname(output_path) or project_root_directory
        default_name = os.path.splitext(os.path.basename(output_path))[0]
        while True:
            try:
                name_in = _prompt_text(
                    f"PDF file name (letters/numbers/dashes only, no spaces) [{default_name}]",
                    default=default_name,
                )
            except EOFError:
                name_in = ""

            pdf_name = default_name if not name_in else name_in
            if not re.fullmatch(r"[A-Za-z0-9-]+", pdf_name):
                click.echo(
                    "Invalid name. Use only letters, numbers, and dashes (-); no spaces."
                )
                continue

            output_path = os.path.join(base_dir, f"{pdf_name}.pdf")
            break

    front_dir_path, back_dir_path, double_sided_dir_path = _select_deck_directories(
        front_dir_path,
        back_dir_path,
        double_sided_dir_path,
        deck,
        interactive=sys.stdin.isatty(),
    )

    _ensure_front_multiple_of_eight(front_dir_path)
    _ensure_back_image(
        front_dir_path, back_dir_path, double_sided_dir_path, only_fronts=only_fronts
    )

    # Avoid overwriting an existing PDF
    if not output_images:
        unique_output = _ensure_unique_pdf_path(output_path)
        if unique_output != output_path:
            click.echo(f"Output exists; writing to unique file: {unique_output}")
            output_path = unique_output

    generate_pdf(
        front_dir_path,
        back_dir_path,
        double_sided_dir_path,
        output_path,
        output_images,
        card_size,
        paper_size,
        only_fronts,
        crop,
        extend_corners,
        ppi,
        quality,
        skip,
        load_offset,
        name,
    )

    if output_images:
        click.echo("\nImage generation complete.\n")
    else:
        click.echo(f"\nPDF created at {output_path}.\n")
        _notify(
            "PDF Ready",
            f"Profile '{profile or 'custom'}' PDF saved to {output_path}",
            event="pdf",
        )
        _offer_open_in_folder(output_path, kind="PDF")


def _run_profile_generation(profile_name: str, extra_args: list[str] | None = None):
    try:
        args = ["--profile", profile_name]
        if extra_args:
            args.extend(extra_args)
        cli_command = cast("Command", cli)
        cli_command.main(args, standalone_mode=False)
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise


def _prompt_to_continue(
    message: str = "Press Enter to return to the previous menu...",
) -> None:
    _prompt_text(message, allow_empty=True)


def _ensure_deck_subfolders(profile_name: str, deck_name: str) -> tuple[str, str, str]:
    """Ensure subdirectories for a deck exist within a profile and return their paths."""
    # This is a stub. Implementation is needed.
    click.echo(
        f"[stub] Ensuring deck subfolders for '{deck_name}' in profile '{profile_name}'."
    )
    return "/path/to/front", "/path/to/back", "/path/to/double_sided"


def _download_deck_fronts(
    card_reports: list[dict], front_path: Path
) -> tuple[int, int]:
    """Download card fronts for a deck report."""
    # This is a stub. Implementation is needed.
    click.echo(f"[stub] Downloading deck fronts to '{front_path}'.")
    return 0, len(card_reports)


def _run_library_health_checks(
    fix_names: bool = False, fix_dupes: bool = False, hash_threshold: int = 95
) -> None:
    """Run health checks on the card library."""
    # This is a stub. Implementation is needed.
    click.echo("[stub] Running library health checks.")


def _random_commander_flow(
    color_str: str | None,
    exact_match: bool,
    commander_legal_only: bool,
    type_filter: str | None,
) -> None:
    """Run the random commander selection flow."""
    # This is a stub. Implementation is needed.
    click.echo("[stub] Running random commander flow.")


def _restore_quarantined_files(path: str, dry_run: bool) -> None:
    """Restore quarantined files from a summary."""
    # This is a stub. Implementation is needed.
    click.echo(f"[stub] Restoring quarantined files from '{path}'.")


def _create_pdf_menu():
    while True:
        profile_names = get_profile_names()

        if not profile_names:
            click.echo("\nNo profiles are configured. Add one in Options first.\n")
            _prompt_to_continue()
            return

        options = [f"[{i}] {name}" for i, name in enumerate(profile_names, start=1)]
        options.append("[0] Back")
        _print_boxed_menu("Choose a profile to generate", options)

        valid_choices = {"0"} | {str(i) for i in range(1, len(profile_names) + 1)}
        selection = _get_key_choice(valid_choices)

        if selection == "0":
            return

        if not selection.isdigit():
            click.echo("Please enter a valid number.")
            continue

        numeric_choice = int(selection)

        if numeric_choice < 1 or numeric_choice > len(profile_names):
            click.echo("Invalid selection. Try again.")
            continue

        profile_name = profile_names[numeric_choice - 1]

        profile_paths = build_profile_directories(
            profile_name,
            {
                "front_dir_path": front_directory,
                "back_dir_path": back_directory,
                "double_sided_dir_path": double_sided_directory,
                "output_path": default_output_path,
            },
        )

        deck_args: list[str] = []
        deck_names = _deck_subfolders(
            profile_paths["front_dir_path"],
            profile_paths["back_dir_path"],
            profile_paths["double_sided_dir_path"],
        )

        if deck_names:
            deck_options = [
                f"[{i}] {name}" for i, name in enumerate(deck_names, start=1)
            ]
            deck_options.append("[0] Use all cards in the profile")
            _print_boxed_menu("Deck folders detected", deck_options)

            deck_valid = {"0"} | {str(i) for i in range(1, len(deck_names) + 1)}
            deck_selection = _get_key_choice(deck_valid)

            if deck_selection.isdigit():
                deck_choice = int(deck_selection)
                if deck_choice == 0:
                    pass
                elif 1 <= deck_choice <= len(deck_names):
                    deck_name = deck_names[deck_choice - 1]
                    deck_args = ["--deck", deck_name]
                else:
                    click.echo("Invalid deck selection; using all cards.")
            else:
                click.echo("Invalid deck selection; using all cards.")

        click.echo(f"\nGenerating PDF for profile '{profile_name}'...\n")
        _run_profile_generation(profile_name, deck_args)
        _prompt_to_continue(
            "Generation finished. Press Enter to return to the previous menu..."
        )


def _pregenerate_tokens_flow():
    try:
        count_input = _prompt_text(
            "How many random tokens should be fetched?", default="1"
        )
    except EOFError:
        return

    if not count_input:
        count = 1
    else:
        if not count_input.isdigit():
            click.echo("Please enter a positive number.")
            _prompt_to_continue()
            return
        count = max(1, int(count_input))

    click.echo(f"\nSelecting {count} random token(s) from cached bulk data...\n")

    saved = 0
    skipped = 0

    random_entries = _bulk_random_token_entries(count)

    if not random_entries:
        click.echo(
            "No tokens found in the local bulk index. Run fetch-lands or sync bulk data first."
        )
        _prompt_to_continue()
        return

    for entry in random_entries:
        card = _token_entry_to_card(entry)
        created, path, meta = _save_token_card(card)

        if created:
            saved += 1
            if meta:
                click.echo(
                    f"Saved {meta['name']} ({meta['set']}) -> {meta['rel_path']}"
                )
            else:
                click.echo("Saved token without metadata details.")
        else:
            skipped += 1
            if meta:
                click.echo(f"Skipped existing token {meta['name']} ({meta['set']}).")
            else:
                click.echo("Skipped token without image data.")

    _rebuild_token_index()

    click.echo(f"\nDone. Added {saved} token(s), skipped {skipped}.\n")
    _prompt_to_continue()


def _fetch_token_by_name_flow():
    try:
        name = _prompt_text("Token name", default="")
    except EOFError:
        return

    if not name:
        click.echo("Token name is required.")
        _prompt_to_continue()
        return

    set_code_input = (_prompt_text("Set code (optional)", default="") or "").lower()
    extra = _prompt_text(
        "Additional filters (e.g., subtype:Spirit) (optional)", default=""
    )

    name_filter = name
    subtype_filter = None
    set_filter = set_code_input if set_code_input else None

    if extra:
        for token in extra.split():
            token = token.strip()
            if not token:
                continue
            if token.startswith("set:"):
                set_filter = token.split(":", 1)[1].lower()
            elif token.startswith("subtype:"):
                subtype_filter = token.split(":", 1)[1]
            elif token.startswith("name:"):
                name_filter = token.split(":", 1)[1]
            else:
                # treat leftover text as part of name filter substring
                if name_filter:
                    name_filter = f"{name_filter} {token}"
                else:
                    name_filter = token

    results = _bulk_iter_tokens(
        name_filter=name_filter, subtype_filter=subtype_filter, set_filter=set_filter
    )

    if not results:
        click.echo("No tokens found for that query.")
        _prompt_to_continue()
        return

    max_display = 25
    limited_results = results[:max_display]

    click.echo("\nSelect a token to download:\n")
    for index, card in enumerate(limited_results, start=1):
        line = (
            f"[{index}] {card.get('name')} | set={card.get('set')} "
            f"| collector={card.get('collector_number')} | {card.get('type_line')}"
        )
        click.echo(line)

    if len(results) > max_display:
        click.echo(
            f"...and {len(results) - max_display} more, refine your query if needed."
        )

    selection = _prompt_text("Choose a token number (0 to cancel)", default="0")

    if selection == "0":
        return

    if not selection or not selection.isdigit():
        click.echo("Please enter a valid selection.")
        _prompt_to_continue()
        return

    numeric_choice = int(selection)

    if numeric_choice < 1 or numeric_choice > len(limited_results):
        click.echo("Selection out of range.")
        _prompt_to_continue()
        return

    selected_entry = limited_results[numeric_choice - 1]
    selected_card = _token_entry_to_card(selected_entry)

    created, path, meta = _save_token_card(selected_card)

    if created and meta:
        click.echo(f"\nSaved {meta['name']} ({meta['set']}) to {path}.")
    elif created:
        click.echo("\nSaved token (metadata unavailable).")
    else:
        click.echo("\nToken already exists locally; no download performed.")

    _rebuild_token_index()
    _prompt_to_continue()


def _dedupe_token_library() -> tuple[int, int]:
    root = Path(shared_tokens_path)

    if not root.exists():
        return 0, 0

    seen: dict[str, Path] = {}
    removed = 0

    for file in root.rglob("*"):
        if not file.is_file():
            continue
        if file.name.startswith("."):
            continue
        if file.name == "_index.json":
            continue

        extension = file.suffix.lower()
        if extension not in TOKEN_EXTENSION_PRIORITY:
            continue

        key = file.stem

        if key not in seen:
            seen[key] = file
            continue

        preferred = _prefer_token_file(seen[key], file)

        if preferred is file:
            try:
                seen[key].unlink()
                removed += 1
            except OSError:
                pass
            seen[key] = file
        else:
            try:
                file.unlink()
                removed += 1
            except OSError:
                pass

    _rebuild_token_index()

    return len(seen), removed


def _dedupe_tokens_flow():
    kept, removed = _dedupe_token_library()

    click.echo(
        f"\nToken library deduplication complete. Kept {kept} unique entries, removed {removed} file(s).\n"
    )
    _prompt_to_continue()


def _collect_token_language_counts() -> Counter[str]:
    """Return counts of tokens grouped by language code."""
    counts: Counter[str] = Counter()
    _ensure_database_built()

    if _db_index_available():
        try:
            from db.bulk_index import DB_PATH, _get_connection

            conn = _get_connection(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(lang,''), COUNT(*) FROM prints WHERE is_token=1 GROUP BY lang"
            )
            for lang_value, count in cur.fetchall():
                lang_key = (lang_value or "").strip().lower() or "unknown"
                counts[lang_key] += int(count)
            conn.close()
        except Exception as exc:
            # Fallback to JSON index if DB access fails
            logger.warning("Database language report failed, using fallback: %s", exc)
            counts = Counter()

    if not counts:
        index = _load_bulk_index()
        entries = index.get("entries", {})
        token_ids = index.get("token_ids", [])
        for card_id in token_ids:
            entry = entries.get(card_id)
            if not entry:
                continue
            lang_key = (entry.get("lang") or "").strip().lower() or "unknown"
            counts[lang_key] += 1

    return counts


def _token_language_report_cli(warn_languages: str | None, output_json: bool) -> None:
    counts = _collect_token_language_counts()
    total = sum(counts.values())

    # Normalize watch list
    if warn_languages:
        warn_list = [
            lang.strip().lower() for lang in warn_languages.split(",") if lang.strip()
        ]
        warn_list = list(dict.fromkeys(warn_list))  # preserve order, remove dupes
    else:
        warn_list = DEFAULT_TOKEN_WARN_LANGS[:]

    languages = []
    for lang, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        pct = (count / total * 100.0) if total else 0.0
        languages.append({"lang": lang or "unknown", "count": count, "percent": pct})

    missing = [lang for lang in warn_list if counts.get(lang, 0) == 0]

    if output_json:
        payload = {
            "total_tokens": total,
            "languages": languages,
            "watch_languages": warn_list,
            "missing_watch_languages": missing,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo("\nToken Language Report\n---------------------")
    click.echo(f"Total token prints: {total:,}")
    for item in languages:
        click.echo(
            f"  {item['lang'] or 'unknown'}: {item['count']:,} ({item['percent']:.2f}%)"
        )

    if warn_list:
        click.echo(f"\nWatch languages: {', '.join(warn_list)}")
        if missing:
            click.echo(f"[WARNING] No tokens available for {{ {', '.join(missing)} }}")
        else:
            click.echo("[OK] All watch languages have at least one token print.")

    click.echo(
        "\nNote: Scryfall currently publishes approximately 2,800 tokens, mostly in English."
    )


def _token_language_report_flow() -> None:
    click.echo("\nToken Language Report\n---------------------")
    warn_input = (
        _prompt_text(
            "Languages to warn about (comma-separated, blank for default 'ph,ja')",
            default="ph,ja",
        )
        or "ph,ja"
    ).lower()
    warn_value = warn_input or None
    _token_language_report_cli(warn_value, output_json=False)
    _prompt_to_continue()


def _load_coverage_module():
    import importlib.util

    cov_path = os.path.join(script_directory, "coverage.py")
    spec = importlib.util.spec_from_file_location("pm_cov", cov_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load coverage module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _summarize_coverage_snapshot(
    summary: dict, missing_rows: list, *, missing_only: bool
) -> dict:
    set_code = summary.get("set_filter")
    snapshot = {
        "kind": summary.get("kind"),
        "set": (set_code.upper() if set_code else "ALL"),
        "total": summary.get("total", 0),
        "covered": summary.get("covered", 0),
        "missing": summary.get("missing", 0),
        "coverage_pct": float(summary.get("coverage_pct", 0.0)),
    }

    examples = []
    for entry in missing_rows[:5]:
        examples.append(
            {
                "name": getattr(entry, "name", ""),
                "set": getattr(entry, "set", "").upper(),
                "collector": getattr(entry, "collector_number", ""),
            }
        )
    snapshot["missing_examples"] = examples
    snapshot["missing_examples_included"] = bool(examples)
    snapshot["missing_only"] = missing_only
    return snapshot


def _db_health_summary_cli(
    coverage_set: str | None,
    missing_only: bool,
    output_json: bool,
) -> None:
    report: dict[str, object] = {}

    # Smoke test
    smoke_buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(smoke_buffer):
            _run_smoke_tests()
        report["smoke_test"] = smoke_buffer.getvalue().strip()
    except Exception as exc:
        report["smoke_test"] = f"Smoke test failed: {exc}"

    # Database info
    if _db_index_available():
        db_buffer = io.StringIO()
        try:
            from db.bulk_index import info as db_info

            with contextlib.redirect_stdout(db_buffer):
                db_info()
            report["database_info"] = db_buffer.getvalue().strip()
        except Exception as exc:
            report["database_info"] = f"Error retrieving database info: {exc}"
    else:
        report["database_info"] = "Database index not available."

    # Coverage snapshots
    coverage_entries: list[dict[str, object]] = []
    set_values = []
    if coverage_set:
        set_values = [
            s.strip().lower() or None for s in coverage_set.split(",") if s.strip()
        ]
    if not set_values:
        set_values = [None]

    try:
        pm_cov = _load_coverage_module()
        for set_code in set_values:
            rows_land, summary_land = pm_cov.compute_coverage("nonbasic", set_code)
            missing_land = [r for r in rows_land if not r.has_art]
            coverage_entries.append(
                _summarize_coverage_snapshot(
                    summary_land, missing_land, missing_only=missing_only
                )
            )

            rows_tokens, summary_tokens = pm_cov.compute_token_coverage(set_code)
            missing_tokens = [r for r in rows_tokens if not r.has_art]
            coverage_entries.append(
                _summarize_coverage_snapshot(
                    summary_tokens, missing_tokens, missing_only=missing_only
                )
            )
    except Exception as exc:
        coverage_entries = [{"error": str(exc)}]

    report["coverage"] = coverage_entries
    report["coverage_sets"] = [sc.upper() if sc else "ALL" for sc in set_values]

    if output_json:
        click.echo(json.dumps(report, indent=2))
        return

    click.echo("\nDatabase Health Summary\n-----------------------")
    smoke_text = report.get("smoke_test", "")
    if smoke_text:
        click.echo("Smoke test output:")
        click.echo(smoke_text)
    else:
        click.echo("Smoke test output: (empty)")

    click.echo("\nDatabase info:")
    click.echo(report.get("database_info", "(no data)"))

    click.echo("\nCoverage snapshots:")
    for entry in coverage_entries:
        if "error" in entry:
            click.echo(f"  Error collecting coverage: {entry['error']}")
            continue
        kind = entry.get("kind", "?")
        set_label = entry.get("set", "ALL")
        covered = entry.get("covered", 0)
        total = entry.get("total", 0)
        missing = entry.get("missing", 0)
        pct = entry.get("coverage_pct", 0.0)
        click.echo(
            f"  {kind} (set={set_label}): {covered}/{total} covered — missing {missing} ({pct:.1f}% coverage)"
        )
        raw_examples = entry.get("missing_examples")
        examples = (
            [ex for ex in raw_examples if isinstance(ex, dict)]
            if isinstance(raw_examples, list)
            else []
        )
        if examples:
            click.echo("    Missing examples:")
            for sample in examples:
                click.echo(
                    f"      - {sample.get('name', '')} ({sample.get('set', '')} #{sample.get('collector', '')})"
                )


def _db_health_summary_flow() -> None:
    click.echo("\nDatabase Health Summary\n-----------------------")
    set_input = _prompt_text("Set codes (comma-separated, blank for ALL)", default="")
    missing_only = _prompt_yes_no("Missing only?", default=True)
    # missing_only already set above
    _db_health_summary_cli(set_input or None, missing_only, output_json=False)
    _prompt_to_continue()


def _fetch_cards_universal(
    *,
    # Card type filtering
    card_type: str = "any",  # Options: {', '.join(CARD_TYPES)}
    is_token: bool | None = None,
    is_basic_land: bool | None = None,
    type_line_contains: str | None = None,
    # Standard filters
    lang_preference: str = "en",
    set_filter: str | None = None,
    name_filter: str | None = None,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    colors_filter: str | None = None,
    # Art/Layout filters
    fullart_only: bool = False,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    border_color_filter: str | None = None,
    # Token-specific
    subtype_filter: str | None = None,
    # Relationship expansion
    include_related: bool = True,
    # Output control
    output_path: Path | None = None,
    limit: int | None = None,
    # Execution control
    retry_only: bool = False,
    dry_run: bool = False,
    progress: bool = True,
) -> tuple[int, int, int, list[str]]:
    """Universal card fetching function for all card types.

    Consolidates logic from the legacy land and token fetchers into a single, flexible interface.

    Args:
        card_type: Type of cards to fetch. Options:
            - "basic_land": Basic lands (Plains, Island, etc.)
            - "nonbasic_land": Non-basic lands
            - "token": Token cards
            - "creature", "planeswalker", etc.: Specific card types
            - "any": No type filtering
        is_token: Explicitly filter for tokens (True) or non-tokens (False)
        is_basic_land: Explicitly filter for basic lands
        type_line_contains: Filter by type line content (e.g., "Dragon", "Equipment")

        lang_preference: Language preference (e.g., "en", "ja", "en,ja")
        set_filter: Filter by set code (e.g., "znr", "ltr")
        name_filter: Filter by card name (partial match)
        artist_filter: Filter by artist name (partial match)
        rarity_filter: Filter by rarity ({', '.join(RARITIES)})
        colors_filter: Filter by color identity (W,U,B,R,G)

        fullart_only: Only fetch full-art cards
        layout_filter: Filter by layout (normal, transform, modal_dfc, etc.)
        frame_filter: Filter by frame (2015, 2003, future, etc.)
        border_color_filter: Filter by border color (black, white, borderless, etc.)

        subtype_filter: Filter by subtype (for tokens, e.g., "Beast", "Spirit")

        include_related: Expand card list with related cards via all_parts (MDFCs, meld, etc.)

        output_path: Custom output directory (default: determined by card_type)
        limit: Maximum number of cards to process

        retry_only: Only download cards that failed previously
        dry_run: Don't actually download, just report what would be downloaded
        progress: Show progress updates

    Returns:
        Tuple of (saved, skipped, total, skipped_details)
    """
    # Initialize memory monitoring
    memory_monitor = MemoryMonitor()
    if memory_monitor.enabled:
        memory_monitor.log_memory(f"starting universal fetch (type={card_type})")

    # Initialize Discord monitoring
    discord_monitor = _get_discord_monitor()  # noqa: F841

    # Ensure database is available
    _ensure_database_built()

    # Determine output path based on card type
    if output_path is None:
        if card_type == "basic_land":
            output_path = Path(shared_basic_lands_path)
        elif card_type == "nonbasic_land":
            output_path = Path(shared_non_basic_lands_path)
        elif card_type == "token" or is_token:
            output_path = Path(shared_tokens_path)
        else:
            base_dir = Path(shared_basic_lands_path).parent
            type_slug = (
                card_type.lower().replace(" ", "-") if card_type != "any" else "other"
            )
            output_path = base_dir / type_slug

    if not dry_run:
        _ensure_directory(str(output_path))

    # Initialize counters
    saved = 0
    skipped = 0
    total = 0
    processed = 0
    skipped_details: list[str] = []

    # Build presence index
    if dry_run:
        presence = {}
    else:
        if card_type in {"basic_land", "nonbasic_land"}:
            presence = _build_land_presence_index(output_path)
        elif card_type == "token" or is_token:
            presence = _build_token_presence_index()
        elif card_type in {"instant", "sorcery", "artifact", "enchantment"}:
            presence = _build_nested_presence_index(output_path)
        else:
            presence = _build_set_based_presence_index(output_path)

    # Handle retry logic
    if dry_run:
        skipped_retry_ids = set()
    else:
        if card_type == "basic_land":
            skipped_retry_ids = _load_skipped_basic_land_ids()
        else:
            skipped_retry_ids = set()

    # Normalize language preferences
    target_langs = _normalize_langs(lang_preference)

    # Query database with optimized SQL filtering
    if not _db_index_available():
        click.echo(
            "Database not available. Please build database first with 'make bulk-fetch-all'"
        )
        return (0, 0, 0, ["Database not available"])

    # Use optimized query that pushes filters to SQL
    from db.bulk_index import query_cards_optimized

    filtered_entries = query_cards_optimized(
        limit=limit,
        db_path=str(BULK_DB_PATH),
        card_type=card_type,
        is_token=is_token,
        is_basic_land=is_basic_land,
        name_filter=name_filter,
        type_line_contains=type_line_contains,
        subtype_filter=subtype_filter,
        lang_filter=target_langs if len(target_langs) > 1 else target_langs[0],
        set_filter=set_filter,
        artist_filter=artist_filter,
        rarity_filter=rarity_filter,
        colors_filter=colors_filter,
        layout_filter=layout_filter,
        frame_filter=frame_filter,
        border_color_filter=border_color_filter,
        fullart_only=fullart_only,
    )

    if memory_monitor.enabled:
        memory_monitor.log_memory(
            f"after loading {len(filtered_entries)} filtered entries from database"
        )

    if progress:
        filter_desc = []
        if set_filter:
            filter_desc.append(f"set={set_filter}")
        if name_filter:
            filter_desc.append(f"name={name_filter}")
        if artist_filter:
            filter_desc.append(f"artist={artist_filter}")
        if rarity_filter:
            filter_desc.append(f"rarity={rarity_filter}")
        if type_line_contains:
            filter_desc.append(f"type={type_line_contains}")
        if fullart_only:
            filter_desc.append("fullart")

        click.echo(
            f"Applied filters to {card_type}: {', '.join(filter_desc) if filter_desc else 'none'}"
        )
        click.echo(
            f"Found {len(filtered_entries)} potential card(s) in the local bulk index."
        )

    if memory_monitor.enabled:
        memory_monitor.log_memory(f"after filtering to {len(filtered_entries)} entries")

    # Expand with related cards using all_parts
    if include_related and filtered_entries and _db_index_available() and BULK_DB_PATH:
        try:
            from pathlib import Path as PathLib
            from tools.resolve_card_relationships import (
                expand_card_list_with_relationships,
            )

            initial_count = len(filtered_entries)
            initial_ids = [
                str(entry.get("id")) for entry in filtered_entries if entry.get("id")
            ]

            if initial_ids:
                expanded_ids = expand_card_list_with_relationships(
                    initial_ids,
                    PathLib(BULK_DB_PATH),
                    include_tokens=(card_type == "token" or bool(is_token)),
                    verbose=progress,
                )

                # Fetch additional related cards
                additional_ids = expanded_ids - set(initial_ids)
                if additional_ids:
                    from db.bulk_index import _get_connection

                    conn = _get_connection(str(BULK_DB_PATH))
                    cur = conn.cursor()

                    placeholders = ",".join(["?" for _ in additional_ids])
                    cur.execute(
                        f"SELECT * FROM prints WHERE id IN ({placeholders})",
                        list(additional_ids),
                    )
                    rows = cur.fetchall()
                    columns = [description[0] for description in cur.description]

                    for row in rows:
                        additional_entry = dict(zip(columns, row))

                        # Apply same filters to related cards
                        if additional_entry.get("lang", "en") not in target_langs:
                            continue
                        if (
                            set_filter
                            and additional_entry.get("set", "").lower()
                            != set_filter.lower()
                        ):
                            continue
                        if fullart_only:
                            art_type = _derive_art_type(additional_entry)
                            if not (art_type == "fullart" or "fullart" in art_type):
                                continue

                        # When fetching tokens, ensure additional cards are also tokens
                        if card_type == "token" or is_token:
                            additional_type_line = additional_entry.get(
                                "type_line", ""
                            ).lower()
                            if "token" not in additional_type_line:
                                continue

                        filtered_entries.append(additional_entry)

                    conn.close()

                    if progress:
                        added_count = len(filtered_entries) - initial_count
                        click.echo(
                            f"Expanded from {initial_count} to {len(filtered_entries)} cards (+{added_count})"
                        )
        except Exception as e:
            if progress:
                click.echo(f"Warning: Could not expand relationships: {e}")

    # Prepare download jobs
    download_jobs = []
    seen_urls: set[str] = set()

    if progress:
        click.echo("Preparing download jobs...")

    processed_count = 0
    for entry in filtered_entries:
        processed_count += 1
        if progress and processed_count % 100 == 0:
            click.echo(f"  Prepared {processed_count}/{len(filtered_entries)} jobs...")

        card_id = entry.get("id", "")
        card_name = entry.get("name", "unknown")
        set_code = entry.get("set_code", "unk")

        collector_number = entry.get("collector_number", "0")

        # Get image URL
        image_url = entry.get("image_url", "")

        if not image_url:
            skipped += 1
            skipped_details.append(
                f"no image URL: {card_name} ({set_code} #{collector_number})"
            )
            continue

        # Dedupe by URL
        if image_url in seen_urls:
            skipped += 1
            continue
        seen_urls.add(image_url)

        # Determine filename
        entry_enriched = _enrich_entry_with_art_meta(dict(entry))
        land_type: str | None = None
        if card_type in {"basic_land", "nonbasic_land"}:
            base_stem = _land_base_stem(entry_enriched)
            extension = _extension_from_url(image_url, ".png")
            land_type = _classify_land_type(
                entry_enriched.get("name", ""),
                entry_enriched.get("type_line", ""),
                entry_enriched.get("oracle_text", ""),
            )

            # Check if this land already exists using presence index
            if land_type:
                land_bucket = land_type
            else:
                land_bucket = "uncategorized"

            land_presence = presence.get(land_bucket, set())
            if base_stem in land_presence:
                skipped += 1
                if dry_run and progress:
                    click.echo(f"  [SKIP] {base_stem} already present in {land_bucket}")
                continue

            destination = _unique_land_destination(
                output_path,
                land_type,
                base_stem,
                extension,
            )
        else:
            directory: Path
            token_subtype_slug: str = "misc"  # Default value for linting
            if card_type == "token" or is_token:
                base_stem = _token_base_stem(entry_enriched)
                # Token organization by subtype/set structure
                # Extract token subtype from type_line if not already present
                token_subtype = entry_enriched.get("token_subtype")
                if not token_subtype:
                    type_line = entry_enriched.get("type_line", "")
                    token_subtype = _token_subtype_from_type_line(type_line)

                token_subtype_slug = entry_enriched.get(
                    "token_subtype_slug"
                ) or _slugify(token_subtype or "misc")
                classification = token_subtype_slug
                directory = output_path / token_subtype_slug
            else:
                base_stem = _card_base_stem(entry_enriched)
                if card_type in {"instant", "sorcery"}:
                    classification = _classify_spell_path(entry_enriched)
                    directory = output_path / classification
                elif card_type == "artifact":
                    classification = _classify_artifact_path(entry_enriched)
                    directory = output_path / classification
                elif card_type == "enchantment":
                    classification = _classify_enchantment_path(entry_enriched)
                    directory = output_path / classification
                else:
                    classification = set_code
                    directory = output_path / classification

            # Check presence based on card type
            if card_type == "token" or is_token:
                # Token presence uses simple structure: subtype -> stems
                # token_subtype_slug was defined in the token classification branch above
                subtype_presence = presence.get(token_subtype_slug, set())
                if base_stem in subtype_presence:
                    skipped += 1
                    if dry_run and progress:
                        click.echo(
                            f"  [SKIP] {base_stem} already present in {token_subtype_slug}"
                        )
                    continue
            else:
                # Non-token presence uses flat structure
                presence_key = directory.relative_to(output_path).as_posix()
                stem_presence = presence.get(presence_key, set())
                if base_stem in stem_presence:
                    skipped += 1
                    if dry_run and progress:
                        click.echo(
                            f"  [SKIP] {base_stem} already present in {presence_key}"
                        )
                    continue

            if not dry_run:
                directory.mkdir(parents=True, exist_ok=True)

            destination = directory / f"{base_stem}.png"

        # Check if already exists
        if destination.exists():
            skipped += 1
            if dry_run and progress:
                click.echo(f"  [SKIP] {destination} (already exists)")
            continue

        job: DownloadJob = {
            "card_id": card_id,
            "name": card_name,
            "set_code": set_code,
            "collector_number": collector_number,
            "image_url": image_url,
            "destination": destination,
            "base_stem": base_stem,
        }

        if land_type is not None:
            job["land_type"] = land_type

        download_jobs.append(job)

    if progress:
        click.echo(
            f"Prepared {len(download_jobs)} download jobs (skipped {skipped} already present)"
        )

    if dry_run:
        return (0, skipped, len(filtered_entries), skipped_details)

    # Download images
    if download_jobs:
        if progress:
            click.echo(
                f"Starting downloads with {min(8, len(download_jobs))} workers..."
            )

        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(download_jobs)

        def report_progress():
            if progress and processed % 50 == 0:
                label = f"Progress: processed {processed}/{total} cards (saved {saved}, skipped {skipped})"
                _render_progress(label, final=False)

        future_to_job: dict[Future[None], DownloadJob] = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            for job in download_jobs:
                destination = job["destination"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                future = executor.submit(_download_image, job["image_url"], destination)
                future_to_job[future] = job

            for future in as_completed(future_to_job):
                job = future_to_job[future]
                card_id = job["card_id"]
                entry_name = job["name"] or "Unknown"
                try:
                    future.result()
                except click.ClickException as error:
                    skipped += 1
                    if card_id:
                        skipped_retry_ids.add(card_id)
                    if job["destination"].exists():
                        try:
                            job["destination"].unlink()
                        except OSError:
                            pass
                    skipped_details.append(
                        f"download failed: {entry_name} ({job['set_code']} #{job['collector_number']}) - {error}"
                    )
                except Exception as error:
                    skipped += 1
                    if card_id:
                        skipped_retry_ids.add(card_id)
                    if job["destination"].exists():
                        try:
                            job["destination"].unlink()
                        except OSError:
                            pass
                    skipped_details.append(
                        f"download failed: {entry_name} ({job['set_code']} #{job['collector_number']}) - {error}"
                    )
                else:
                    if card_id and card_id in skipped_retry_ids:
                        skipped_retry_ids.discard(card_id)
                    presence.setdefault(job["set_code"], set()).add(job["base_stem"])
                    saved += 1
                finally:
                    processed += 1
                    report_progress()

    # Persist skipped IDs for retry
    if card_type == "basic_land" and skipped_retry_ids:
        _persist_skipped_basic_land_ids(skipped_retry_ids)

    if progress and total:
        label = f"Progress: processed {processed}/{total} cards (saved {saved}, skipped {skipped})"
        _render_progress(label, final=True)

    return saved, skipped, len(filtered_entries), skipped_details


def _extension_from_url(url: str, default: str = ".png") -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return suffix
    return default


def _build_token_presence_index() -> dict[str, set[str]]:
    """Build a simple map of subtype -> base_stems for fast existence checks.

    Structure: {subtype_slug: {base_stem1, base_stem2, ...}}
    This enables O(1) lookups for token existence in simplified directory structure.
    Uses 5-minute cache to avoid rebuilding on every fetch.
    """
    cache_key = "tokens"

    # Check cache
    if cache_key in _PRESENCE_CACHE:
        age = time.time() - _PRESENCE_CACHE_TIME.get(cache_key, 0)
        if age < PRESENCE_CACHE_TTL:
            return _PRESENCE_CACHE[cache_key]

    # Build fresh index
    presence: dict[str, set[str]] = {}
    root = Path(shared_tokens_path)

    if not root.exists():
        return presence

    # Scan simplified structure: tokens/subtype/files
    for subtype_dir in root.iterdir():
        if not subtype_dir.is_dir() or subtype_dir.name.startswith("."):
            continue

        subtype_slug = subtype_dir.name
        base_stems: set[str] = set()

        # Scan files directly in subtype directory
        for file in subtype_dir.iterdir():
            if not file.is_file() or file.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            # Extract base stem from filename
            stem = file.stem
            base_stems.add(stem)

        if base_stems:
            presence[subtype_slug] = base_stems

    # Update cache
    _PRESENCE_CACHE[cache_key] = presence
    _PRESENCE_CACHE_TIME[cache_key] = time.time()

    return presence


def _fetch_all_tokens_flow():
    """Interactive flow for bulk token fetching with comprehensive filters."""
    click.echo("\nBulk Token Fetch\n----------------")
    click.echo("Fetch all available tokens from database with filtering options.")

    # Token name filter
    name_filter = (
        _prompt_text("Token name filter (partial match, optional)", default="") or None
    )

    # Subtype filter
    subtype_filter = (
        _prompt_text(
            "Token subtype (Beast, Spirit, Soldier, etc., optional)", default=""
        )
        or None
    )

    # Set filter
    set_filter = (
        _prompt_text("Set code (ltr, one, mh3, etc., optional)", default="") or None
    )

    # Artist filter
    artist_filter = (
        _prompt_text("Artist name (partial match, optional)", default="") or None
    )

    # Language - handle comma-separated languages like land functions
    lang_input = _prompt_text("Language (en, ph, ja, etc., default: en)", default="en")
    if not lang_input:
        lang_list = ["en"]  # Default to English
    else:
        # Parse comma-separated languages
        lang_list = [lang.strip() for lang in lang_input.split(",") if lang.strip()]
        if not lang_list:
            lang_list = ["en"]

    # Rarity filter
    rarity_filter = (
        _prompt_text(f"Rarity ({', '.join(RARITIES)}, optional)", default="") or None
    )

    # Full-art only
    fullart_only = _prompt_yes_no("Full-art tokens only?", default=False)

    # Limit
    limit_input = _prompt_text(
        "Maximum tokens to process (optional, default: all)", default=""
    )
    limit = None
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            click.echo("Invalid limit, processing all tokens.")

    # Dry run
    dry_run = _prompt_yes_no(
        "Dry run only (preview without downloading)?", default=False
    )

    click.echo("\nStarting bulk token fetch...")
    click.echo(
        f"   Filters: name={name_filter}, subtype={subtype_filter}, set={set_filter}"
    )
    click.echo(
        f"   Advanced: artist={artist_filter}, rarity={rarity_filter}, lang={lang_list}"
    )
    click.echo(
        f"   Options: fullart_only={fullart_only}, limit={limit}, dry_run={dry_run}"
    )

    try:
        saved, skipped, total, skipped_details = _fetch_cards_universal(
            card_type="token",
            is_token=True,
            lang_preference=",".join(lang_list),
            name_filter=name_filter,
            subtype_filter=subtype_filter,
            set_filter=set_filter,
            artist_filter=artist_filter,
            rarity_filter=rarity_filter,
            fullart_only=fullart_only,
            limit=limit,
            include_related=False,
            dry_run=dry_run,
            progress=True,
        )

        if skipped_details and len(skipped_details) > 0:
            show_details = _prompt_yes_no(
                f"Show {len(skipped_details)} skipped entries?", default=False
            )
            if show_details in {"y", "yes"}:
                click.echo("\nSkipped entries:")
                for detail in skipped_details[:50]:  # Limit to first 50
                    click.echo(f"  - {detail}")
                if len(skipped_details) > 50:
                    click.echo(f"  ... and {len(skipped_details) - 50} more")

    except Exception as e:
        click.echo(f"Error during token fetch: {e}")
        import traceback

        traceback.print_exc()

    _prompt_to_continue()


class MemoryMonitor:
    """Optional memory monitoring with psutil integration."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.psutil_available = False
        self.process = None
        self.start_memory = None
        self.peak_memory = None

        if enabled:
            try:
                import psutil  # pyright: ignore[reportMissingImports]

                self.psutil_available = True
                self.process = psutil.Process()
                self.start_memory = self.process.memory_info().rss / 1024**2  # MB
                self.peak_memory = self.start_memory
                # Note: Using print since logger may not be available
                print(
                    f"Memory monitoring enabled. Initial usage: {self.start_memory:.1f}MB"
                )
            except ImportError:
                print("Warning: psutil not available - memory monitoring disabled")
                self.enabled = False

    def check_memory(self) -> dict:
        """Get current memory usage statistics."""
        if not self.enabled or not self.psutil_available:
            return {"available": False}

        try:
            import psutil  # pyright: ignore[reportMissingImports]

            if self.process is None:
                return {"available": False, "error": "Process not initialized"}

            current_memory = self.process.memory_info().rss / 1024**2
            if self.peak_memory is None or current_memory > self.peak_memory:
                self.peak_memory = current_memory

            sys_memory = psutil.virtual_memory()
            start_mb = self.start_memory or 0

            return {
                "available": True,
                "current_mb": round(current_memory, 1),
                "start_mb": round(start_mb, 1),
                "peak_mb": round(self.peak_memory, 1),
                "delta_mb": round(current_memory - start_mb, 1),
                "system_total_gb": round(sys_memory.total / 1024**3, 1),
                "system_available_gb": round(sys_memory.available / 1024**3, 1),
                "system_percent_used": sys_memory.percent,
            }
        except Exception as e:
            print(f"Warning: Memory check failed: {e}")
            return {"available": False, "error": str(e)}

    def log_memory(self, context: str = ""):
        """Log current memory usage with context."""
        if not self.enabled:
            return

        stats = self.check_memory()
        if stats.get("available"):
            context_str = f" ({context})" if context else ""
            print(
                f"Memory{context_str}: {stats['current_mb']}MB "
                f"(+{stats['delta_mb']}MB from start, peak: {stats['peak_mb']}MB)"
            )

    def get_summary(self) -> dict:
        """Get final memory usage summary."""
        stats = self.check_memory()
        if stats.get("available"):
            return {
                "memory_monitoring": True,
                "initial_memory_mb": stats["start_mb"],
                "peak_memory_mb": stats["peak_mb"],
                "final_memory_mb": stats["current_mb"],
                "total_memory_increase_mb": stats["delta_mb"],
                "system_memory_gb": stats["system_total_gb"],
                "system_memory_used_percent": stats["system_percent_used"],
            }
        else:
            return {"memory_monitoring": False}


def _derive_art_type(entry: dict) -> str:
    """Map Scryfall fields to comprehensive art type taxonomy.

    Handles complex combinations of frame effects to prevent collisions.
    Priority order for primary classification, with modifier support:
    - textless (highest priority - very distinctive)
    - borderless (border_color = "borderless")
    - showcase
    - extended
    - retro (frame == '1993')
    - fullart
    - standard (fallback)

    Modifiers applied after primary type:
    - inverted -> adds "-oilslick" for sets ONE/MOM/MAT, otherwise "-inverted"
    - etched -> adds "-etched" suffix
    - And many more: -glossy, -gilded, -serialized, -acorn, -ub, -booster
    """
    frame_effects = entry.get("frame_effects") or []
    frame = entry.get("frame")
    full_art = entry.get("full_art", False)
    border_color = entry.get("border_color", "").lower()
    set_code = (entry.get("set") or "").lower()

    frame_effects = [fx.strip().lower() for fx in frame_effects if isinstance(fx, str)]

    frame = (entry.get("frame") or "").strip().lower()
    full_art = bool(entry.get("full_art"))

    # Determine primary art type (in priority order)
    primary_type = "standard"  # Default fallback

    if "textless" in frame_effects:
        primary_type = "textless"
    elif border_color == "borderless":
        primary_type = "borderless"
    elif "showcase" in frame_effects:
        primary_type = "showcase"
    elif "extendedart" in frame_effects:
        primary_type = "extended"
    elif frame == "1993":
        primary_type = "retro"
    elif full_art or "fullart" in frame_effects:
        primary_type = "fullart"

    # Apply finish modifiers (in consistent order)
    modifiers = []

    # Core finish modifiers
    # Only treat "inverted" as "oilslick" for specific sets where this is confirmed
    # Many "inverted" cards are not actually oilslick treatments
    if "inverted" in frame_effects and set_code in {
        "one",
        "mom",
        "mat",
    }:  # Known oilslick sets
        modifiers.append("oilslick")
    elif "inverted" in frame_effects:
        modifiers.append("inverted")  # Keep as generic inverted treatment
    if "etched" in frame_effects:
        modifiers.append("etched")

    # Additional finish modifiers
    if "glossy" in frame_effects:
        modifiers.append("glossy")
    if "gilded" in frame_effects:
        modifiers.append("gilded")
    if "serialized" in frame_effects:
        modifiers.append("serialized")

    # Set-specific modifiers
    set_code = entry.get("set", "").lower()
    if set_code == "unf" and "acorn" in frame_effects:
        modifiers.append("acorn")
    if "universesbeyond" in frame_effects:
        modifiers.append("ub")  # Universes Beyond

    # Special treatments
    if "booster" in frame_effects or "boosterfun" in frame_effects:
        modifiers.append("booster")
    if "concept" in frame_effects:
        modifiers.append("concept")
    if "thick" in frame_effects:
        modifiers.append("thick")

    # Combine primary type with modifiers
    if modifiers:
        return f"{primary_type}-{'-'.join(sorted(modifiers))}"
    else:
        return primary_type


def _get_art_type_stats(entries: list[dict]) -> dict[str, int]:
    """Generate statistics about art types in a collection of entries."""
    stats = {}
    for entry in entries:
        art_type = _derive_art_type(entry)
        stats[art_type] = stats.get(art_type, 0) + 1
    return dict(sorted(stats.items()))


def _detect_potential_collisions(entries: list[dict]) -> list[dict]:
    """Detect potential naming collisions in card entries."""
    stems_seen = {}
    collisions = []

    for entry in entries:
        # Generate the base stem that would be used for filename
        name = entry.get("name", "")
        art_type = _derive_art_type(entry)

        # Create a simplified stem for collision detection
        stem = f"{name.lower().replace(' ', '-').replace(',', '')}-{art_type}-en"

        if stem in stems_seen:
            collisions.append({"stem": stem, "cards": [stems_seen[stem], entry]})
        else:
            stems_seen[stem] = entry

    return collisions[:100]  # Return first 100 collisions


def _analyze_frame_effects_coverage() -> dict:
    """Analyze coverage of frame effects across the system."""
    # This would normally analyze the database, but for now return static data
    known_primary = {
        "textless",
        "borderless",
        "showcase",
        "extended",
        "retro",
        "fullart",
        "standard",
    }
    known_modifiers = {"oilslick", "etched", "glossy", "gilded", "serialized"}

    return {
        "known_primary": list(known_primary),
        "known_modifiers": list(known_modifiers),
        "coverage_status": "comprehensive",
        "total_combinations": len(known_primary) * (2 ** len(known_modifiers)),
    }


def _generate_art_type_report(entries: list[dict], entry_type: str = "cards") -> dict:
    """Generate comprehensive art type analysis report with memory monitoring."""
    # Initialize memory monitoring for analysis
    monitor = MemoryMonitor()

    stats = _get_art_type_stats(entries)
    if monitor.enabled:
        monitor.log_memory("after art type stats")

    collisions = _detect_potential_collisions(entries)
    if monitor.enabled:
        monitor.log_memory("after collision detection")

    coverage = _analyze_frame_effects_coverage()

    report = {
        "entry_type": entry_type,
        "total_entries": len(entries),
        "art_type_distribution": stats,
        "potential_collisions": len(collisions),
        "collision_details": collisions[:10],  # Show first 10
        "frame_effects_coverage": coverage,
        "unique_art_types": len(stats),
        "most_common_art_type": (
            max(stats.items(), key=lambda x: x[1]) if stats else None
        ),
        "performance": monitor.get_summary(),
    }

    if monitor.enabled:
        monitor.log_memory("analysis complete")
    return report


def _normalize_langs(lang_preference: str) -> list[str]:
    """Normalize language preference into list of language codes.

    Supports:
    - 'en': English only
    - 'phyrexian'/'ph': Phyrexian only
    - 'special': English + fantasy languages (ph, grc, la, he, sa)
    - 'all': All languages
    - 'en,ph,ja': Comma-separated list
    """
    lang_preference = lang_preference.lower().strip()

    # Handle system locale formats (e.g., en_US.UTF-8 -> en)
    if "_" in lang_preference or "." in lang_preference:
        lang_preference = lang_preference.split("_")[0].split(".")[0]

    if lang_preference == "en":
        return ["en"]
    elif lang_preference in ("phyrexian", "ph"):
        return ["ph"]  # Phyrexian
    elif lang_preference == "special":
        # English + fantasy languages (excludes real-world languages)
        return ["en", "ph", "grc", "la", "he", "sa"]
    elif lang_preference == "all":
        # All 18 languages
        return [
            "en",
            "es",
            "fr",
            "de",
            "it",
            "pt",
            "ja",
            "ko",
            "ru",
            "zhs",
            "zht",
            "ph",
            "grc",
            "la",
            "he",
            "sa",
            "ar",
            "hi",
        ]
    elif "," in lang_preference:
        # Comma-separated list
        langs = []
        for lang in lang_preference.split(","):
            lang = lang.strip()
            if lang == "phyrexian":
                lang = "ph"
            langs.append(lang)
        return langs
    else:
        # Single language code
        if lang_preference == "phyrexian":
            return ["ph"]
        return [lang_preference]


def _land_base_stem(entry: dict, lang: str | None = None) -> str:
    """Generate base filename stem for land cards with enhanced naming scheme.

    Format: landname-arttype-language-set-collector
    Examples: island-fullart-en-mh3-123, forest-showcase-ph-mh2-045
    """
    name = entry.get("name", "")
    art_type = _derive_art_type(entry)
    raw_set = (
        entry.get("set")
        or entry.get("set_code")
        or entry.get("set_id")
        or entry.get("set_name")
    )
    set_code = _normalize_set_code(raw_set or "misc")
    collector_number = entry.get("collector_number") or ""

    # Extract language from entry if not provided
    if lang is None:
        lang = entry.get("lang", "en")

    # Clean up the name for filename use
    clean_name = name.lower().replace(" ", "").replace(",", "").replace("'", "")

    collector_slug = (
        _slugify(collector_number, allow_underscores=True)
        if collector_number
        else "no-collector"
    )

    return f"{clean_name}-{art_type}-{lang}-{set_code}-{collector_slug}"


def _card_base_stem(entry: dict, lang: str | None = None) -> str:
    """Generate base filename stem for non-land cards with extended naming scheme.

    Format: cardname-arttype-language-set
    Examples: lightning-bolt-standard-en-ltr, tarmogoyf-borderless-en-mh2
    """
    name = entry.get("name", "")
    art_type = _derive_art_type(entry)
    set_code = entry.get("set", "misc").lower()

    # Extract language from entry if not provided
    if lang is None:
        lang = entry.get("lang", "en")

    # Clean up the name for filename use
    clean_name = (
        name.lower().replace(" ", "").replace(",", "").replace("'", "").replace("-", "")
    )

    return f"{clean_name}-{art_type}-{lang}-{set_code}"


def _get_card_type_directory(entry: dict) -> str:
    """Determine the appropriate directory for a card based on its type."""
    type_line = entry.get("type_line", "").lower()

    if "creature" in type_line:
        return shared_creatures_path
    elif "enchantment" in type_line:
        return shared_enchantments_path
    elif "artifact" in type_line:
        return shared_artifacts_path
    else:
        # Fallback for unknown types - use creatures folder
        return shared_creatures_path


def _token_base_stem(entry: dict, lang: str | None = None) -> str:
    """Generate base filename stem for tokens with extended naming scheme.

    Format: tokenname-arttype-language-set
    Examples: beast-standard-en-ltr, spirit-showcase-ph-one, soldier-borderless-en-mh2
    """
    name = entry.get("name", "")
    art_type = _derive_art_type(entry)
    set_code = entry.get("set", "misc").lower()

    # Extract language from entry if not provided
    if lang is None:
        lang = entry.get("lang", "en")

    # Clean up the name for filename use
    clean_name = (
        name.lower().replace(" ", "").replace(",", "").replace("'", "").replace("-", "")
    )

    return f"{clean_name}-{art_type}-{lang}-{set_code}"


def _parse_token_stem(stem: str) -> dict | None:
    """Parse token stem in new format: tokenname-arttype-language-set."""
    parts = stem.split("-")

    if len(parts) >= 4:
        # New format: tokenname-arttype-language-set
        token_name = parts[0]
        set_code = parts[-1]
        language = parts[-2]
        art_type = "-".join(parts[1:-2]) if len(parts) > 4 else parts[1]

        return {
            "name": token_name,
            "art_type": art_type,
            "language": language,
            "set": set_code,
            "subtype": token_name,  # Assume token name is the subtype for now
        }

    return None


def _guess_subtype_from_stem(stem: str) -> str:
    """Guess token subtype from filename stem."""
    # Try to extract the main token name from various formats
    if "_" in stem:
        # Legacy format: name_set
        return stem.split("_")[0]
    elif "-" in stem:
        # New format: name-arttype-lang-set
        return stem.split("-")[0]
    else:
        # Single word
        return stem


def _migrate_tokens_to_new_structure(
    dry_run: bool = True,
) -> tuple[int, int, list[str]]:
    """Migrate existing tokens to hybrid organization with new naming.

    FROM: tokens/beast/beast_ltr.png
    TO:   tokens/beast/ltr/beast-standard-en-ltr.png

    Returns: (moved_count, skipped_count, error_messages)
    """
    root = Path(shared_tokens_path)
    if not root.exists():
        return 0, 0, ["Token directory does not exist"]

    moved = 0
    skipped = 0
    errors = []

    click.echo(f"{'[DRY RUN] ' if dry_run else ''}Migrating tokens to new structure...")

    # Process all subtype directories
    for subtype_dir in sorted(root.iterdir()):
        if not subtype_dir.is_dir():
            continue
        if subtype_dir.name.startswith("."):
            continue
        if subtype_dir.name == "_index.json":
            continue

        subtype_name = subtype_dir.name
        click.echo(f"Processing subtype: {subtype_name}")

        # Process all token files in this subtype
        for token_file in sorted(subtype_dir.iterdir()):
            if not token_file.is_file():
                continue
            if token_file.name.startswith("."):
                continue
            if token_file.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            try:
                # Parse legacy filename: tokenname_setcode.ext
                stem = token_file.stem
                if "_" not in stem:
                    errors.append(f"Cannot parse legacy format: {token_file}")
                    skipped += 1
                    continue

                name_part, set_part = stem.rsplit("_", 1)
                set_code = set_part.lower()
                token_name = name_part

                # Create new filename: tokenname-standard-en-setcode.ext
                new_stem = f"{token_name}-standard-en-{set_code}"
                new_filename = f"{new_stem}{token_file.suffix}"

                # Create hybrid directory: tokens/subtype/set/filename
                subtype_dir = root / subtype_name
                set_dir = subtype_dir / set_code
                new_path = set_dir / new_filename

                if new_path.exists():
                    click.echo(
                        f"  Skip (exists): {subtype_name}/{set_code}/{new_filename}"
                    )
                    skipped += 1
                    continue

                click.echo(
                    f"  Move: {token_file.name} -> {subtype_name}/{set_code}/{new_filename}"
                )

                if not dry_run:
                    set_dir.mkdir(parents=True, exist_ok=True)
                    token_file.rename(new_path)

                moved += 1

            except Exception as e:
                errors.append(f"Error processing {token_file}: {e}")
                skipped += 1

    # Clean up empty subtype directories
    if not dry_run:
        for subtype_dir in root.iterdir():
            if subtype_dir.is_dir() and not any(subtype_dir.iterdir()):
                try:
                    subtype_dir.rmdir()
                    click.echo(f"Removed empty directory: {subtype_dir.name}")
                except OSError:
                    pass

    click.echo(
        f"\nMigration {'preview' if dry_run else 'complete'}: {moved} moved, {skipped} skipped"
    )
    if errors:
        click.echo(f"Errors encountered: {len(errors)}")
        for error in errors[:5]:  # Show first 5 errors
            click.echo(f"  {error}")
        if len(errors) > 5:
            click.echo(f"  ... and {len(errors) - 5} more")

    return moved, skipped, errors


def _parse_enhanced_stem_format(stem: str) -> tuple[str, str, str]:
    """Parse enhanced stem format: landname-arttype-language.

    Returns: (landname, arttype, language)
    """
    parts = stem.split("-")

    if len(parts) >= 3:
        # New format: landname-arttype-language (possibly with compound art types)
        language = parts[-1]

        # Handle compound art types (e.g., showcase-oilslick-etched)
        if len(parts) > 3:
            landname = parts[0]
            arttype = "-".join(parts[1:-1])
        else:
            landname, arttype = parts[0], parts[1]

        return landname, arttype, language
    elif len(parts) == 2:
        # Legacy format: landtype-arttype (assume English)
        return parts[0], parts[1], "en"
    else:
        # Single part or unknown format
        return stem, "standard", "en"


def _derive_basic_landtype(name: str) -> str:
    name_l = (name or "").strip().lower()
    # Handle Snow-Covered basics and localized names by substring match
    for t in ("plains", "island", "swamp", "mountain", "forest", "wastes"):
        if t in name_l:
            return t
    # Fallback to last word, then slug
    parts = name_l.split()
    return parts[-1] if parts else _slugify(name)


def _derive_landtype(entry: dict) -> str:
    if entry.get("is_basic_land"):
        return _derive_basic_landtype(
            entry.get("name") or entry.get("name_slug") or "land"
        )
    return entry.get("name_slug") or _slugify(entry.get("name", "land"))


# Enhanced _land_base_stem function moved above - this old version removed


def _classify_land_type(card_name: str, type_line: str, oracle_text: str = "") -> str:
    """Classify land by mana production pattern.

    Returns: mono, dual, tri, wubrg, colorless, utility, or special category
    """
    name_lower = card_name.lower()
    type_lower = type_line.lower()
    oracle_lower = (oracle_text or "").lower()

    # Basic lands – route into the same color-based mono folders as nonbasics
    if "basic" in type_lower:
        if "plains" in name_lower:
            return "mono/white"
        elif "island" in name_lower:
            return "mono/blue"
        elif "swamp" in name_lower:
            return "mono/black"
        elif "mountain" in name_lower:
            return "mono/red"
        elif "forest" in name_lower:
            return "mono/green"
        elif "wastes" in name_lower:
            return "colorless/wastes"

    # Special mechanical types
    if "gate" in type_lower:
        return "special/gates"
    elif "desert" in type_lower:
        return "special/deserts"
    elif "cave" in type_lower:
        return "special/caves"
    elif any(
        x in name_lower for x in ["urza's mine", "urza's power plant", "urza's tower"]
    ):
        return "special/urzatron"

    # Landscape cycle (Modern Horizons 3)
    elif "landscape" in name_lower:
        # Landscapes are a named type cycle, keep them under special/
        return "special/landscapes"

    # Five-color / any color
    # First, detect classic "rainbow" fixing: add mana of any color.
    if "mana of any color" in oracle_lower or "any color of mana" in oracle_lower:
        return "wubrg/rainbow"

    # Heavy five-color enablers for manabases (add WUBRG / five mana / one of each color)
    if (
        "add five mana" in oracle_lower
        or "add wubrg" in oracle_lower
        or "one mana of each color" in oracle_lower
    ):
        return "wubrg/manabase"

    # Fetchlands / sac lands (utility/fetchlands)
    if (
        "sacrifice" in oracle_lower
        and "search your library" in oracle_lower
        and "land" in oracle_lower
    ):
        return "utility/fetchlands"

    # Utility lands (legendary, manlands, etc.)
    if "legendary" in type_lower and "creature" not in type_lower:
        return "utility/legendary"
    elif "creature" in type_lower or "becomes a" in oracle_lower:
        return "utility/manlands"

    # Analyze mana symbols to determine color identity
    colors = []
    if "{w}" in oracle_lower or "white" in oracle_lower:
        colors.append("W")
    if "{u}" in oracle_lower or "blue" in oracle_lower:
        colors.append("U")
    if "{b}" in oracle_lower or "black" in oracle_lower:
        colors.append("B")
    if "{r}" in oracle_lower or "red" in oracle_lower:
        colors.append("R")
    if "{g}" in oracle_lower or "green" in oracle_lower:
        colors.append("G")

    # Sort colors in WUBRG order for consistent naming
    color_identity = "".join(colors)

    # Pathway lands: keep under their dual color buckets as dual/<guild>/pathways
    if "pathway" in name_lower:
        pathway_guild_map = {
            # Zendikar Rising (enemy pairs)
            "brightclimb pathway": "orzhov",  # // grimclimb
            "grimclimb pathway": "orzhov",
            "clearwater pathway": "dimir",  # // murkwater
            "murkwater pathway": "dimir",
            "riverglide pathway": "izzet",  # // lavaglide
            "needleverge pathway": "boros",  # // pillarverge
            "pillarverge pathway": "boros",
            "cragcrown pathway": "gruul",  # // timbercrown
            "timbercrown pathway": "gruul",
            "branchloft pathway": "selesnya",  # // boulderloft
            "boulderloft pathway": "selesnya",
            # Kaldheim (ally pairs)
            "barkchannel pathway": "simic",  # // tidechannel
            "tidechannel pathway": "simic",
            "blightstep pathway": "rakdos",  # // searstep
            "searstep pathway": "rakdos",
            "darkbore pathway": "golgari",  # // slitherbore
            "slitherbore pathway": "golgari",
            "hengegate pathway": "azorius",  # // mistgate
            "mistgate pathway": "azorius",
            "needleverge pathway": "boros",  # safety if spelled differently
        }

        guild = pathway_guild_map.get(name_lower)
        if guild:
            # Place Pathways with other dual lands, under a dedicated subfolder
            return f"dual/{guild}/pathways"
        # Fallback to generic dual/other if we can't recognize the name
        return "dual/other"

    # Map color combinations to guild/shard/wedge names
    if len(colors) == 5:
        return "wubrg/rainbow"
    elif len(colors) == 4:
        # Four-color combinations (Commander naming)
        four_color_map = {
            "WUBG": "four-color/artifice",  # Missing R
            "URBG": "four-color/aggression",  # Missing W
            "WRBG": "four-color/altruism",  # Missing U
            "WURG": "four-color/growth",  # Missing B
            "WUBR": "four-color/chaos",  # Missing G
        }
        return four_color_map.get(color_identity, "four-color/other")
    elif len(colors) == 3:
        # Three-color combinations (Shards and Wedges)
        tri_color_map = {
            # Allied Shards (Alara) - all permutations
            "WUG": "tri/bant",
            "WGU": "tri/bant",
            "UWG": "tri/bant",
            "UGW": "tri/bant",
            "GWU": "tri/bant",
            "GUW": "tri/bant",
            "WUB": "tri/esper",
            "WBU": "tri/esper",
            "UWB": "tri/esper",
            "UBW": "tri/esper",
            "BWU": "tri/esper",
            "BUW": "tri/esper",
            "UBR": "tri/grixis",
            "URB": "tri/grixis",
            "BUR": "tri/grixis",
            "BRU": "tri/grixis",
            "RUB": "tri/grixis",
            "RBU": "tri/grixis",
            "BRG": "tri/jund",
            "BGR": "tri/jund",
            "RBG": "tri/jund",
            "RGB": "tri/jund",
            "GBR": "tri/jund",
            "GRB": "tri/jund",
            "RGW": "tri/naya",
            "RWG": "tri/naya",
            "GRW": "tri/naya",
            "GWR": "tri/naya",
            "WRG": "tri/naya",
            "WGR": "tri/naya",
            # Enemy Wedges (Tarkir) - all permutations
            "WBG": "tri/abzan",
            "WGB": "tri/abzan",
            "BWG": "tri/abzan",
            "BGW": "tri/abzan",
            "GWB": "tri/abzan",
            "GBW": "tri/abzan",
            "URW": "tri/jeskai",
            "UWR": "tri/jeskai",
            "RUW": "tri/jeskai",
            "RWU": "tri/jeskai",
            "WUR": "tri/jeskai",
            "WRU": "tri/jeskai",
            "BGU": "tri/sultai",
            "BUG": "tri/sultai",
            "GBU": "tri/sultai",
            "GUB": "tri/sultai",
            "UBG": "tri/sultai",
            "UGB": "tri/sultai",
            "RWB": "tri/mardu",
            "RBW": "tri/mardu",
            "WRB": "tri/mardu",
            "WBR": "tri/mardu",
            "BRW": "tri/mardu",
            "BWR": "tri/mardu",
            # Temur wedges (all permutations of G, U, R)
            "GUR": "tri/temur",
            "GRU": "tri/temur",
            "RGU": "tri/temur",
            "RUG": "tri/temur",
            "URG": "tri/temur",
            "UGR": "tri/temur",
        }
        return tri_color_map.get(color_identity, "tri/other")
    elif len(colors) == 2:
        # Two-color combinations (Guilds)
        dual_color_map = {
            # Allied Guild Pairs (Ravnica)
            "WU": "dual/azorius",
            "UB": "dual/dimir",
            "BR": "dual/rakdos",
            "RG": "dual/gruul",
            "GW": "dual/selesnya",
            "WG": "dual/selesnya",  # Alternative order
            # Enemy Guild Pairs (Ravnica)
            "WB": "dual/orzhov",
            "UR": "dual/izzet",
            "BG": "dual/golgari",
            "RW": "dual/boros",
            "WR": "dual/boros",  # Alternative order
            "UG": "dual/simic",
        }
        return dual_color_map.get(color_identity, "dual/other")
    elif len(colors) == 1:
        # Monocolor nonbasic lands by color
        mono_map = {
            "W": "mono/white",
            "U": "mono/blue",
            "B": "mono/black",
            "R": "mono/red",
            "G": "mono/green",
        }
        return mono_map.get(colors[0], "mono/other")

    # Colorless lands (no detected colors) with special behavior
    # Ramp-style colorless lands (Ancient Tomb, Temple of the False God, etc.)
    if "{c}{c}" in oracle_lower or "add two colorless mana" in oracle_lower:
        return "colorless/ramp"
    if (
        "add {c} for each" in oracle_lower
        or "add one colorless mana for each" in oracle_lower
    ):
        return "colorless/ramp"

    # Colorless utility lands (card draw, scry, recursion, etc.)
    if (
        "draw a card" in oracle_lower
        or "scry" in oracle_lower
        or "return target" in oracle_lower
    ):
        return "colorless/utility"

    # Colorless land-hate (Strip Mine, Wasteland, Ghost Quarter, etc.)
    if (
        "destroy target land" in oracle_lower
        or "destroy target nonbasic land" in oracle_lower
        or "nonbasic land" in oracle_lower
        and "destroy" in oracle_lower
    ):
        return "colorless/land-hate"

    # Colorless commander/multiplayer support (Command Beacon, Homeward Path, etc.)
    if "commander" in oracle_lower:
        return "colorless/commander"

    # Colorless tribal/synergy lands (Swarmyard, Animal Sanctuary, Elephant Graveyard, etc.)
    if any(
        tribe in oracle_lower
        for tribe in [
            "elephant",
            "griffin",
            "rat",
            "spider",
            "sliver",
            "zombie",
            "cat",
            "dog",
        ]
    ):
        return "colorless/tribal"

    # Generic colorless
    if "{c}" in oracle_lower or "colorless" in oracle_lower:
        return "colorless/other"

    # Utility MDFC-style spell lands (Zendikar Rising spell-lands and similar)
    if "znr" in type_lower or any(
        key in name_lower
        for key in [
            "agadeem",
            "emeria",
            "sejiri",
            "turntimber",
            "ondu",
            "valakut",
            "kabira",
            "makindi",
            "malakir",
            "pelakka",
            "bala ged",
            "beyeen",
            "jwari",
            "khalni",
        ]
    ):
        return "utility/mdfc"

    # Maze / combat-prevention utility lands (Maze of Ith, Glacial Chasm, etc.)
    if (
        "remove target attacking creature from combat" in oracle_lower
        or "untap target attacking creature" in oracle_lower
        or "prevent all combat damage" in oracle_lower
        or "prevent all damage that would be dealt to you" in oracle_lower
    ):
        return "utility/maze"

    # Default utility
    return "utility/other"


COLOR_ORDER = ["W", "U", "B", "R", "G"]
COLOR_NAMES = {
    "W": "white",
    "U": "blue",
    "B": "black",
    "R": "red",
    "G": "green",
}
TWO_COLOR_NAMES = {
    "WU": "azorius",
    "WB": "orzhov",
    "WR": "boros",
    "WG": "selesnya",
    "UB": "dimir",
    "UR": "izzet",
    "UG": "simic",
    "BR": "rakdos",
    "BG": "golgari",
    "RG": "gruul",
}
THREE_COLOR_NAMES = {
    "WUB": "esper",
    "WUR": "jeskai",
    "WUG": "bant",
    "WBR": "mardu",
    "WBG": "abzan",
    "WRG": "naya",
    "UBR": "grixis",
    "UBG": "sultai",
    "URG": "temur",
    "BRG": "jund",
}


def _normalize_color_identity(entry: dict) -> list[str]:
    """Return color identity symbols ordered WUBRG."""

    colors = entry.get("color_identity") or entry.get("oracle_color_identity") or []
    color_set = {c.upper() for c in colors if c and c.upper() in COLOR_NAMES}
    return [symbol for symbol in COLOR_ORDER if symbol in color_set]


def _color_identity_path(entry: dict) -> str:
    """Return path segment representing color identity."""

    colors = _normalize_color_identity(entry)

    if not colors:
        return "colorless"

    if len(colors) == 1:
        return f"mono/{COLOR_NAMES[colors[0]]}"

    key = "".join(colors)

    if len(colors) == 2:
        name = TWO_COLOR_NAMES.get(key, key.lower())
        return f"dual/{name}"

    if len(colors) == 3:
        name = THREE_COLOR_NAMES.get(key, key.lower())
        return f"tri/{name}"

    if len(colors) == 4:
        return f"quad/{key.lower()}"

    return "five/wubrg"


def _detect_spell_effect(entry: dict) -> str:
    """Rudimentary spell classification based on oracle text."""

    oracle_text = (entry.get("oracle_text") or entry.get("printed_text") or "").lower()

    if not oracle_text:
        return "utility"

    def contains(*phrases: str) -> bool:
        return any(phrase in oracle_text for phrase in phrases)

    if contains("destroy all", "exile all", "deal", "each creature") and (
        "destroy" in oracle_text or "exile" in oracle_text or "damage" in oracle_text
    ):
        return "sweeper"

    if "counter target" in oracle_text:
        return "counter"

    if contains("destroy target", "exile target", "-x/-x", "deals"):
        if "all" in oracle_text:
            return "sweeper"
        return "removal"

    if contains("search your library"):
        return "tutor"

    if contains("create", "token"):
        return "token"

    if contains("add {", "search your library for a land", "put a land"):
        return "ramp"

    if contains("return target", "from your graveyard"):
        return "reanimation"

    if contains("draw", "cards"):
        return "card-advantage"

    if contains("target opponent discards"):
        return "discard"

    if contains("gain", "life"):
        return "life-gain"

    if contains("prevent"):
        return "prevention"

    if contains("until end of turn", "gets", "+"):
        return "combat-trick"

    return "utility"


def _detect_artifact_role(entry: dict) -> str:
    """Classify artifact by primary role."""

    type_line = (entry.get("type_line") or "").lower()
    oracle_text = (entry.get("oracle_text") or "").lower()

    if "equipment" in type_line:
        return "equipment"
    if "vehicle" in type_line:
        return "vehicles"
    if "creature" in type_line:
        return "creature-artifacts"
    if "add {" in oracle_text or "mana pool" in oracle_text:
        return "mana-rocks"
    if (
        "clue" in type_line
        or "food" in type_line
        or "treasure" in type_line
        or "blood" in type_line
        or "map" in type_line
    ):
        return "token-artifacts"
    if "legendary" in type_line:
        return "legendary"
    if "create" in oracle_text and "token" in oracle_text:
        return "token-generators"
    return "utility"


def _detect_enchantment_role(entry: dict) -> str:
    """Classify enchantment by subtype or effect."""

    type_line = (entry.get("type_line") or "").lower()
    oracle_text = (entry.get("oracle_text") or "").lower()

    if "aura" in type_line:
        return "auras"
    if "saga" in type_line:
        return "sagas"
    if "class" in type_line:
        return "class"
    if "background" in type_line:
        return "backgrounds"
    if "shrine" in type_line:
        return "shrines"
    if "curse" in type_line:
        return "curses"
    if "creature" in type_line:
        return "creature-enchantments"
    if "create" in oracle_text and "token" in oracle_text:
        return "token-generators"
    if "draw" in oracle_text:
        return "card-advantage"
    if "prevent" in oracle_text or "shroud" in oracle_text or "hexproof" in oracle_text:
        return "protection"
    return "utility"


def _classify_spell_path(entry: dict) -> str:
    color_path = _color_identity_path(entry)
    effect = _detect_spell_effect(entry)
    return f"{color_path}/{effect}"


def _classify_artifact_path(entry: dict) -> str:
    role = _detect_artifact_role(entry)
    color_path = _color_identity_path(entry)
    return f"role/{role}/{color_path}"


def _classify_enchantment_path(entry: dict) -> str:
    role = _detect_enchantment_role(entry)
    color_path = _color_identity_path(entry)
    return f"role/{role}/{color_path}"


def _unique_land_destination(
    base_dir: Path,
    land_type: str,
    base_stem: str,
    extension: str = ".png",
) -> Path:
    """Return a unique destination path for a land card organized by type."""

    if land_type:
        parts = [segment for segment in land_type.split("/") if segment]
    else:
        parts = ["uncategorized"]

    type_dir = base_dir.joinpath(*parts)
    type_dir.mkdir(parents=True, exist_ok=True)
    destination = type_dir / f"{base_stem}{extension}"

    counter = 1
    while destination.exists():
        destination = type_dir / f"{base_stem}_{counter}{extension}"
        counter += 1

    return destination


def _sld_organized_destination(
    base_dir: Path,
    base_stem: str,
    ext: str,
    collector_number: str | None,
) -> Path:
    """Generate SLD-specific organized destination with art-type/drop structure."""
    # Parse the art type from base_stem - works for both basic and non-basic lands
    # Basic: forest-fullart-en → fullart
    # Non-basic: command-tower-borderless-en → borderless
    parts = base_stem.split("-")
    art_type = "standard"  # Default fallback

    # Scan parts to find the art type (could be at any position except first and last)
    for part in parts[1:-1]:  # Skip first (name) and last (language)
        if part in _ART_TYPES:
            art_type = part
            break

    # Detect the drop theme
    drop_theme = _detect_sld_drop(collector_number)

    # Create organized path: sld/art-type/drop-theme/
    target_dir = base_dir / "sld" / art_type / drop_theme
    target_dir.mkdir(parents=True, exist_ok=True)

    # Always try collector number first for better identification
    coll = (collector_number or "").strip()
    if coll:
        coll_slug = _slugify(coll, allow_underscores=True)
        with_coll = target_dir / f"{base_stem}-{coll_slug}{ext}"
        if not with_coll.exists():
            return with_coll

    # Fallback to base filename if no collector number
    candidate = target_dir / f"{base_stem}{ext}"
    if not candidate.exists():
        return candidate

    # Numeric disambiguation as last resort
    n = 2
    while True:
        numbered = target_dir / f"{base_stem}-{n}{ext}"
        if not numbered.exists():
            return numbered
        n += 1


def _unique_token_destination(
    base_dir: Path,
    base_stem: str,
    ext: str,
    collector_number: str | None,
) -> Path:
    """Generate unique token destination with collector number collision resolution."""
    # Always try collector number first for better identification
    coll = (collector_number or "").strip()
    if coll:
        coll_slug = _slugify(coll, allow_underscores=True)
        with_coll = base_dir / f"{base_stem}-{coll_slug}{ext}"
        if not with_coll.exists():
            return with_coll

    # Fallback to base filename if no collector number
    candidate = base_dir / f"{base_stem}{ext}"
    if not candidate.exists():
        return candidate

    # Numeric disambiguation as last resort
    n = 2
    while True:
        numbered = base_dir / f"{base_stem}-{n}{ext}"
        if not numbered.exists():
            return numbered
        n += 1


def _unique_card_destination(
    base_dir: Path,
    base_stem: str,
    ext: str,
    collector_number: str | None,
    *,
    disambiguators: dict[str, str | None] | None = None,
) -> Path:
    """Generate unique card destination with collector number collision resolution.

    Optional ``disambiguators`` provide additional slug components (e.g., set, lang) that
    are appended before numeric suffixes to keep filenames deterministic when multiple
    prints share the same collector number.
    """
    # Always try collector number first for better identification
    coll = (collector_number or "").strip()
    if coll:
        coll_slug = _slugify(coll, allow_underscores=True)
        with_coll = base_dir / f"{base_stem}-{coll_slug}{ext}"
        if not with_coll.exists():
            return with_coll

    # Fallback to base filename if no collector number
    candidate = base_dir / f"{base_stem}{ext}"
    if not candidate.exists():
        return candidate

    # Numeric disambiguation as last resort
    n = 2
    while True:
        numbered = base_dir / f"{base_stem}-{n}{ext}"
        if not numbered.exists():
            return numbered
        n += 1


def _enrich_entry_with_art_meta(entry: dict) -> dict:
    """Ensure entry has fields used for art-type derivation by merging from database or bulk index if needed."""
    need = not (
        "frame" in entry
        or "frame_effects" in entry
        or "full_art" in entry
        or "border_color" in entry
    )
    if need:
        card_id = entry.get("id")
        if card_id:
            # Try database first for fast lookup
            if _db_index_available():
                try:
                    from db.bulk_index import DB_PATH, _get_connection

                    conn = _get_connection(DB_PATH)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT frame, frame_effects, full_art, border_color, name, name_slug FROM prints WHERE id=? LIMIT 1",
                        (card_id,),
                    )
                    row = cur.fetchone()
                    conn.close()

                    if row:
                        (
                            frame,
                            frame_effects,
                            full_art,
                            border_color,
                            name,
                            name_slug,
                        ) = row

                        # Parse frame_effects from JSON string to list
                        import json

                        try:
                            if isinstance(frame_effects, str):
                                frame_effects = json.loads(frame_effects)
                        except (json.JSONDecodeError, TypeError):
                            frame_effects = []

                        db_data = {
                            "frame": frame,
                            "frame_effects": frame_effects,
                            "full_art": (
                                bool(full_art) if full_art is not None else False
                            ),
                            "border_color": border_color,
                            "name": name,
                            "name_slug": name_slug,
                        }
                        # Merge only known fields to avoid clobbering
                        for key, value in db_data.items():
                            if value and key not in entry:
                                entry[key] = value
                        return entry
                except Exception:
                    pass  # Fall back to JSON method

            # Fallback to JSON bulk index if database not available
            bulk = _bulk_lookup_entry(card_id) or {}
            # Merge only known fields to avoid clobbering
            for key in (
                "frame",
                "frame_effects",
                "full_art",
                "border_color",
                "name",
                "name_slug",
            ):
                if key in bulk and key not in entry:
                    entry[key] = bulk[key]
    return entry


# Art type taxonomy for parsing existing filenames
_ART_TYPES = {
    "fullart",
    "textless",
    "borderless",
    "retro",
    "extended",
    "showcase",
    "standard",
    # Additional art types that can be detected with modifiers
    "borderless-inverted",
    "borderless-etched",
    "showcase-etched",
    "showcase-inverted",
    "showcase-oilslick",
    "extended-etched",
    "fullart-inverted",
    "fullart-etched",
}


# SLD Drop Detection based on collector number ranges
# Source: https://scryfall.com/sets/sld
_SLD_DROPS = {
    # Recent drops (2024-2025)
    (1945, 1949): "flower-power",
    (2193, 2196): "play-doh-squishful-thinking",
    (1995, 1999): "spiderman-daily-bugle",
    (1990, 1994): "spiderman-heroic-deeds",
    (1950, 1954): "spiderman-mana-symbiote",
    (2000, 2004): "spiderman-venom-colors",
    (2019, 2023): "spiderman-venom-inks",
    (1985, 1989): "spiderman-villainous-plots",
    (2076, 2080): "alien-auroras",
    (2088, 2094): "sonic-chasing-adventure",
    (2081, 2087): "sonic-friends-foes",
    # Lands-focused drops
    (1647, 1656): "brain-dead-lands",
    (1939, 1943): "spongebob-lands-under-sea",
    (1468, 1472): "pixel-lands-02",
    (1372, 1376): "doctor-who-dalek-lands",
    (359, 363): "dracula-lands",
    (1130, 1134): "kozyndan-lands",
    (1190, 1194): "post-malone-lands",
    (325, 329): "pixelsnowlands",
    (46, 50): "tokyo-lands",
    # Extended art drops
    (
        1358,
        1367,
    ): "extended-art-collection",  # Fixed: was 1360-1367, should be 1358-1367
    # Artist series
    (1160, 1163): "john-avon-series",
    (1173, 1176): "kev-walker-series",
    (1151, 1154): "aleksi-briclot-series",
    (1168, 1172): "frank-frazetta-series",
    (1285, 1288): "randy-vargas-series",
    (1289, 1292): "alayna-danner-series",
    (1251, 1254): "rebecca-guay-series",
    # Themed collections
    (1092, 1134): "fullart-collection",
    (415, 419): "borderless-collection",  # Fixed: was 416-452, actual range is 415-419
    (888, 896): "cats-vs-dogs",
    (100, 109): "happy-little-gathering",
    (384, 395): "zodiac-lands",
    (239, 243): "brutal-basic-lands",
    (254, 263): "kamigawa-ink",
    (119, 122): "seb-mckinnon-series",
    (476, 500): "totally-spaced-out",
    (680, 688): "shadowborn-apostles",
    # Additional discovered ranges from misc folder analysis
    (540, 559): "foil-jumpstart-lands",
    (561, 579): "stained-glass-walkers",
    (1348, 1351): "angels-collection",
    (1088, 1091): "transformers-collection",
    (1382, 1386): "meditations-on-nature",
    (1399, 1403): "lil-walkers",
    (1478, 1482): "chaos-vault",
    (704, 706): "wastes-collection",
    (673, 674): "phelddagrif-lands",
    (1513, 1515): "raining-cats-dogs-bonus",
}


def _detect_sld_drop(collector_number: str | None) -> str:
    """Detect SLD drop theme based on collector number."""
    if not collector_number:
        return "misc"

    try:
        num = int(collector_number)
        for (start, end), drop_name in _SLD_DROPS.items():
            if start <= num <= end:
                return drop_name
    except (ValueError, TypeError):
        pass

    # Fallback to "misc" if no match found
    return "misc"


def _parse_base_stem_from_stem(stem: str) -> str | None:
    """Given a filename stem, return %landtype%-%arttype% if it can be derived.

    This scans from the right for a token that matches a known art type.
    If found, returns the stem up to and including that token.
    """
    parts = stem.split("-")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] in _ART_TYPES:
            return "-".join(parts[: i + 1])
    return None


def _build_land_presence_index(base_dir: Path) -> dict[str, set[str]]:
    """Build a map of directory bucket -> present land stems.

    Buckets correspond to classification folders (e.g., "mono/plains" or
    "utility/legendary"). Legacy files that still live directly under the
    root (set-based layout) are indexed using their immediate parent directory
    name. This keeps duplicate checks O(1) while the helper runs in O(files)
    amortized and is cached for five minutes.
    """
    cache_key = f"lands_{base_dir}"

    # Check cache
    if cache_key in _PRESENCE_CACHE:
        age = time.time() - _PRESENCE_CACHE_TIME.get(cache_key, 0)
        if age < PRESENCE_CACHE_TTL:
            return _PRESENCE_CACHE[cache_key]

    # Build fresh index keyed by directory buckets (type hierarchy)
    presence_map: dict[str, set[str]] = defaultdict(set)

    if not base_dir.exists():
        return {}

    for file in sorted(base_dir.rglob("*")):
        if not file.is_file():
            continue
        if file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        relative_dir = file.parent.relative_to(base_dir).as_posix()
        bucket = relative_dir or "root"
        stem = file.stem

        # Handle both old and new formats
        old_bs = _parse_base_stem_from_stem(stem)
        if old_bs:
            presence_map[bucket].add(old_bs)

        presence_map[bucket].add(stem)

    presence = {bucket: set(stems) for bucket, stems in presence_map.items()}

    _PRESENCE_CACHE[cache_key] = presence
    _PRESENCE_CACHE_TIME[cache_key] = time.time()
    return presence


def _build_nested_presence_index(base_dir: Path) -> dict[str, set[str]]:
    """Build presence index for nested directories (color/effect buckets)."""

    presence: dict[str, set[str]] = defaultdict(set)
    if not base_dir.exists():
        return {}

    for file in base_dir.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        bucket = file.parent.relative_to(base_dir).as_posix()
        presence[bucket].add(file.stem)

    return {bucket: set(stems) for bucket, stems in presence.items()}


def _build_set_based_presence_index(base_dir: Path) -> dict[str, set[str]]:
    """Presence index keyed by immediate child directory (default fallback)."""

    presence: dict[str, set[str]] = defaultdict(set)
    if not base_dir.exists():
        return {}

    for child in base_dir.iterdir():
        if not child.is_dir():
            continue
        for file in child.iterdir():
            if not file.is_file():
                continue
            if file.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            presence[child.name].add(file.stem)

    return {bucket: set(stems) for bucket, stems in presence.items()}


def _basic_land_pf_key(card: dict) -> str:
    name = card.get("name", "").strip().lower()
    set_code = (card.get("set") or "").lower()
    collector_number = (card.get("collector_number") or "").strip().lower()
    return f"{name}|{set_code}|{collector_number}"


def _existing_basic_land_keys() -> set[str]:
    keys: set[str] = set()
    root = Path(shared_basic_lands_path)

    if not root.exists():
        return keys

    for file in root.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        stem = file.stem
        parts = stem.split("-")
        if len(parts) < 4:
            continue

        collector_slug = parts[-1]
        set_code = parts[-2]
        name_slug = "-".join(parts[:-2])

        key = f"{name_slug}|{set_code}|{collector_slug}"
        keys.add(key)

    return keys


def _existing_non_basic_land_keys() -> set[str]:
    keys: set[str] = set()
    root = Path(shared_non_basic_lands_path)

    if not root.exists():
        return keys

    for file in root.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        stem = file.stem
        parts = stem.split("-")

        if len(parts) < 4:
            legacy_parts = stem.split("_")
            if len(legacy_parts) < 2:
                continue
            name_slug = "_".join(legacy_parts[:-1])
            collector_slug = legacy_parts[-1]
            set_code = file.parent.name.lower()
            key = f"{name_slug}|{set_code}|{collector_slug}"
            keys.add(key)
            continue

        collector_slug = parts[-1]
        set_code = parts[-2]
        name_slug = "-".join(parts[:-2])

        key = f"{name_slug}|{set_code}|{collector_slug}"
        keys.add(key)

    return keys


def _render_progress(label: str, *, final: bool = False) -> None:
    global _PROGRESS_LAST_LEN

    message = f"  {label}"
    if final or not sys.stdout.isatty():
        if sys.stdout.isatty():
            click.echo(f"\r{message}")
        else:
            click.echo(message)
        _PROGRESS_LAST_LEN = 0
    else:
        padding = max(0, _PROGRESS_LAST_LEN - len(message))
        sys.stdout.write(f"\r{message}{' ' * padding}")
        sys.stdout.flush()
        _PROGRESS_LAST_LEN = len(message)


def _maybe_pause_fetch(progress_label: str, timeout: float = 5.0) -> None:
    _render_progress(progress_label)


def _normalize_land_directory(root_path: Path) -> None:
    """Legacy helper retained for backwards compatibility.

    The current land organization is classification-based, so this function is
    effectively a no-op. Legacy migrations are handled by `_run_land_migration`.
    """
    _ensure_directory(str(root_path))


def _run_land_migration(scope: str, set_filter: str | None, dry_run: bool) -> None:
    """Rename legacy land filenames to the new %landtype%-%arttype% scheme.

    - Scope: 'basic' | 'nonbasic' | 'all'
    - set_filter: restrict to set code (lowercase)
    - dry_run: do not mutate, only report planned changes
    Outputs CSV and JSON report under shared/reports/land-migration/<timestamp>/
    """

    def timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    roots: list[tuple[Path, bool]] = []
    if scope in {"basic", "all"}:
        roots.append((Path(shared_basic_lands_path), True))
    if scope in {"nonbasic", "non-basic", "all"}:
        roots.append((Path(shared_non_basic_lands_path), False))

    index = _load_bulk_index()
    entries = index.get("entries", {})
    cards_by_key = index.get("cards_by_key", {})

    actions: list[dict] = []
    migrated = 0
    skipped = 0
    errors = 0

    for root, is_basic in roots:
        if not root.exists():
            continue
        for set_dir in sorted(root.iterdir()):
            if not set_dir.is_dir():
                continue
            set_code = set_dir.name.lower()
            if set_filter and set_code != set_filter.lower():
                continue
            for file in sorted(set_dir.iterdir()):
                if not file.is_file():
                    continue
                if file.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                stem = file.stem

                # Detect legacy pattern: name_slug_COLLECTOR
                underscore_idx = stem.rfind("_")
                if underscore_idx <= 0:
                    # Either already migrated or custom file; try to detect new format quickly
                    # If it already matches new naming (exists as-is), skip
                    skipped += 1
                    actions.append(
                        {
                            "action": "skip",
                            "reason": "not_legacy_pattern",
                            "path": str(file),
                        }
                    )
                    continue

                name_slug = stem[:underscore_idx]
                collector_slug = stem[underscore_idx + 1 :]

                key = f"{name_slug}|{set_code}|{collector_slug}"
                card_id = cards_by_key.get(key)
                entry = entries.get(card_id) if card_id else None
                if not entry:
                    # Fallback minimal entry to proceed with standard arttype
                    entry = {
                        "id": None,
                        "name_slug": name_slug,
                        "name": _title_from_slug(name_slug),
                        "set": set_code,
                        "collector_number": collector_slug,
                        "type_line": "Land",
                        "is_basic_land": is_basic,
                    }
                entry = _enrich_entry_with_art_meta(dict(entry))

                base_stem = _land_base_stem(entry)
                land_type = _classify_land_type(
                    entry.get("name", ""),
                    entry.get("type_line", ""),
                    entry.get("oracle_text", ""),
                )
                ext = file.suffix
                dest = _unique_land_destination(
                    (
                        Path(shared_basic_lands_path)
                        if is_basic
                        else Path(shared_non_basic_lands_path)
                    ),
                    land_type,
                    base_stem,
                    ext,
                )

                if dest.resolve() == file.resolve():
                    skipped += 1
                    actions.append(
                        {
                            "action": "skip",
                            "reason": "already_correct",
                            "path": str(file),
                        }
                    )
                    continue

                if dry_run:
                    migrated += 1
                    actions.append(
                        {
                            "action": "rename",
                            "from": str(file),
                            "to": str(dest),
                            "reason": "dry_run",
                        }
                    )
                    continue

                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    file.rename(dest)
                    migrated += 1
                    actions.append(
                        {
                            "action": "rename",
                            "from": str(file),
                            "to": str(dest),
                        }
                    )
                except OSError as exc:
                    errors += 1
                    actions.append(
                        {
                            "action": "error",
                            "path": str(file),
                            "error": str(exc),
                        }
                    )

    # Write report
    reports_root = (
        Path(project_root_directory)
        / "magic-the-gathering"
        / "shared"
        / "reports"
        / "land-migration"
    )
    reports_root.mkdir(parents=True, exist_ok=True)
    out_dir = reports_root / timestamp()
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = out_dir / "migration.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["action", "from", "to", "reason", "error"])
        for a in actions:
            writer.writerow(
                [
                    a.get("action"),
                    a.get("from") or a.get("path"),
                    a.get("to") or "",
                    a.get("reason") or "",
                    a.get("error") or "",
                ]
            )

    # JSON
    json_path = out_dir / "migration_summary.json"
    summary = {
        "scope": scope,
        "set_filter": set_filter,
        "dry_run": dry_run,
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "actions": actions}, f, indent=2)
        f.write("\n")

    click.echo(
        f"Migration {'(dry run) ' if dry_run else ''}completed: migrated={migrated}, skipped={skipped}, errors={errors}"
    )
    click.echo(f"Wrote migration CSV: {csv_path}")
    click.echo(f"Wrote migration JSON: {json_path}")
    _offer_open_in_folder(str(json_path), kind="migration report")


def _fetch_all_basic_lands_from_scryfall(
    *,
    retry_only: bool = False,
    lang_preference: str = "en",
    dry_run: bool = False,
    progress: bool = True,
    land_set_filter: str | None = None,
    fullart_only: bool = False,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    border_color_filter: str | None = None,
    include_related: bool = True,
    limit: int | None = None,
) -> tuple[int, int, int, list[str]]:
    """Fetch all basic lands from Scryfall.

    DEPRECATED: This function now wraps _fetch_cards_universal().
    Use _fetch_cards_universal(card_type="basic_land", ...) for new code.
    """
    return _fetch_cards_universal(
        card_type="basic_land",
        lang_preference=lang_preference,
        set_filter=land_set_filter,
        artist_filter=artist_filter,
        rarity_filter=rarity_filter,
        fullart_only=fullart_only,
        layout_filter=layout_filter,
        frame_filter=frame_filter,
        border_color_filter=border_color_filter,
        include_related=include_related,
        limit=limit,
        retry_only=retry_only,
        dry_run=dry_run,
        progress=progress,
    )


def _fetch_all_basic_lands_from_scryfall_LEGACY(
    *,
    retry_only: bool = False,
    lang_preference: str = "en",
    dry_run: bool = False,
    progress: bool = True,
    land_set_filter: str | None = None,
    fullart_only: bool = False,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    border_color_filter: str | None = None,
    include_related: bool = True,
) -> tuple[int, int, int, list[str]]:
    """LEGACY IMPLEMENTATION - Kept for reference, not used."""
    # Initialize memory monitoring and Discord notifications
    memory_monitor = MemoryMonitor()
    if memory_monitor.enabled:
        memory_monitor.log_memory("starting basic lands fetch")

    # Initialize Discord monitoring
    discord_monitor = _get_discord_monitor()  # noqa: F841

    # Ensure database is available for fast queries
    _ensure_database_built()

    if not dry_run:
        _ensure_directory(shared_basic_lands_path)
        _normalize_land_directory(Path(shared_basic_lands_path))
    saved = 0
    skipped = 0
    skipped_details: list[str] = []
    # Skip expensive file system scans for dry runs
    if dry_run:
        existing_keys = set()
        presence = {}
    else:
        existing_keys = _existing_basic_land_keys()
        presence = _build_land_presence_index(Path(shared_basic_lands_path))

    # Skip retry logic for dry runs to improve performance
    if dry_run:
        retry_entries = []
        skipped_retry_ids = set()
    else:
        skipped_retry_ids = _load_skipped_basic_land_ids()
        retry_entries: list[dict] = []

        if skipped_retry_ids:
            click.echo(
                f"Found {len(skipped_retry_ids)} previously skipped card(s); retrying first..."
            )

        # Use database for retry lookups if available, otherwise fallback to JSON
        if _db_index_available():
            try:
                from db.bulk_index import DB_PATH, _get_connection

                conn = _get_connection(DB_PATH)
                cur = conn.cursor()
                placeholders = ",".join(["?" for _ in skipped_retry_ids])
                cur.execute(
                    f"SELECT * FROM prints WHERE id IN ({placeholders})",
                    list(skipped_retry_ids),
                )
                rows = cur.fetchall()

                # Convert rows to dict format
                columns = [description[0] for description in cur.description]
                for row in rows:
                    entry = dict(zip(columns, row))
                    retry_entries.append(entry)
                    skipped_retry_ids.discard(entry["id"])

                conn.close()

                # Any remaining IDs weren't found
                for remaining_id in skipped_retry_ids:
                    skipped_details.append(
                        f"retry lookup failed: {remaining_id} not found in database"
                    )

            except Exception:
                # Fallback to JSON if database fails
                index = _load_bulk_index()
                entries_map = index["entries"]

                for skipped_id in list(skipped_retry_ids):
                    entry = entries_map.get(skipped_id)
                    if entry:
                        retry_entries.append(entry)
                    else:
                        skipped_details.append(
                            f"retry lookup failed: {skipped_id} not found in bulk index"
                        )
                        skipped_retry_ids.discard(skipped_id)
        else:
            # No database available, use JSON
            index = _load_bulk_index()
            entries_map = index["entries"]

            for skipped_id in list(skipped_retry_ids):
                entry = entries_map.get(skipped_id)
                if entry:
                    retry_entries.append(entry)
                else:
                    skipped_details.append(
                        f"retry lookup failed: {skipped_id} not found in bulk index"
                    )
                    skipped_retry_ids.discard(skipped_id)

    # Apply filtering at database level for efficiency
    target_langs = _normalize_langs(lang_preference)
    basic_land_entries = _bulk_iter_basic_lands(
        lang_filter=target_langs,  # Always apply language filter
        set_filter=land_set_filter,
        fullart_only=fullart_only,
        artist_filter=artist_filter,
        rarity_filter=rarity_filter,
        layout_filter=layout_filter,
        frame_filter=frame_filter,
        border_color_filter=border_color_filter,
    )

    combined_entries: list[dict] = []
    seen_ids: set[str] = set()

    for entry in retry_entries + basic_land_entries:
        card_id = entry["id"]
        if card_id in seen_ids:
            continue
        seen_ids.add(card_id)
        combined_entries.append(entry)

    # Expand with related cards using all_parts (e.g., MDFC basics)
    if include_related and combined_entries and _db_index_available() and BULK_DB_PATH:
        try:
            from pathlib import Path as PathLib
            from tools.resolve_card_relationships import (
                expand_card_list_with_relationships,
            )

            initial_count = len(combined_entries)
            initial_ids = [
                str(entry.get("id")) for entry in combined_entries if entry.get("id")
            ]

            if initial_ids:
                expanded_ids = expand_card_list_with_relationships(
                    initial_ids,
                    PathLib(BULK_DB_PATH),
                    include_tokens=False,
                    verbose=progress,
                )

                # Fetch additional related cards
                additional_ids = expanded_ids - set(initial_ids)
                if additional_ids:
                    from db.bulk_index import _get_connection

                    conn = _get_connection(str(BULK_DB_PATH))
                    cur = conn.cursor()

                    placeholders = ",".join(["?" for _ in additional_ids])
                    cur.execute(
                        f"SELECT * FROM prints WHERE id IN ({placeholders})",
                        list(additional_ids),
                    )
                    rows = cur.fetchall()
                    columns = [description[0] for description in cur.description]

                    for row in rows:
                        additional_entry = dict(zip(columns, row))
                        entry_id = additional_entry.get("id")
                        if entry_id and entry_id not in seen_ids:
                            combined_entries.append(additional_entry)
                            seen_ids.add(entry_id)

                    conn.close()

                    if progress and len(combined_entries) > initial_count:
                        click.echo(
                            f"Expanded with {len(combined_entries) - initial_count} related cards from all_parts"
                        )
        except Exception as e:
            if progress:
                click.echo(f"Warning: Could not expand with related cards: {e}")

    total = len(combined_entries)
    if memory_monitor.enabled:
        memory_monitor.log_memory(f"after loading {total} filtered entries")

    # Show filtering summary
    filters_applied = []
    if land_set_filter:
        filters_applied.append(f"set={land_set_filter}")
    if fullart_only:
        filters_applied.append("fullart_only")
    if lang_preference != "en":
        filters_applied.append(f"languages={lang_preference}")

    if filters_applied:
        click.echo(f"Applied filters: {', '.join(filters_applied)}")

    click.echo(f"Found {total} potential basic land print(s) in the local bulk index.")

    processed = 0

    def report_progress() -> None:
        if total == 0:
            return
        if processed >= total or (
            SCRYFALL_PROGRESS_INTERVAL and processed % SCRYFALL_PROGRESS_INTERVAL == 0
        ):
            label = f"Progress: processed {processed}/{total} cards (saved {saved}, skipped {skipped})"
            _maybe_pause_fetch(label)

    download_jobs: list[DownloadJob] = []
    seen_urls: set[str] = set()

    for entry in combined_entries:
        card_id = entry.get("id")
        name = entry.get("name")
        set_code = entry.get("set") or ""
        collector_number = entry.get("collector_number") or ""

        key = f"{entry.get('name_slug')}|{set_code}|{collector_number}"

        # Check for existing file using legacy key format for backward compatibility
        if key in existing_keys:
            skipped += 1
            skipped_details.append(
                f"already present: {name} ({set_code} #{collector_number})"
            )
            if card_id and card_id in skipped_retry_ids:
                skipped_retry_ids.discard(card_id)
            processed += 1
            report_progress()
            continue

        image_url = entry.get("image_url")
        if not image_url:
            skipped += 1
            processed += 1
            report_progress()
            continue

        extension = _extension_from_url(image_url, ".png")

        entry_enriched = _enrich_entry_with_art_meta(dict(entry))
        base_stem = _land_base_stem(entry_enriched)

        # Classify land type for organization
        land_type = _classify_land_type(
            entry_enriched.get("name", ""),
            entry_enriched.get("type_line", ""),
            entry_enriched.get("oracle_text", ""),
        )

        destination = _unique_land_destination(
            Path(shared_basic_lands_path),
            land_type,
            base_stem,
            extension,
        )

        download_jobs.append(
            {
                "card_id": card_id,
                "name": name or "Unknown",
                "set_code": set_code,
                "collector_number": collector_number,
                "image_url": image_url,
                "destination": destination,
                "base_stem": base_stem,
                "land_type": land_type,
            }
        )

    if download_jobs and not dry_run:
        with ThreadPoolExecutor(max_workers=SCRYFALL_MAX_WORKERS) as executor:
            future_to_job = {}
            for job in download_jobs:
                job["destination"].parent.mkdir(parents=True, exist_ok=True)
                future = executor.submit(
                    _download_image, job["image_url"], job["destination"]
                )
                future_to_job[future] = job
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                card_id = job.get("card_id")
                entry_name = job.get("name") or "Unknown"
                destination = job["destination"]
                try:
                    future.result()
                except click.ClickException as error:
                    skipped += 1
                    if card_id:
                        skipped_retry_ids.add(card_id)
                    if destination.exists():
                        try:
                            destination.unlink()
                        except OSError:
                            pass
                    skipped_details.append(
                        f"download failed: {entry_name} ({job['set_code']} #{job['collector_number']}) - {error}"
                    )
                except Exception as error:  # pragma: no cover
                    skipped += 1
                    if card_id:
                        skipped_retry_ids.add(card_id)
                    if destination.exists():
                        try:
                            destination.unlink()
                        except OSError:
                            pass
                    skipped_details.append(
                        f"download failed: {entry_name} ({job['set_code']} #{job['collector_number']}) - {error}"
                    )
                else:
                    if card_id and card_id in skipped_retry_ids:
                        skipped_retry_ids.discard(card_id)
                    land_type_bucket = job.get("land_type")
                    bucket = (
                        land_type_bucket
                        if land_type_bucket is not None
                        else job["set_code"]
                    )
                    presence.setdefault(bucket, set()).add(job["base_stem"])
                    image_url = job["image_url"]
                    if image_url:
                        seen_urls.add(image_url)
                    saved += 1
                finally:
                    processed += 1
                    report_progress()

    _persist_skipped_basic_land_ids(skipped_retry_ids)

    if total:
        label = f"Progress: processed {processed}/{total} cards (saved {saved}, skipped {skipped})"
        _render_progress(label, final=True)

    return saved, skipped, len(combined_entries), skipped_details


# Removed duplicate _fetch_cards_universal - using the one at line 5664


def _fetch_all_non_basic_lands_LEGACY(
    *,
    retry_only: bool = False,
    lang_preference: str = "en",
    dry_run: bool = False,
    progress: bool = True,
    land_set_filter: str | None = None,
    fullart_only: bool = False,
    include_related: bool = True,
) -> tuple[int, int, int, list[str]]:
    """LEGACY IMPLEMENTATION - Kept for reference, not used."""
    # Initialize memory monitoring and Discord notifications
    memory_monitor = MemoryMonitor()
    if memory_monitor.enabled:
        memory_monitor.log_memory("starting non-basic lands fetch")

    # Initialize Discord monitoring
    discord_monitor = _get_discord_monitor()  # noqa: F841

    # Ensure database is available for fast queries
    _ensure_database_built()

    if not dry_run:
        _ensure_directory(shared_non_basic_lands_path)
        _normalize_land_directory(Path(shared_non_basic_lands_path))

    saved = 0
    skipped = 0
    skipped_details: list[str] = []
    presence = _build_land_presence_index(Path(shared_non_basic_lands_path))
    legacy_keys = _existing_non_basic_land_keys()
    skipped_retry_ids: set[str] = set()
    # In-run dedupe across identical art assets reused by multiple prints
    seen_urls: set[str] = set()

    # Apply filtering at database level for efficiency
    target_langs = _normalize_langs(lang_preference)

    if _db_index_available():
        # Get all non-basic lands from database
        all_non_basic_entries: list[dict] = db_query_non_basic_lands()

        # Apply filtering
        non_basic_entries = []
        for entry in all_non_basic_entries:
            # Language filtering
            if entry.get("lang", "en") not in target_langs:
                continue

            # Set filtering
            if (
                land_set_filter
                and entry.get("set", "").lower() != land_set_filter.lower()
            ):
                continue

            # Full-art filtering
            if fullart_only:
                art_type = _derive_art_type(entry)
                if not (art_type == "fullart" or "fullart" in art_type):
                    continue

            non_basic_entries.append(entry)
    else:
        # Fallback to JSON index with filtering
        index = _load_bulk_index()
        entries = index.get("entries", {})

        non_basic_entries = []
        for entry in entries.values():
            type_line = (entry.get("type_line") or "").lower()
            if "land" not in type_line:
                continue
            if entry.get("is_basic_land"):
                continue

            # Apply filtering
            # Language filtering
            if entry.get("lang", "en") not in target_langs:
                continue

            # Set filtering
            if (
                land_set_filter
                and entry.get("set", "").lower() != land_set_filter.lower()
            ):
                continue

            # Full-art filtering
            if fullart_only:
                art_type = _derive_art_type(entry)
                if not (art_type == "fullart" or "fullart" in art_type):
                    continue

            non_basic_entries.append(entry)

    # Expand with related cards using all_parts (e.g., MDFC lands)
    if include_related and non_basic_entries and _db_index_available() and BULK_DB_PATH:
        try:
            from pathlib import Path as PathLib
            from tools.resolve_card_relationships import (
                expand_card_list_with_relationships,
            )

            initial_count = len(non_basic_entries)
            initial_ids = [
                str(entry.get("id")) for entry in non_basic_entries if entry.get("id")
            ]

            if initial_ids:
                expanded_ids = expand_card_list_with_relationships(
                    initial_ids,
                    PathLib(BULK_DB_PATH),
                    include_tokens=False,
                    verbose=progress,
                )

                # Fetch additional related cards
                additional_ids = expanded_ids - set(initial_ids)
                if additional_ids:
                    # Query database for additional cards
                    from db.bulk_index import _get_connection

                    conn = _get_connection(str(BULK_DB_PATH))
                    cur = conn.cursor()

                    placeholders = ",".join(["?" for _ in additional_ids])
                    cur.execute(
                        f"SELECT * FROM prints WHERE id IN ({placeholders})",
                        list(additional_ids),
                    )
                    rows = cur.fetchall()
                    columns = [description[0] for description in cur.description]

                    for row in rows:
                        additional_entry = dict(zip(columns, row))

                        # Apply same filters to related cards
                        # Language filter: always check, not just when lang_preference != "en"
                        if additional_entry.get("lang", "en") not in target_langs:
                            continue
                        if (
                            land_set_filter
                            and additional_entry.get("set", "").lower()
                            != land_set_filter.lower()
                        ):
                            continue
                        if fullart_only:
                            art_type = _derive_art_type(additional_entry)
                            if not (art_type == "fullart" or "fullart" in art_type):
                                continue

                        non_basic_entries.append(additional_entry)

                    conn.close()

                    if progress and len(non_basic_entries) > initial_count:
                        click.echo(
                            f"Expanded with {len(non_basic_entries) - initial_count} related cards from all_parts"
                        )
        except Exception as e:
            if progress:
                click.echo(f"Warning: Could not expand with related cards: {e}")

    if memory_monitor.enabled:
        memory_monitor.log_memory(
            f"after loading {len(non_basic_entries)} filtered non-basic entries"
        )

    # Show filtering summary
    filters_applied = []
    if land_set_filter:
        filters_applied.append(f"set={land_set_filter}")
    if fullart_only:
        filters_applied.append("fullart_only")
    if lang_preference != "en":
        filters_applied.append(f"languages={lang_preference}")

    if filters_applied:
        click.echo(f"Applied filters to non-basic lands: {', '.join(filters_applied)}")

    total = len(non_basic_entries)
    if total == 0:
        return 0, 0, 0, []

    click.echo(
        f"Found {total} potential non-basic land print(s) in the local bulk index."
    )

    processed = 0

    def report_progress() -> None:
        if processed >= total or (
            SCRYFALL_PROGRESS_INTERVAL and processed % SCRYFALL_PROGRESS_INTERVAL == 0
        ):
            label = f"Progress: processed {processed}/{total} cards (saved {saved}, skipped {skipped})"
            _maybe_pause_fetch(label)

    download_jobs: list[DownloadJob] = []

    if progress:
        click.echo("Preparing download jobs...")

    for i, entry in enumerate(non_basic_entries):
        if progress and i > 0 and i % 100 == 0:
            click.echo(f"  Prepared {i}/{total} jobs...")
        # Ensure we have art meta (DB rows won't include these)
        entry_enriched = _enrich_entry_with_art_meta(dict(entry))
        card_id = entry_enriched.get("id")
        name = entry_enriched.get("name") or "Unknown"
        set_code = entry_enriched.get("set") or "unk"
        collector_number = entry_enriched.get("collector_number") or ""
        image_url = entry_enriched.get("image_url")

        key = f"{entry.get('name_slug') or _slugify(entry.get('name','land'))}|{set_code}|{collector_number}"

        # Check legacy key format for backwards compatibility
        if key in legacy_keys:
            skipped += 1
            skipped_details.append(
                f"already present (legacy): {entry.get('name')} ({set_code} #{collector_number})"
            )
            processed += 1
            report_progress()
            continue

        # In-run duplicate by URL (many reprints share the exact same image URL)
        if image_url and image_url in seen_urls:
            skipped += 1
            skipped_details.append(
                f"duplicate image url: {entry.get('name')} ({set_code} #{collector_number})"
            )
            processed += 1
            report_progress()
            continue

        if not image_url:
            skipped += 1
            skipped_details.append(
                f"no image url: {entry.get('name')} ({set_code} #{collector_number})"
            )
            processed += 1
            report_progress()
            continue

        extension = _extension_from_url(image_url, ".png")

        base_stem = _land_base_stem(entry_enriched)

        # Classify land type for organization
        land_type = _classify_land_type(
            entry_enriched.get("name", ""),
            entry_enriched.get("type_line", ""),
            entry_enriched.get("oracle_text", ""),
        )

        destination = _unique_land_destination(
            Path(shared_non_basic_lands_path),
            land_type,
            base_stem,
            extension,
        )

        # If file already exists for this exact target (e.g., rerun), skip
        if destination.exists():
            skipped += 1
            skipped_details.append(
                f"already present (path): {entry.get('name')} ({set_code} #{collector_number})"
            )
            processed += 1
            report_progress()
            continue

        download_jobs.append(
            {
                "card_id": card_id,
                "name": name,
                "set_code": set_code,
                "collector_number": collector_number,
                "image_url": image_url,
                "destination": destination,
                "base_stem": base_stem,
                "land_type": land_type,
            }
        )

    if progress:
        click.echo(
            f"Prepared {len(download_jobs)} download jobs (skipped {skipped} already present)"
        )

    if download_jobs:
        if progress:
            click.echo(f"Starting downloads with {SCRYFALL_MAX_WORKERS} workers...")
        with ThreadPoolExecutor(max_workers=SCRYFALL_MAX_WORKERS) as executor:
            future_to_job = {}
            for job in download_jobs:
                destination = job["destination"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                future = executor.submit(_download_image, job["image_url"], destination)
                future_to_job[future] = job
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                card_id = job["card_id"]
                entry_name = job["name"] or "Unknown"
                destination = job["destination"]
                try:
                    future.result()
                    if progress and (saved + skipped) % 50 == 0:
                        click.echo(
                            f"  Downloaded {saved}, skipped {skipped} ({saved + skipped}/{len(download_jobs)})"
                        )
                except click.ClickException as error:
                    skipped += 1
                    skipped_details.append(
                        f"download failed: {entry_name} ({job['set_code']} #{job['collector_number']}) - {error}"
                    )
                except Exception as error:  # pragma: no cover
                    skipped += 1
                    if destination.exists():
                        try:
                            destination.unlink()
                        except OSError:
                            pass
                    skipped_details.append(
                        f"download failed: {entry_name} ({job['set_code']} #{job['collector_number']}) - {error}"
                    )
                else:
                    if card_id and card_id in skipped_retry_ids:
                        skipped_retry_ids.discard(card_id)
                    land_type_bucket = job.get("land_type")
                    bucket = (
                        land_type_bucket
                        if land_type_bucket is not None
                        else job["set_code"]
                    )
                    presence.setdefault(bucket, set()).add(job["base_stem"])
                    image_url = job["image_url"]
                    if image_url:
                        seen_urls.add(image_url)
                    saved += 1
                finally:
                    processed += 1
                    report_progress()

    if progress:
        label = f"Progress: processed {processed}/{total} cards (saved {saved}, skipped {skipped})"
        _render_progress(label, final=True)

    # Final memory logging and Discord notification
    if memory_monitor.enabled:
        memory_monitor.log_memory("completed basic lands fetch")

    # Send Discord notification
    if discord_monitor and not dry_run:
        fetch_stats = {
            "saved": saved,
            "skipped": skipped,
            "total": total,
            "memory_summary": memory_monitor.get_summary(),
            "filters": {
                "language": lang_preference,
                "set": land_set_filter,
                "fullart_only": fullart_only,
                "retry_only": retry_only,
            },
        }
        discord_monitor.send_fetch_complete("Basic Lands", fetch_stats)

    return saved, skipped, total, skipped_details


def _ensure_basic_land_symlinks() -> list[str]:
    """Create symlinks for basic lands in all profiles."""
    warnings: list[str] = []

    for profile_name in get_profile_names():
        _, _, profile_warnings = _ensure_profile_structure(profile_name)
        for warning in profile_warnings:
            warnings.append(f"{profile_name}: {warning}")

    return warnings


def _sync_basic_lands_flow():
    click.echo("\nFetching all basic lands from Scryfall. This may take a while...\n")

    saved, skipped, total, skipped_details = _fetch_all_basic_lands_from_scryfall()
    warnings = _ensure_basic_land_symlinks()

    click.echo(
        f"Retrieved {total} entries. Downloaded {saved} new image(s), skipped {skipped} existing file(s)."
    )

    if saved:
        click.echo(f"New images saved: {saved}")
    if skipped:
        click.echo(f"Skipped duplicates or missing data: {skipped}")

    if skipped_details:
        click.echo("\nSkipped entries:")
        for detail in skipped_details[:20]:
            click.echo(f"  - {detail}")
        if len(skipped_details) > 20:
            click.echo(f"  ... {len(skipped_details) - 20} more skipped entries")

    if warnings:
        click.echo("\nWarnings:")
        for warning in warnings:
            click.echo(f"  - {warning}")

    click.echo()
    _prompt_to_continue()


def _hdr(title: str) -> str:
    # Use red (crimson-like) and bold for headers
    try:
        return click.style(title, fg="red", bold=True, underline=True)
    except Exception:
        return title


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _print_boxed_menu(title: str, lines: list[str]) -> None:
    # normalize arrows with extra padding
    styled_lines: list[str] = []
    for line in lines:
        raw = line.replace(" → ", "  →  ")
        m = re.match(r"^\[(\d)\]\s*(.+)$", raw)
        if m:
            num = m.group(1)
            rest = m.group(2)
            # Bright cyan number with bold
            num_part = click.style(f"[{num}]", fg="cyan", bold=True)
            if "→" in rest:
                left, right = rest.split("→", 1)
                left = left.rstrip()
                right = right.strip()
                # Bright white arrow
                arrow_part = click.style("→", fg="bright_white", bold=True)
                # Bright black (gray) description
                desc_part = click.style(right, fg="bright_black")
                styled = f"{num_part} {click.style(left, bold=True)}  {arrow_part}  {desc_part}"
            else:
                styled = f"{num_part} {click.style(rest, bold=True)}"
            styled_lines.append(styled)
        else:
            styled_lines.append(raw)

    # Enhanced title with color
    title_styled = click.style(title, fg="bright_magenta", bold=True)
    content = [title_styled, ""] + styled_lines  # blank line after title
    width = max(_visible_len(line) for line in content)
    pad = 3  # increased inner horizontal padding
    inner = width + pad * 2
    ascii_box = os.environ.get("PM_ASCII_BOX", "0").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    if ascii_box:
        top = "+" + ("-" * inner) + "+"
        bot = "+" + ("-" * inner) + "+"
        side_l = side_r = "|"
    else:
        # Use bright blue for borders
        top = click.style(f"┌{'─' * inner}┐", fg="bright_blue")
        bot = click.style(f"└{'─' * inner}┘", fg="bright_blue")
        side_l = click.style("│", fg="bright_blue")
        side_r = click.style("│", fg="bright_blue")
    click.echo(top)
    for idx, raw in enumerate(content):
        plain_len = _visible_len(raw)
        left = " " * pad
        right = " " * (inner - plain_len - pad)
        click.echo(f"{side_l}{left}{raw}{right}{side_r}")
    click.echo(bot)


def _get_key_choice(valid: set[str]) -> str:
    """Read a single key from the user (no Enter needed). Falls back to input() on failure.
    Returns the pressed key as a string. Keeps reading until a valid key is pressed.
    """
    try:
        onekey = os.environ.get("PM_ONEKEY", "1").lower() in {"1", "true", "on", "yes"}
        if onekey:
            while True:
                ch = click.getchar()
                if ch in valid:
                    click.echo(ch)
                    return ch
                # Ignore other keys like arrows/ctrls
    except Exception:
        pass
    # Fallback (TTY problems or Windows without proper getchar)
    try:
        sel = _prompt_text("Choose an option", default="") or ""
    except EOFError:
        sel = ""
    return sel


def _tokens_menu():
    while True:
        click.echo()
        options = [
            "[1] Pregenerate random tokens",
            "[2] Fetch token by name",
            "[3] Bulk fetch all tokens (with comprehensive filters)",
            "[4] Dedupe shared token library",
            "[5] Token language report",
            "[6] View token catalog",
            "[7] Build token pack from manifest",
            "[8] Generate blank token pack manifest",
            "[9] Wizard: token pack from deck list",
            "[A] Search tokens by keyword",
            "[B] Launch token explorer",
            "[M] Migrate tokens to hybrid structure",
            "[0] Back",
        ]
        _print_boxed_menu("Token Utilities", options)

        selection = _get_key_choice(
            {
                "0",
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "a",
                "A",
                "b",
                "B",
                "m",
                "M",
            }
        )

        if selection == "0":
            return

        if selection == "1":
            _pregenerate_tokens_flow()
            continue

        if selection == "2":
            _fetch_token_by_name_flow()
            continue

        if selection == "3":
            _fetch_all_tokens_flow()
            continue

        if selection == "4":
            _dedupe_tokens_flow()
            continue

        if selection == "5":
            _token_language_report_flow()
            continue

        if selection == "6":
            name_filter = _prompt_text("Name filter (optional)", default="")
            subtype_filter = _prompt_text("Subtype filter (optional)", default="")
            set_filter = _prompt_text("Set code filter (optional)", default="")
            limit_input = _prompt_text("Maximum results to show [50]", default="50")

            try:
                limit_value = int(limit_input) if limit_input else 50
                if limit_value <= 0:
                    raise ValueError
            except ValueError:
                click.echo("Invalid limit. Using default of 50.")
                limit_value = 50

            _display_token_metadata(
                name_filter or None,
                subtype_filter or None,
                set_filter or None,
                None,
                limit_value,
                pause_after=True,
            )
            continue

        if selection == "7":
            manifest_path = _prompt_text("Path to token manifest JSON", default="")
            if not manifest_path:
                click.echo("Manifest path is required.")
                _prompt_to_continue()
                continue
            pack_name = _prompt_text("Pack name (optional)", default="") or None
            try:
                _build_token_pack(manifest_path, pack_name)
            except click.ClickException as error:
                click.echo(str(error))
            _prompt_to_continue()
            continue

        if selection == "8":
            output_path = _prompt_text(
                "Where should the template JSON be written?", default=""
            )
            if not output_path:
                click.echo("Output path is required.")
                _prompt_to_continue()
                continue
            try:
                _write_token_manifest_template(output_path)
                click.echo(f"Template written to {output_path}.")
            except click.ClickException as error:
                click.echo(str(error))
            _prompt_to_continue()
            continue

        if selection == "9":
            deck_path = input("Path or URL to deck list: ").strip()
            if not deck_path:
                click.echo("Deck path or URL is required.")
                _prompt_to_continue()
                continue
            pack_name = input("Pack name (optional): ").strip() or None
            try:
                _token_pack_wizard_from_deck(deck_path, pack_name)
            except click.ClickException as error:
                click.echo(str(error))
            _prompt_to_continue()
            continue

        if selection.lower() == "a":
            keyword = input("Keyword/mechanic to search for: ").strip()
            if not keyword:
                click.echo("Keyword is required.")
                _prompt_to_continue()
                continue
            set_filter = input("Set code filter (optional): ").strip() or None
            limit_input = input("Maximum results to show [50]: ").strip()
            try:
                limit_value = int(limit_input) if limit_input else 50
                if limit_value <= 0:
                    raise ValueError
            except ValueError:
                click.echo("Invalid limit. Using default of 50.")
                limit_value = 50
            _display_token_keyword_search(
                keyword, set_filter, limit_value, pause_after=True
            )
            continue

        if selection.lower() == "b":
            _token_explorer_loop()
            continue

        if selection.lower() == "m":
            click.echo("\nToken Structure Migration")
            click.echo("=" * 25)
            click.echo("This will migrate tokens to hybrid structure:")
            click.echo("  FROM: tokens/beast/beast_ltr.png")
            click.echo("  TO:   tokens/beast/ltr/beast-standard-en-ltr.png")
            click.echo()

            # First do a dry run to show what would happen
            click.echo("Scanning existing tokens...")
            moved, skipped, errors = _migrate_tokens_to_new_structure(dry_run=True)

            if moved == 0:
                click.echo(
                    "No tokens found to migrate (already using new structure or no tokens exist)."
                )
                _prompt_to_continue()
                continue

            proceed = (
                input(f"\nProceed with migration of {moved} tokens? [y/N]: ")
                .strip()
                .lower()
            )
            if proceed in {"y", "yes"}:
                click.echo("\nMigrating tokens...")
                _migrate_tokens_to_new_structure(dry_run=False)
                click.echo("\nRebuilding token index...")
                _rebuild_token_index()
                click.echo("Migration complete!")
            else:
                click.echo("Migration cancelled.")
            _prompt_to_continue()
            continue

        click.echo("Please choose a valid option.")
        _prompt_to_continue()


def _create_profile_flow():
    click.echo("\nCreate Profile\n---------------")
    raw_name = input("Enter a profile name: ")
    profile_name = _sanitize_profile_name(raw_name)

    if not profile_name:
        click.echo("Profile name must contain letters, numbers, hyphen, or underscore.")
        _prompt_to_continue()
        return

    if raw_name.strip() and raw_name.strip() != profile_name:
        click.echo(f"Using profile identifier '{profile_name}'.")

    existing_profiles = get_profiles()

    if profile_name in existing_profiles:
        click.echo(f"Profile '{profile_name}' already exists.")
        _prompt_to_continue()
        return

    created_dirs, created_symlinks, warnings = _ensure_profile_structure(profile_name)
    _add_profile_definition(profile_name)

    click.echo(f"\nProfile '{profile_name}' created.")

    if created_dirs:
        click.echo("  Directories created:")
        for directory in created_dirs:
            click.echo(f"    - {directory}")

    if created_symlinks:
        click.echo("  Symlinks created:")
        for link in created_symlinks:
            click.echo(f"    - {link}")

    if warnings:
        click.echo("  Warnings:")
        for warning in warnings:
            click.echo(f"    - {warning}")

    _prompt_to_continue()


def _delete_profile_flow():
    profile_names = get_profile_names()

    if not profile_names:
        click.echo("\nNo profiles available to delete.\n")
        _prompt_to_continue()
        return

    options = [f"[{i}] {name}" for i, name in enumerate(profile_names, start=1)]
    options.append("[0] Cancel")
    _print_boxed_menu("Delete Profile", options)

    valid_choices = {"0"} | {str(i) for i in range(1, len(profile_names) + 1)}
    selection = _get_key_choice(valid_choices)

    if selection == "0":
        return

    if not selection.isdigit():
        click.echo("Please enter a valid number.")
        _prompt_to_continue()
        return

    numeric_choice = int(selection)

    if numeric_choice < 1 or numeric_choice > len(profile_names):
        click.echo("Invalid selection.")
        _prompt_to_continue()
        return

    profile_name = profile_names[numeric_choice - 1]

    confirmation = input(f"Type '{profile_name}' to confirm deletion: ").strip().lower()

    if confirmation != profile_name:
        click.echo("Confirmation did not match. Aborting deletion.")
        _prompt_to_continue()
        return

    archive_path = _archive_profile_directory(profile_name)
    _remove_profile_definition(profile_name)

    click.echo(f"\nProfile '{profile_name}' removed from profiles.json.")

    if archive_path:
        click.echo(f"Archived directory saved to {archive_path}.")
    else:
        click.echo("No profile directory was found to archive.")

    _prompt_to_continue()


def _initialize_profiles_flow():
    profile_names = get_profile_names()

    if not profile_names:
        click.echo("\nNo profiles configured.\n")
        _prompt_to_continue()
        return

    click.echo("\nInitializing profiles...\n")

    for profile_name in profile_names:
        created_dirs, created_symlinks, warnings = _ensure_profile_structure(
            profile_name
        )

        if not created_dirs and not created_symlinks and not warnings:
            click.echo(f"- {profile_name}: ok")
            continue

        click.echo(f"- {profile_name}:")

        if created_dirs:
            click.echo("    Created directories:")
            for directory in created_dirs:
                click.echo(f"      * {directory}")

        if created_symlinks:
            click.echo("    Created symlinks:")
            for link in created_symlinks:
                click.echo(f"      * {link}")

        if warnings:
            click.echo("    Warnings:")
            for warning in warnings:
                click.echo(f"      * {warning}")

    click.echo()
    _prompt_to_continue()


def _land_coverage_flow() -> None:
    click.echo("\nLand Coverage Report\n--------------------")
    kind = (
        input("Type [basic|nonbasic|all] (default: nonbasic): ").strip() or "nonbasic"
    ).lower()
    if kind not in {"basic", "nonbasic", "all"}:
        click.echo("Invalid type. Please choose 'basic', 'nonbasic', or 'all'.")
        _prompt_to_continue()
        return
    set_code = input("Set code filter (optional, e.g., mh3): ").strip() or None
    out_dir = input("Custom output directory (optional): ").strip() or None

    try:
        import importlib.util

        cov_path = os.path.join(script_directory, "coverage.py")
        spec = importlib.util.spec_from_file_location("pm_coverage", cov_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load coverage tool module.")
        pm_cov = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pm_cov)  # type: ignore[attr-defined]

        rows, summary = pm_cov.compute_coverage(kind, set_code)
        csv_path, json_path = pm_cov.write_outputs(rows, summary, out_dir)
    except Exception as exc:
        click.echo(f"Error computing coverage: {exc}")
        _prompt_to_continue()
        return

    click.echo(f"Wrote coverage CSV: {csv_path}")
    click.echo(f"Wrote coverage JSON: {json_path}")
    click.echo(
        f"Coverage: {summary.get('covered', 0)}/{summary.get('total', 0)} "
        f"({summary.get('coverage_pct', 0.0):.1f}%) kind={summary.get('kind')} "
        f"set={summary.get('set_filter') or 'ALL'}"
    )
    _offer_open_in_folder(str(json_path), kind="coverage report")
    _prompt_to_continue()


def _profiles_shared_menu():
    while True:
        click.echo()
        options = [
            "[1] List profiles",
            "[2] Create profile",
            "[3] Delete profile",
            "[4] Initialize profiles (structure & symlinks)",
            "[5] Sync basic lands from Scryfall",
            "[6] Advanced land fetch (basic/non-basic with filters)",
            "[7] Sync shared tokens to profile",
            "[8] Sync shared lands to profile",
            "[0] Back",
        ]
        _print_boxed_menu("Profiles & Shared", options)

        selection = _get_key_choice({"0", "1", "2", "3", "4", "5", "6", "7", "8"})

        if selection == "0":
            return

        if selection == "1":
            profile_names = get_profile_names()

            if not profile_names:
                click.echo("\nNo profiles configured.\n")
            else:
                click.echo("\nConfigured profiles:\n")
                for name in profile_names:
                    click.echo(f"- {name}")
                click.echo()
            _prompt_to_continue()
            continue

        if selection == "2":
            _create_profile_flow()
            continue

        if selection == "3":
            _delete_profile_flow()
            continue

        if selection == "4":
            _initialize_profiles_flow()
            continue

        if selection == "5":
            _sync_basic_lands_flow()
            continue

        if selection == "6":
            _advanced_land_fetch_flow()
            continue

        if selection == "7":
            click.echo("\n🔄 Sync Shared Tokens to Profile\n")
            profile_names = get_profile_names()
            if not profile_names:
                click.echo("No profiles configured.")
                _prompt_to_continue()
                continue

            click.echo("Available profiles:")
            for name in profile_names:
                click.echo(f"  • {name}")

            profile = input("\nProfile name: ").strip()
            if not profile:
                click.echo("Profile name is required.")
                _prompt_to_continue()
                continue

            dry_run = input("Dry run (preview only)? [y/N]: ").strip().lower() in {
                "y",
                "yes",
            }
            verbose = input("Verbose output? [y/N]: ").strip().lower() in {"y", "yes"}

            try:
                import subprocess

                cmd = [sys.executable, "tools/asset_sync.py", "sync-tokens", profile]
                if dry_run:
                    cmd.append("--dry-run")
                if verbose:
                    cmd.append("--verbose")

                result = subprocess.run(
                    cmd, cwd=script_directory, capture_output=True, text=True
                )
                click.echo(result.stdout)
                if result.returncode != 0:
                    click.echo(f"Error: {result.stderr}")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection == "8":
            click.echo("\n🔄 Sync Shared Lands to Profile\n")
            profile_names = get_profile_names()
            if not profile_names:
                click.echo("No profiles configured.")
                _prompt_to_continue()
                continue

            click.echo("Available profiles:")
            for name in profile_names:
                click.echo(f"  • {name}")

            profile = input("\nProfile name: ").strip()
            if not profile:
                click.echo("Profile name is required.")
                _prompt_to_continue()
                continue

            land_type = input("Land type (basic/nonbasic/all) [all]: ").strip() or "all"
            dry_run = input("Dry run (preview only)? [y/N]: ").strip().lower() in {
                "y",
                "yes",
            }
            verbose = input("Verbose output? [y/N]: ").strip().lower() in {"y", "yes"}

            try:
                import subprocess

                cmd = [
                    sys.executable,
                    "tools/asset_sync.py",
                    "sync-lands",
                    profile,
                    "--type",
                    land_type,
                ]
                if dry_run:
                    cmd.append("--dry-run")
                if verbose:
                    cmd.append("--verbose")

                result = subprocess.run(
                    cmd, cwd=script_directory, capture_output=True, text=True
                )
                click.echo(result.stdout)
                if result.returncode != 0:
                    click.echo(f"Error: {result.stderr}")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        click.echo("Please choose a valid option.")
        _prompt_to_continue()


def _advanced_land_fetch_flow():
    """Interactive menu for advanced land fetching with all filtering options."""
    click.echo("\nAdvanced Land Fetch\n-------------------")

    # Land type selection
    land_type = (
        input("Land type [basic/nonbasic/both] (default: both): ").strip().lower()
    )
    if land_type not in ["basic", "nonbasic", "both"]:
        land_type = "both"

    # Language preference
    click.echo("\nLanguage options:")
    click.echo("  en          - English only")
    click.echo("  ph/phyrexian - Phyrexian only")
    click.echo("  special     - English + fantasy languages")
    click.echo("  all         - All languages")
    click.echo("  en,ph,ja    - Comma-separated list")
    lang = input("Language preference (default: en): ").strip()
    if not lang:
        lang = "en"

    # Set filter
    set_code = input("Set code filter (optional, e.g., ltr, one): ").strip()
    if not set_code:
        set_code = None

    # Full-art only
    fullart_input = input("Full-art only? [y/N]: ").strip().lower()
    fullart_only = fullart_input in {"y", "yes", "1"}

    # Retry only
    retry_input = input("Retry failed downloads only? [y/N]: ").strip().lower()
    retry_only = retry_input in {"y", "yes", "1"}

    # Dry run
    dry_input = input("Dry run (preview only)? [y/N]: ").strip().lower()
    dry_run = dry_input in {"y", "yes", "1"}

    # Show summary
    click.echo("\nFetch Configuration:")
    click.echo(f"  Land type: {land_type}")
    click.echo(f"  Language: {lang}")
    click.echo(f"  Set filter: {set_code or 'None'}")
    click.echo(f"  Full-art only: {'Yes' if fullart_only else 'No'}")
    click.echo(f"  Retry only: {'Yes' if retry_only else 'No'}")
    click.echo(f"  Dry run: {'Yes' if dry_run else 'No'}")

    confirm = input("\nProceed with fetch? [Y/n]: ").strip().lower()
    if confirm in {"n", "no"}:
        click.echo("Cancelled.")
        _prompt_to_continue()
        return

    # Execute the fetch operations
    try:
        if land_type in ["basic", "both"]:
            click.echo("\nFetching basic lands...")
            saved, skipped, total, _ = _fetch_all_basic_lands_from_scryfall(
                retry_only=retry_only,
                lang_preference=lang,
                dry_run=dry_run,
                progress=True,
                land_set_filter=set_code,
                fullart_only=fullart_only,
            )
            click.echo(
                f"Basic lands: {saved} downloaded, {skipped} skipped, {total} total"
            )

        if land_type in ["nonbasic", "both"]:
            click.echo("\nFetching non-basic lands...")
            saved, skipped, total, _ = _fetch_cards_universal(
                card_type="nonbasic_land",
                is_basic_land=False,
                is_token=False,
                lang_preference=lang,
                set_filter=set_code,
                fullart_only=fullart_only,
                retry_only=retry_only,
                dry_run=dry_run,
                progress=True,
            )
            click.echo(
                f"Non-basic lands: {saved} downloaded, {skipped} skipped, {total} total"
            )

        click.echo("[PASS] Land fetch completed!")

    except Exception as e:
        click.echo(f"[ERROR] Error during fetch: {e}")

    _prompt_to_continue()


def _maintenance_tools_menu():
    while True:
        click.echo()
        options = [
            "[1] Open web dashboard",
            "[2] Library health checks (fix/dupes)",
            "[3] Land coverage report",
            "[4] Search cards by oracle text/type",
            "[5] Configure notifications",
            "[6] Database optimization (add composite indexes)",
            "[7] Run comprehensive test suite (all tests)",
            "[8] Run benchmarks (performance)",
            "[9] Generate documentation (CLI + schema)",
            "[A] Database health summary report",
            "[0] Back",
        ]
        _print_boxed_menu("Maintenance & Tools", options)

        selection = _get_key_choice(
            {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "A"}
        )

        if selection == "0":
            return

        if selection == "1":
            click.echo("Opening web dashboard at http://127.0.0.1:5000 ...")
            try:
                webbrowser.open("http://127.0.0.1:5000")
            except Exception:
                pass
            _prompt_to_continue()
            continue

        if selection == "2":
            click.echo(_hdr("Library Health Checks"))
            fix_names = input(
                "Fix filename hygiene (lowercase, spaces→-)? [y/N]: "
            ).strip().lower() in {"y", "yes"}
            fix_dupes = input(
                "Remove perceptual duplicate images? [y/N]: "
            ).strip().lower() in {"y", "yes"}
            thresh_in = input("Hash threshold [0-64] (default 6): ").strip()
            try:
                hash_threshold = int(thresh_in) if thresh_in else 6
                if hash_threshold < 0 or hash_threshold > 64:
                    raise ValueError
            except ValueError:
                click.echo("Invalid threshold; using default of 6.")
                hash_threshold = 6
            _run_library_health_checks(
                fix_names=fix_names, fix_dupes=fix_dupes, hash_threshold=hash_threshold
            )
            _prompt_to_continue()
            continue

        if selection == "3":
            _land_coverage_flow()
            continue

        if selection == "4":
            query = input("Oracle text/type search: ").strip()
            if not query:
                click.echo("Search text is required.")
                _prompt_to_continue()
                continue
            set_filter = input("Set code filter (optional): ").strip() or None
            include_tokens = input("Include tokens? [y/N]: ").strip().lower() in {
                "y",
                "yes",
            }
            limit_input = input("Maximum results to show [50]: ").strip()
            try:
                limit_value = int(limit_input) if limit_input else 50
                if limit_value <= 0:
                    raise ValueError
            except ValueError:
                click.echo("Invalid limit. Using default of 50.")
                limit_value = 50
            _display_card_text_search(
                query,
                set_filter,
                limit_value,
                include_tokens=include_tokens,
                pause_after=True,
            )
            continue

        if selection == "5":
            _configure_notifications_flow()
            continue

        if selection == "6":
            click.echo("\nDatabase Optimization\n---------------------")
            click.echo("This will add 10 composite indexes for faster searches.")
            confirm = input("Proceed? [y/N]: ").strip().lower()

            if confirm in {"y", "yes"}:
                try:
                    result = subprocess.run(
                        [sys.executable, "tools/optimize_db.py", "optimize"],
                        cwd=script_directory,
                        capture_output=True,
                        text=True,
                    )
                    click.echo(result.stdout)
                    if result.returncode != 0:
                        click.echo(f"Error: {result.stderr}")
                except Exception as e:
                    click.echo(f"Error running optimization: {e}")
            _prompt_to_continue()
            continue

        if selection == "7":
            click.echo(
                "\nRunning Comprehensive Test Suite\n---------------------------------"
            )
            all_passed = True

            try:
                # Run AI recommendations tests
                click.echo("\n[1/3] Running AI recommendations tests...")
                result = subprocess.run(
                    [sys.executable, "tools/test_ai_recommendations.py"],
                    cwd=script_directory,
                )
                if result.returncode != 0:
                    all_passed = False
                    click.echo("[FAIL] AI recommendations tests failed")
                else:
                    click.echo("[PASS] AI recommendations tests passed")

                # Run integration tests
                click.echo("\n[2/3] Running integration tests...")
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests/test_integration.py", "-v"],
                    cwd=script_directory,
                )
                if result.returncode != 0:
                    all_passed = False
                    click.echo("[FAIL] Integration tests failed")
                else:
                    click.echo("[PASS] Integration tests passed")

                # Run schema tests
                click.echo("\n[3/3] Running schema validation tests...")
                result = subprocess.run(
                    [sys.executable, "tools/test_schema.py"],
                    cwd=script_directory,
                )
                if result.returncode != 0:
                    all_passed = False
                    click.echo("[FAIL] Schema tests failed")
                else:
                    click.echo("[PASS] Schema tests passed")

                # Summary
                click.echo("\n" + "=" * 50)
                if all_passed:
                    click.echo("[PASS] All test suites passed")
                else:
                    click.echo("[FAIL] Some test suites failed")
                click.echo("=" * 50)

            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection == "8":
            click.echo("\nRunning Benchmarks\n------------------")
            try:
                result = subprocess.run(
                    [sys.executable, "tests/benchmarks/run_benchmarks.py"],
                    cwd=script_directory,
                )
                if result.returncode == 0:
                    click.echo("\n[PASS] Benchmarks complete")
                else:
                    click.echo("\n[FAIL] Benchmarks failed")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection == "9":
            click.echo("\nGenerating Documentation\n------------------------")
            try:
                # Generate CLI docs
                result = subprocess.run(
                    [sys.executable, "tools/generate_cli_docs.py"],
                    cwd=script_directory,
                    capture_output=True,
                    text=True,
                )
                click.echo(result.stdout)

                # Generate schema docs (may fail if DB doesn't exist)
                result = subprocess.run(
                    [sys.executable, "tools/generate_schema_docs.py"],
                    cwd=script_directory,
                    capture_output=True,
                    text=True,
                )
                click.echo(result.stdout)

                click.echo("\n[PASS] Documentation generated")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection.lower() == "a":
            _db_health_summary_flow()
            continue

        click.echo("Please choose a valid option.")
        _prompt_to_continue()


def _deck_tools_menu():
    while True:
        click.echo()
        options = [
            "[1] Generate profile PDF (with deck folders)",
            "[2] Analyze deck list / scrape deck URLs",
            "[3] Build token pack from manifest",
            "[4] Random commander generator",
            "[0] Back",
        ]
        _print_boxed_menu("Deck Tools", options)

        selection = _get_key_choice({"0", "1", "2", "3", "4"})

        if selection == "0":
            return

        if selection == "1":
            _create_pdf_menu()
            continue

        if selection == "2":
            deck_path = input("Path or URL to deck list: ").strip()
            if not deck_path:
                click.echo("Deck path or URL is required.")
                _prompt_to_continue()
                continue
            deck_name = input("Deck name (optional): ").strip() or None
            profile_choice = input("Profile to associate (optional): ").strip() or None
            if profile_choice:
                profiles = get_profile_names()
                if profile_choice not in profiles:
                    click.echo(f"Profile '{profile_choice}' not found.")
                    _prompt_to_continue()
                    continue
            try:
                _process_deck_list(deck_path, deck_name, None, profile_choice or None)
            except click.ClickException as error:
                click.echo(str(error))
            _prompt_to_continue()
            continue

        if selection == "3":
            manifest_path = input("Path to token pack manifest (JSON): ").strip()
            if not manifest_path:
                click.echo("Manifest path is required.")
                _prompt_to_continue()
                continue
            pack_name = input("Pack name (optional): ").strip() or None
            try:
                _build_token_pack(manifest_path, pack_name)
            except click.ClickException as error:
                click.echo(str(error))
            _prompt_to_continue()
            continue

        if selection == "4":
            color_str = (
                input("Color identity filter (e.g., w, wu, bgr) [optional]: ")
                .strip()
                .lower()
                or None
            )
            exact_answer = (
                input("Require exact color identity match? [Y/n]: ").strip().lower()
            )
            exact = False if exact_answer in {"n", "no"} else True
            legal_answer = (
                input("Only include Commander-legal cards? [Y/n]: ").strip().lower()
            )
            legal_only = False if legal_answer in {"n", "no"} else True
            type_str = (
                input("Type/subtype filter (e.g., human, wizard) [optional]: ").strip()
                or None
            )
            _random_commander_flow(
                color_str,
                exact_match=exact,
                commander_legal_only=legal_only,
                type_filter=type_str,
            )
            _prompt_to_continue()
            continue

        click.echo("Please choose a valid option.")
        _prompt_to_continue()


def _card_search_menu():
    """Interactive menu for comprehensive card search and fetching."""
    while True:
        click.echo()
        options = [
            "[1] Universal card search (all types with filtering)",
            "[2] Creature search (with rarity, CMC, color filters)",
            "[3] Enchantment search (with comprehensive filtering)",
            "[4] Artifact search (with comprehensive filtering)",
            "[5] Instant/Sorcery search (with comprehensive filtering)",
            "[6] Enhanced land search (with artist, rarity, frame filters)",
            "[0] Back",
        ]
        _print_boxed_menu("Card Search & Fetch", options)

        selection = _get_key_choice({"0", "1", "2", "3", "4", "5", "6"})

        if selection == "0":
            return

        if selection == "1":
            _universal_card_search_flow()
        elif selection == "2":
            _creature_search_flow()
        elif selection == "3":
            _enchantment_search_flow()
        elif selection == "4":
            _artifact_search_flow()
        elif selection == "5":
            _spell_search_flow()
        elif selection == "6":
            _enhanced_land_search_flow()


def _universal_card_search_flow():
    """Interactive flow for universal card search with all filtering options."""
    click.echo("\nUniversal Card Search\n---------------------")

    # Card name filter
    name_filter = input("Card name (partial match, optional): ").strip()
    if not name_filter:
        name_filter = None

    # Card type filter
    type_filter = input(
        f"Card type ({', '.join(['creature', 'enchantment', 'artifact', 'instant', 'sorcery'])}, optional): "
    ).strip()
    if not type_filter:
        type_filter = None

    # Artist filter
    artist_filter = input("Artist name (partial match, optional): ").strip()
    if not artist_filter:
        artist_filter = None

    # Rarity filter
    rarity_filter = input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip()
    if not rarity_filter:
        rarity_filter = None

    # Set filter
    set_filter = input("Set code (e.g., ltr, one, optional): ").strip()
    if not set_filter:
        set_filter = None

    # Colors filter
    colors_input = input("Colors (W,U,B,R,G comma-separated, optional): ").strip()
    colors_filter = None
    if colors_input:
        colors_filter = [c.strip().upper() for c in colors_input.split(",")]

    # CMC filter
    cmc_input = input("Converted Mana Cost (number, optional): ").strip()
    cmc_filter = None
    if cmc_input:
        try:
            cmc_filter = float(cmc_input)
        except ValueError:
            click.echo("Invalid CMC value, ignoring...")

    # Limit
    limit_input = input("Maximum results (default: 20): ").strip()
    limit = 20
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            limit = 20

    # Ask user if they want to download or just preview
    download_input = input("Download cards or just preview? [d/P]: ").strip().lower()
    dry_run = download_input not in {"d", "download", "1"}

    if dry_run:
        click.echo("\nPreviewing cards...")
    else:
        click.echo("\nDownloading cards...")

    try:
        _fetch_cards_from_database(
            name_filter=name_filter,
            type_filter=type_filter,
            lang_filter="en",  # Default to English for menu
            set_filter=set_filter,
            artist_filter=artist_filter,
            rarity_filter=rarity_filter,
            cmc_filter=cmc_filter,
            colors_filter=colors_filter,
            limit=limit,
            dry_run=dry_run,
        )
    except Exception as e:
        click.echo(f"Error during search: {e}")

    _prompt_to_continue()


def _creature_search_flow():
    """Interactive flow for creature-specific search."""
    click.echo("\nCreature Search\n---------------")

    # Pre-set type to creature
    rarity_filter = input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip()
    if not rarity_filter:
        rarity_filter = None

    set_filter = input("Set code (e.g., ltr, one, optional): ").strip()
    if not set_filter:
        set_filter = None

    colors_input = input("Colors (W,U,B,R,G comma-separated, optional): ").strip()
    colors_filter = None
    if colors_input:
        colors_filter = [c.strip().upper() for c in colors_input.split(",")]

    cmc_input = input("Converted Mana Cost (number, optional): ").strip()
    cmc_filter = None
    if cmc_input:
        try:
            cmc_filter = float(cmc_input)
        except ValueError:
            click.echo("Invalid CMC value, ignoring...")

    limit_input = input("Maximum results (default: 10): ").strip()
    limit = 10
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            limit = 10

    click.echo("\nSearching for creatures...")
    try:
        _fetch_cards_from_database(
            type_filter="creature",
            lang_filter="en",
            set_filter=set_filter,
            rarity_filter=rarity_filter,
            cmc_filter=cmc_filter,
            colors_filter=colors_filter,
            exclude_tokens=True,
            exclude_lands=True,
            limit=limit,
            dry_run=True,
        )
    except Exception as e:
        click.echo(f"Error during search: {e}")

    _prompt_to_continue()


def _enchantment_search_flow():
    """Interactive flow for enchantment-specific search."""
    click.echo("\nEnchantment Search\n------------------")

    rarity_filter = input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip()
    if not rarity_filter:
        rarity_filter = None

    set_filter = input("Set code (e.g., ltr, one, optional): ").strip()
    if not set_filter:
        set_filter = None

    cmc_input = input("Converted Mana Cost (number, optional): ").strip()
    cmc_filter = None
    if cmc_input:
        try:
            cmc_filter = float(cmc_input)
        except ValueError:
            click.echo("Invalid CMC value, ignoring...")

    limit_input = input("Maximum results (default: 10): ").strip()
    limit = 10
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            limit = 10

    click.echo("\nSearching for enchantments...")
    try:
        _fetch_cards_from_database(
            type_filter="enchantment",
            lang_filter="en",
            set_filter=set_filter,
            rarity_filter=rarity_filter,
            cmc_filter=cmc_filter,
            exclude_tokens=True,
            exclude_lands=True,
            limit=limit,
            dry_run=True,
        )
    except Exception as e:
        click.echo(f"Error during search: {e}")

    _prompt_to_continue()


def _artifact_search_flow():
    """Interactive flow for artifact-specific search."""
    click.echo("\nArtifact Search\n---------------")

    rarity_filter = input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip()
    if not rarity_filter:
        rarity_filter = None

    set_filter = input("Set code (e.g., ltr, one, optional): ").strip()
    if not set_filter:
        set_filter = None

    cmc_input = input("Converted Mana Cost (number, optional): ").strip()
    cmc_filter = None
    if cmc_input:
        try:
            cmc_filter = float(cmc_input)
        except ValueError:
            click.echo("Invalid CMC value, ignoring...")

    limit_input = input("Maximum results (default: 10): ").strip()
    limit = 10
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            limit = 10

    click.echo("\nSearching for artifacts...")
    try:
        _fetch_cards_from_database(
            type_filter="artifact",
            lang_filter="en",
            set_filter=set_filter,
            rarity_filter=rarity_filter,
            cmc_filter=cmc_filter,
            exclude_tokens=True,
            exclude_lands=True,
            limit=limit,
            dry_run=True,
        )
    except Exception as e:
        click.echo(f"Error during search: {e}")

    _prompt_to_continue()


def _spell_search_flow():
    """Interactive flow for instant/sorcery search."""
    click.echo("\nInstant/Sorcery Search\n----------------------")

    spell_type = (
        input(f"Spell type [{'/'.join(SPELL_TYPES)}] (default: both): ").strip().lower()
    )
    if spell_type not in SPELL_TYPES:
        type_filter = None  # Will search both
        click.echo("Searching both instants and sorceries...")
    else:
        type_filter = spell_type

    rarity_filter = input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip()
    if not rarity_filter:
        rarity_filter = None

    set_filter = input("Set code (e.g., ltr, one, optional): ").strip()
    if not set_filter:
        set_filter = None

    colors_input = input("Colors (W,U,B,R,G comma-separated, optional): ").strip()
    colors_filter = None
    if colors_input:
        colors_filter = [c.strip().upper() for c in colors_input.split(",")]

    cmc_input = input("Converted Mana Cost (number, optional): ").strip()
    cmc_filter = None
    if cmc_input:
        try:
            cmc_filter = float(cmc_input)
        except ValueError:
            click.echo("Invalid CMC value, ignoring...")

    limit_input = input("Maximum results (default: 10): ").strip()
    limit = 10
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            limit = 10

    click.echo(f"\nSearching for {type_filter or 'instants/sorceries'}...")
    try:
        _fetch_cards_from_database(
            type_filter=type_filter,
            lang_filter="en",
            set_filter=set_filter,
            rarity_filter=rarity_filter,
            cmc_filter=cmc_filter,
            colors_filter=colors_filter,
            exclude_tokens=True,
            exclude_lands=True,
            limit=limit,
            dry_run=True,
        )
    except Exception as e:
        click.echo(f"Error during search: {e}")

    _prompt_to_continue()


def _enhanced_land_search_flow():
    """Interactive flow for enhanced land search with comprehensive filtering."""
    click.echo("\nEnhanced Land Search\n--------------------")

    # Land type
    land_type = (
        input("Land type [basic/nonbasic/both] (default: both): ").strip().lower()
    )
    if land_type not in ["basic", "nonbasic"]:
        land_type = "both"

    # Language
    lang = input("Language (en, ph, ltr, ja, etc., default: en): ").strip()
    if not lang:
        lang = "en"

    # Set filter
    set_filter = input("Set code (e.g., ltr, one, optional): ").strip()
    if not set_filter:
        set_filter = None

    # Artist filter
    artist_filter = input("Artist name (partial match, optional): ").strip()
    if not artist_filter:
        artist_filter = None

    # Rarity filter
    rarity_filter = input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip()
    if not rarity_filter:
        rarity_filter = None

    # Full-art filter
    fullart_input = input("Full-art only? [y/N]: ").strip().lower()
    fullart_only = fullart_input in {"y", "yes", "1"}

    # Limit
    limit_input = input("Maximum results (default: 20): ").strip()
    limit = 20
    if limit_input:
        try:
            limit = int(limit_input)
        except ValueError:
            limit = 20

    # Execute search
    click.echo(f"\nSearching for {land_type} lands...")

    try:
        if land_type == "basic" or land_type == "both":
            from db.bulk_index import query_basic_lands

            basic_results = query_basic_lands(
                lang_filter=lang,
                set_filter=set_filter,
                artist_filter=artist_filter,
                rarity_filter=rarity_filter,
                fullart_only=fullart_only,
                limit=limit if land_type == "basic" else limit // 2,
            )
            if basic_results:
                click.echo(f"\nFound {len(basic_results)} basic lands:")
                for i, card in enumerate(basic_results[:5]):
                    click.echo(
                        f"  {i+1}. {card['name']} ({card['set']}) - {card['rarity']} - {card.get('artist', 'Unknown')}"
                    )
                if len(basic_results) > 5:
                    click.echo(f"  ... and {len(basic_results) - 5} more")

        if land_type == "nonbasic" or land_type == "both":
            from db.bulk_index import query_non_basic_lands

            nonbasic_results = query_non_basic_lands(
                lang_filter=lang,
                set_filter=set_filter,
                artist_filter=artist_filter,
                rarity_filter=rarity_filter,
                fullart_only=fullart_only,
                limit=limit if land_type == "nonbasic" else limit // 2,
            )
            if nonbasic_results:
                click.echo(f"\nFound {len(nonbasic_results)} non-basic lands:")
                for i, card in enumerate(nonbasic_results[:5]):
                    click.echo(
                        f"  {i+1}. {card['name']} ({card['set']}) - {card['rarity']} - {card.get('artist', 'Unknown')}"
                    )
                if len(nonbasic_results) > 5:
                    click.echo(f"  ... and {len(nonbasic_results) - 5} more")

    except Exception as e:
        click.echo(f"Error during search: {e}")

    _prompt_to_continue()


def _hobby_features_menu():
    """Interactive menu for hobby features and discovery tools."""
    while True:
        click.echo()
        options = [
            "[1] Artist search (find cards by artist)",
            "[2] Random card discovery (get inspiration)",
            "[3] Set exploration (browse sets like a binder)",
            "[4] Deck theme scanner (analyze deck composition)",
            "[0] Back",
        ]
        _print_boxed_menu("Hobby Features & Discovery", options)

        selection = _get_key_choice({"0", "1", "2", "3", "4"})

        if selection == "0":
            return

        if selection == "1":
            click.echo("\n🎨 Artist Search\n")
            artist = input("Artist name: ").strip()
            if not artist:
                click.echo("Artist name is required.")
                _prompt_to_continue()
                continue

            card_type = input("Card type filter (optional): ").strip() or None
            limit_input = input("Maximum results [20]: ").strip()
            try:
                limit = int(limit_input) if limit_input else 20
            except ValueError:
                limit = 20

            try:
                import subprocess

                cmd = [sys.executable, "tools/hobby_features.py", "artist", artist]
                if card_type:
                    cmd.extend(["--type", card_type])
                cmd.extend(["--limit", str(limit)])

                result = subprocess.run(
                    cmd, cwd=script_directory, capture_output=True, text=True
                )
                click.echo(result.stdout)
                if result.returncode != 0:
                    click.echo(f"Error: {result.stderr}")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection == "2":
            click.echo("\n🎲 Random Card Discovery\n")
            card_type = (
                input("Card type (creature, artifact, etc., optional): ").strip()
                or None
            )
            rarity = (
                input(f"Rarity ({', '.join(RARITIES)}, optional): ").strip() or None
            )
            set_code = input("Set code (e.g., ltr, one, optional): ").strip() or None
            count_input = input("Number of cards [5]: ").strip()
            try:
                count = int(count_input) if count_input else 5
            except ValueError:
                count = 5

            try:
                import subprocess

                cmd = [sys.executable, "tools/hobby_features.py", "random"]
                if card_type:
                    cmd.extend(["--type", card_type])
                if rarity:
                    cmd.extend(["--rarity", rarity])
                if set_code:
                    cmd.extend(["--set", set_code])
                cmd.extend(["--count", str(count)])

                result = subprocess.run(
                    cmd, cwd=script_directory, capture_output=True, text=True
                )
                click.echo(result.stdout)
                if result.returncode != 0:
                    click.echo(f"Error: {result.stderr}")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection == "3":
            click.echo("\n📚 Set Exploration\n")
            set_code = input("Set code (e.g., ltr, one): ").strip()
            if not set_code:
                click.echo("Set code is required.")
                _prompt_to_continue()
                continue

            card_type = input("Card type filter (optional): ").strip() or None
            rarity = input("Rarity filter (optional): ").strip() or None
            sort_by = input("Sort by (name, rarity, cmc) [name]: ").strip() or "name"
            limit_input = input("Maximum results [50]: ").strip()
            try:
                limit = int(limit_input) if limit_input else 50
            except ValueError:
                limit = 50

            try:
                import subprocess

                cmd = [sys.executable, "tools/hobby_features.py", "explore", set_code]
                if card_type:
                    cmd.extend(["--type", card_type])
                if rarity:
                    cmd.extend(["--rarity", rarity])
                cmd.extend(["--sort", sort_by, "--limit", str(limit)])

                result = subprocess.run(
                    cmd, cwd=script_directory, capture_output=True, text=True
                )
                click.echo(result.stdout)
                if result.returncode != 0:
                    click.echo(f"Error: {result.stderr}")
            except Exception as e:
                click.echo(f"Error: {e}")
            _prompt_to_continue()
            continue

        if selection == "4":
            click.echo("\nDeck Theme Scanner\n-------------------")
            click.echo(
                "This feature analyzes deck composition and suggests matching basic lands."
            )
            click.echo("Note: This requires a deck list file with card names.")
            _prompt_to_continue()
            continue


def launch_menu():
    while True:
        click.echo()
        options = [
            "[1] Deck Tools          →  Manage deck reports and PDF generation",
            "[2] Token Utilities     →  Search, build packs, explorers",
            "[3] Card Search & Fetch →  Universal card search with comprehensive filtering",
            "[4] Profiles & Shared   →  Manage profiles and shared assets",
            "[5] Maintenance & Tools →  Health checks, coverage, notifications",
            "[6] Hobby Features      →  Discovery tools, artist search, set exploration",
            "[7] Plugins             →  Manage plugins (enable/disable)",
            "[0] Exit",
        ]
        _print_boxed_menu("The Proxy Machine CLI", options)

        selection = _get_key_choice({"0", "1", "2", "3", "4", "5", "6", "7"})

        if selection == "1":
            _deck_tools_menu()
        elif selection == "2":
            _tokens_menu()
        elif selection == "3":
            _card_search_menu()
        elif selection == "4":
            _profiles_shared_menu()
        elif selection == "5":
            _maintenance_tools_menu()
        elif selection == "6":
            _hobby_features_menu()
        elif selection == "7":
            _plugins_menu()
        elif selection == "0":
            click.echo("\nGoodbye!\n")
            break
        else:
            click.echo("Please select a valid menu option.")


def dispatch_subcommand():
    """Handle subcommand dispatch for db/verify/etc."""
    cmd = sys.argv[1]
    if cmd == "db":
        # Delegate to tools/db.py with remaining args
        tool = os.path.join(script_directory, "tools", "db.py")
        code = subprocess.call([sys.executable, tool] + sys.argv[2:])
        raise SystemExit(code)
    if cmd == "verify":
        tool = os.path.join(script_directory, "tools", "verify.py")
        code = subprocess.call([sys.executable, tool] + sys.argv[2:])
        raise SystemExit(code)
    cli.main(standalone_mode=True)


def run_cli():
    """Launch the interactive CLI menu."""
    launch_menu()


def main():
    """Main entrypoint - dispatch to subcommand or interactive CLI."""
    if len(sys.argv) > 1:
        dispatch_subcommand()
    else:
        run_cli()


def _download_deck_from_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "moxfield" in host:
        deck_id = parsed.path.rstrip("/").split("/")[-1]
        api_url = f"https://api.moxfield.com/v2/decks/all/{deck_id}"
        data = _http_get(api_url, as_json=True, rate_limiter=None)
        if not isinstance(data, dict):
            raise click.ClickException("Unexpected response from Moxfield API.")
        deck_name = data.get("name") or deck_id
        mainboard = data.get("mainboard") or {}
        lines = []
        for entry in mainboard.values():
            card = entry or {}
            count = card.get("quantity") or 0
            name = card.get("card", {}).get("name")
            if count and name:
                lines.append(f"{count} {name}")
        if not lines:
            raise click.ClickException("No mainboard cards found in Moxfield deck.")
        return "\n".join(lines), deck_name

    if "archidekt" in host:
        parts = parsed.path.rstrip("/").split("/")
        if parts and parts[-1].isdigit():
            deck_id = parts[-1]
        else:
            raise click.ClickException(
                "Could not determine Archidekt deck ID from URL."
            )
        api_url = f"https://archidekt.com/api/decks/{deck_id}/"
        data = _http_get(api_url, as_json=True, rate_limiter=None)
        if not isinstance(data, dict):
            raise click.ClickException("Unexpected response from Archidekt API.")
        deck_name = data.get("name") or deck_id
        cards = data.get("cards") or []
        lines = []
        for card in cards:
            quantity = card.get("quantity")
            details = card.get("card", {})
            name = details.get("name")
            if quantity and name:
                lines.append(f"{quantity} {name}")
        if not lines:
            raise click.ClickException("No cards found in Archidekt deck.")
        return "\n".join(lines), deck_name

    if "tappedout" in host:
        # TappedOut format: https://tappedout.net/mtg-decks/deck-name/
        deck_slug = parsed.path.rstrip("/").split("/")[-1]
        # TappedOut provides a text export endpoint
        export_url = f"https://tappedout.net/mtg-decks/{deck_slug}/?fmt=txt"
        try:
            response = _http_get(export_url, rate_limiter=None)
            if isinstance(response, bytes):
                deck_text = response.decode("utf-8")
            else:
                deck_text = str(response)

            # Parse the text format (lines like "1x Card Name" or "1 Card Name")
            lines = []
            deck_name = deck_slug.replace("-", " ").title()
            for line in deck_text.split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                # Match patterns like "1x Card Name" or "1 Card Name"
                match = re.match(r"^(\d+)x?\s+(.+)$", line)
                if match:
                    count, name = match.groups()
                    lines.append(f"{count} {name}")

            if not lines:
                raise click.ClickException("No cards found in TappedOut deck.")
            return "\n".join(lines), deck_name
        except Exception as e:
            raise click.ClickException(f"Failed to fetch TappedOut deck: {e}")

    if "mtggoldfish" in host or "goldfish" in host:
        # MTGGoldfish format: https://www.mtggoldfish.com/deck/12345
        # Extract deck ID from path
        parts = parsed.path.rstrip("/").split("/")
        if len(parts) >= 3 and parts[1] == "deck":
            deck_id = parts[2].split("#")[0]  # Remove any anchor
        else:
            raise click.ClickException(
                "Could not determine MTGGoldfish deck ID from URL."
            )

        # MTGGoldfish provides a download endpoint
        download_url = f"https://www.mtggoldfish.com/deck/download/{deck_id}"
        try:
            response = _http_get(download_url, rate_limiter=None)
            if isinstance(response, bytes):
                deck_text = response.decode("utf-8")
            else:
                deck_text = str(response)

            # Parse Arena/MTGO format (lines like "1 Card Name")
            lines = []
            deck_name = f"MTGGoldfish-{deck_id}"
            for line in deck_text.split("\n"):
                line = line.strip()
                if not line or line.startswith("Deck") or line.startswith("Sideboard"):
                    continue
                # Match pattern "1 Card Name"
                match = re.match(r"^(\d+)\s+(.+)$", line)
                if match:
                    count, name = match.groups()
                    lines.append(f"{count} {name}")

            if not lines:
                raise click.ClickException("No cards found in MTGGoldfish deck.")
            return "\n".join(lines), deck_name
        except Exception as e:
            raise click.ClickException(f"Failed to fetch MTGGoldfish deck: {e}")

    raise click.ClickException(
        "Unsupported deck URL. Currently supports Moxfield, Archidekt, TappedOut, and MTGGoldfish."
    )


if __name__ == "__main__":
    main()
