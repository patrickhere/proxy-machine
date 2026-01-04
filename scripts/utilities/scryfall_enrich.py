#!/usr/bin/env python3
"""
Scryfall Enrichers: lightweight helpers to fetch set information and rulings.

Caching:
- Set info is cached under bulk-data/sets/<code>.json (30 days TTL by default)
- Rulings are cached under bulk-data/rulings/oracle/<oracle_id>.json (7 days TTL by default)
- Oracle->print id resolution is cached under bulk-data/oracle_map/<oracle_id>.txt (7 days TTL)

Network resilience:
- HTTP GETs include retries with exponential backoff and jitter, handling transient TLS/timeout/5xx/429 errors.

These helpers intentionally use the requests library and standard sqlite3.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import requests as _requests
else:  # pragma: no cover - runtime alias only
    _requests = None  # type: ignore[assignment]

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Import bulk_paths helpers for centralized path resolution
import sys

sys.path.insert(0, SCRIPT_DIR)
from bulk_paths import get_bulk_data_directory

BULK_DIR = str(get_bulk_data_directory())
SETS_CACHE_DIR = os.path.join(BULK_DIR, "sets")
RULINGS_CACHE_DIR = os.path.join(BULK_DIR, "rulings", "oracle")
ORACLE_MAP_DIR = os.path.join(BULK_DIR, "oracle_map")

API_ROOT = "https://api.scryfall.com"
USER_AGENT = "ProxyMachine/1.0 (patrick)"
DEFAULT_TIMEOUT = float(os.environ.get("PM_HTTP_TIMEOUT", "15"))
MAX_RETRIES = int(os.environ.get("PM_HTTP_RETRIES", "4"))
BACKOFF_BASE = float(os.environ.get("PM_HTTP_BACKOFF_BASE", "0.5"))


# DB path (imported lazily to avoid hard dependency)
try:
    from db.bulk_index import DB_PATH as BULK_DB_PATH
except Exception:
    from bulk_paths import bulk_db_path, legacy_bulk_locations

    BULK_DB_PATH = str(bulk_db_path())
    if not os.path.exists(BULK_DB_PATH):
        # Check legacy locations
        for legacy_dir in legacy_bulk_locations():
            legacy_db = legacy_dir / "bulk.db"
            if legacy_db.exists():
                BULK_DB_PATH = str(legacy_db)
                break


def _http_get_json(url: str, *, timeout: float | None = None) -> dict:
    """GET JSON with retries and exponential backoff.

    Retries on: timeouts, connection errors, 5xx, and 429.
    """
    import random

    # Offline mode: skip network
    if os.environ.get("PM_OFFLINE", "0").strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("offline mode: network disabled")
    t = float(timeout or DEFAULT_TIMEOUT)
    if requests is None:
        raise RuntimeError("requests library is required for Scryfall enrichment")
    req = requests
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = req.get(url, headers={"User-Agent": USER_AGENT}, timeout=t)
            # Retry on 5xx/429
            if resp.status_code in {429, 500, 502, 503, 504}:
                raise req.HTTPError(f"{resp.status_code} from {url}")
            resp.raise_for_status()
            return resp.json()
        except (req.Timeout, req.ConnectionError, req.HTTPError) as e:
            last_exc = e
            if attempt >= MAX_RETRIES:
                break
            # Backoff with jitter
            sleep_s = BACKOFF_BASE * (2**attempt) + random.random() * 0.25
            time.sleep(sleep_s)
        except Exception as e:  # non-retryable
            last_exc = e
            break
    if last_exc:
        raise last_exc
    # should not reach
    raise RuntimeError("_http_get_json failed without exception")


def _safe_write_json(path: str, data: Any) -> None:
    try:
        tmp = path + ".part"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        pass


def get_set_info(set_code: str, *, ttl_seconds: int = 30 * 24 * 3600) -> dict:
    os.makedirs(SETS_CACHE_DIR, exist_ok=True)
    code = (set_code or "").strip().lower()
    cache_path = os.path.join(SETS_CACHE_DIR, f"{code}.json")
    try:
        if ttl_seconds > 0 and os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age <= ttl_seconds:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
    except Exception:
        pass

    try:
        data = _http_get_json(f"{API_ROOT}/sets/{code}")
        _safe_write_json(cache_path, data)
        return data
    except Exception:
        # Network error: fall back to stale cache if present
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        # Surface an empty object on failure to avoid crashing UI
        return {"code": code, "error": "set_info_fetch_failed"}


def _resolve_print_id_by_oracle(
    oracle_id: str, *, ttl_seconds: int = 7 * 24 * 3600
) -> Optional[str]:
    # Prefer local DB when available
    try:
        if os.path.exists(BULK_DB_PATH):  # type: ignore[arg-type]
            conn = sqlite3.connect(BULK_DB_PATH)  # type: ignore[arg-type]
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM prints WHERE oracle_id=? LIMIT 1", (oracle_id,)
                )
                row = cur.fetchone()
                if row and row[0]:
                    return str(row[0])
            finally:
                conn.close()
    except Exception:
        pass

    # Cache-backed fallback: Scryfall search
    os.makedirs(ORACLE_MAP_DIR, exist_ok=True)
    fmap = os.path.join(ORACLE_MAP_DIR, f"{oracle_id}.txt")
    try:
        if ttl_seconds > 0 and os.path.exists(fmap):
            age = time.time() - os.path.getmtime(fmap)
            if age <= ttl_seconds:
                with open(fmap, "r", encoding="utf-8") as fh:
                    cid = fh.read().strip()
                    if cid:
                        return cid
    except Exception:
        pass

    try:
        q = f"oracleid:{oracle_id}"
        data = _http_get_json(f"{API_ROOT}/cards/search?q={q}")
        cards = data.get("data") or []
        if cards:
            cid = cards[0].get("id")
            if cid:
                cid_s = str(cid)
                try:
                    os.makedirs(ORACLE_MAP_DIR, exist_ok=True)
                    with open(fmap, "w", encoding="utf-8") as fh:
                        fh.write(cid_s + "\n")
                except Exception:
                    pass
                return cid_s
    except Exception:
        pass
    return None


def get_rulings_for_oracle(
    oracle_id: str, *, ttl_seconds: int = 7 * 24 * 3600
) -> List[Dict[str, Any]]:
    oid = (oracle_id or "").strip()
    if not oid:
        return []
    # Check cache first
    os.makedirs(RULINGS_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(RULINGS_CACHE_DIR, f"{oid}.json")
    try:
        if ttl_seconds > 0 and os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age <= ttl_seconds:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        rulings = data.get("data") or []
                    else:
                        # Backward-compat: previously might have stored list
                        rulings = data or []
                    return [
                        {
                            "published_at": r.get("published_at"),
                            "comment": r.get("comment"),
                            "source": r.get("source"),
                        }
                        for r in rulings
                    ]
    except Exception:
        pass

    # Resolve and fetch
    cid = _resolve_print_id_by_oracle(oid)
    if not cid:
        # Fall back to stale cache if present
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        rulings = data.get("data") or []
                    else:
                        rulings = data or []
                    return [
                        {
                            "published_at": r.get("published_at"),
                            "comment": r.get("comment"),
                            "source": r.get("source"),
                        }
                        for r in rulings
                    ]
        except Exception:
            pass
        return []
    try:
        data = _http_get_json(f"{API_ROOT}/cards/{cid}/rulings")
        # Write cached raw payload to preserve original fields
        _safe_write_json(cache_path, data)
        rulings = data.get("data") or []
        return [
            {
                "published_at": r.get("published_at"),
                "comment": r.get("comment"),
                "source": r.get("source"),
            }
            for r in rulings
        ]
    except Exception:
        # On network errors, prefer stale cache
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        rulings = data.get("data") or []
                    else:
                        rulings = data or []
                    return [
                        {
                            "published_at": r.get("published_at"),
                            "comment": r.get("comment"),
                            "source": r.get("source"),
                        }
                        for r in rulings
                    ]
        except Exception:
            pass
        return []
