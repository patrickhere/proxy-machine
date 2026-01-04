#!/usr/bin/env python3
"""
DB CLI wrapper

Convenience wrapper around db/bulk_index.py and bulk JSON fetchers.

Examples:
  uv run python tools/db.py build
  uv run python tools/db.py info --json
  uv run python tools/db.py refresh --allow-download
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DB_TOOL = os.path.join(PROJECT_ROOT, "proxy-machine", "db", "bulk_index.py")
FETCH_TOOL = os.path.join(PROJECT_ROOT, "proxy-machine", "tools", "fetch_bulk.py")


def _run_py(args: list[str]) -> int:
    cmd = [sys.executable] + args
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 130


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk DB convenience CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("build", help="Build or rebuild the bulk.db from JSON dumps")
    sub.add_parser("rebuild", help="Force rebuild the bulk.db")
    sub.add_parser("vacuum", help="VACUUM/ANALYZE the database")
    p_info = sub.add_parser("info", help="Show DB info")
    p_info.add_argument("--json", action="store_true", help="Emit JSON if available")

    p_refresh = sub.add_parser("refresh", help="Fetch bulks, rebuild DB, and VACUUM")
    p_refresh.add_argument(
        "--allow-download",
        action="store_true",
        help="Permit network downloads (respects PM_OFFLINE if not set)",
    )

    sub.add_parser("verify", help="Verify DB health and exit non-zero on failure")

    args = parser.parse_args()

    if args.cmd in {"build", "rebuild", "vacuum"}:
        code = _run_py([DB_TOOL, args.cmd])
        raise SystemExit(code)

    if args.cmd == "info":
        # Show info by invoking the tool
        code = _run_py([DB_TOOL, "info"])
        raise SystemExit(code)

    if args.cmd == "refresh":
        orig_offline = os.environ.get("PM_OFFLINE")
        try:
            if not args.allow_download:
                os.environ["PM_OFFLINE"] = "1"
            # Fetch bulks
            for bid in ("default-cards", "oracle-cards", "unique-artwork"):
                code = _run_py([FETCH_TOOL, "--id", bid])
                if code not in (0, None):
                    raise SystemExit(code)
            # Rebuild and vacuum
            for step in ("rebuild", "vacuum"):
                code = _run_py([DB_TOOL, step])
                if code not in (0, None):
                    raise SystemExit(code)
        finally:
            if orig_offline is None:
                os.environ.pop("PM_OFFLINE", None)
            else:
                os.environ["PM_OFFLINE"] = orig_offline
        print("DB refresh complete.")
        return

    if args.cmd == "verify":
        code = _run_py([DB_TOOL, "verify"])
        raise SystemExit(code)

    parser.print_help()


if __name__ == "__main__":
    main()
