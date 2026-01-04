#!/usr/bin/env python3
"""
Workspace verification CLI

Performs a series of health checks and reports results. Exits non-zero if any
checks fail. Supports JSON output for automation.

Examples:
  uv run python tools/verify.py
  uv run python tools/verify.py --json --min-disk-gb 2
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Repo root is two levels above tools/: <repo>/<proxy-machine>/tools → <repo>/
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SHARED_ROOT = os.path.join(PROJECT_ROOT, "magic-the-gathering", "shared")
ARCHIVED_ROOT = os.path.join(PROJECT_ROOT, "archived")

# Import bulk_paths helpers
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from bulk_paths import bulk_db_path, get_bulk_data_directory, legacy_bulk_locations

BULK_ROOT = str(get_bulk_data_directory())


def _resolve_bulk_db_path() -> str:
    db_path = bulk_db_path()
    if db_path.exists():
        return str(db_path)
    # Check legacy locations
    for legacy_dir in legacy_bulk_locations():
        legacy_db = legacy_dir / "bulk.db"
        if legacy_db.exists():
            return str(legacy_db)
    return str(db_path)


# DB path (consistent with db/bulk_index.py) with backward-compatible fallback
BULK_DB_PATH = _resolve_bulk_db_path()


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: Dict[str, Any]


def _check_paths() -> CheckResult:
    required_dirs = [
        SHARED_ROOT,
        BULK_ROOT,
        os.path.join(SHARED_ROOT, "tokens"),
        os.path.join(SHARED_ROOT, "basic-lands"),
        os.path.join(SHARED_ROOT, "non-basic-lands"),
        os.path.join(ARCHIVED_ROOT),
    ]
    missing = [p for p in required_dirs if not os.path.exists(p)]
    # Permit legacy bulk-data directories during transition
    for legacy_dir in legacy_bulk_locations():
        legacy_path = str(legacy_dir)
        if os.path.exists(legacy_path) and legacy_path in missing:
            missing.remove(legacy_path)
    return CheckResult(
        name="paths",
        ok=len(missing) == 0,
        details={"missing": missing, "checked": required_dirs},
    )


def _check_disk(min_gb: float) -> CheckResult:
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    free_gb = free / (1024**3)
    return CheckResult(
        name="disk",
        ok=free_gb >= min_gb,
        details={"free_gb": round(free_gb, 2), "min_gb": min_gb},
    )


def _check_db() -> CheckResult:
    info: Dict[str, Any] = {
        "path": BULK_DB_PATH,
        "exists": os.path.exists(BULK_DB_PATH),
    }
    ok = False
    conn: sqlite3.Connection | None = None
    if os.path.exists(BULK_DB_PATH):
        try:
            conn = sqlite3.connect(BULK_DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM prints;")
            prints = int(cur.fetchone()[0])
            info["prints"] = prints
            try:
                cur.execute("SELECT COUNT(*) FROM unique_artworks;")
                info["unique_artworks"] = int(cur.fetchone()[0])
            except sqlite3.DatabaseError:
                info["unique_artworks"] = 0
            cur.execute("SELECT value FROM metadata WHERE key='schema_version';")
            row = cur.fetchone()
            info["schema_version"] = int(row[0]) if row and row[0] else None
            cur.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='prints_fts';"
            )
            info["fts5"] = bool(cur.fetchone()[0])
            ok = prints > 0 and bool(info["schema_version"]) is not None
        except Exception as e:
            info["error"] = str(e)
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
    return CheckResult(name="db", ok=ok, details=info)


def main() -> None:
    parser = argparse.ArgumentParser(description="Workspace verification CLI")
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text table"
    )
    parser.add_argument(
        "--min-disk-gb",
        type=float,
        default=1.0,
        help="Minimum free disk space required (GB)",
    )
    args = parser.parse_args()

    checks: List[CheckResult] = []
    checks.append(_check_paths())
    checks.append(_check_disk(args.min_disk_gb))
    checks.append(_check_db())

    all_ok = all(c.ok for c in checks)

    if args.json:
        payload = {"ok": all_ok, "checks": [asdict(c) for c in checks]}
        print(json.dumps(payload, indent=2))
    else:
        print("Workspace Verification\n----------------------")
        for c in checks:
            status = "OK" if c.ok else "FAIL"
            print(f"- {c.name}: {status}")
        if not all_ok:
            print("\nDetails:")
            for c in checks:
                if not c.ok:
                    print(f"* {c.name}: {json.dumps(c.details, indent=2)}")
    raise SystemExit(0 if all_ok else 3)


if __name__ == "__main__":
    main()
