#!/usr/bin/env python3
"""
Unique Artworks CLI

Query unique artworks from the local SQLite bulk index with rich filters, or
show aggregate counts per oracle (optionally within a set).

Examples:
  uv run python tools/ua.py --name "Lightning Bolt" --limit 25
  uv run python tools/ua.py --name "Lightning Bolt" --set me4 --counts
  uv run python tools/ua.py --oracle-id <uuid> --artist "John Avon" --full-art 1

Exit codes:
  0 on success, 2 if DB is missing, 1 on other errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List

# Ensure parent directory (proxy-machine/) is on sys.path so 'db' can be imported
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# Local db helpers
try:
    from db.bulk_index import (
        DB_PATH as BULK_DB_PATH,
        query_unique_artworks,
        count_unique_artworks,
    )
except Exception:
    BULK_DB_PATH = None  # type: ignore

    def query_unique_artworks(*args, **kwargs):  # type: ignore
        return []

    def count_unique_artworks(*args, **kwargs) -> int:  # type: ignore
        return 0


def _print_table(rows: List[dict]) -> None:
    cols = [
        ("name", 28),
        ("set", 5),
        ("collector_number", 6),
        ("artist", 22),
        ("illustration_id", 36),
        ("full_art", 8),
    ]
    header = " ".join([f"{k.upper():<{w}}" for k, w in cols])
    print(header)
    print("-" * len(header))
    for r in rows:
        line = []
        for k, w in cols:
            val: Any = r.get(k)
            if k == "full_art":
                val = "yes" if r.get("full_art") else "no"
            s = str(val or "")
            if len(s) > w:
                s = s[: max(0, w - 1)] + "…"
            line.append(f"{s:<{w}}")
        print(" ".join(line))


def main() -> None:
    parser = argparse.ArgumentParser(description="Unique artworks query CLI")
    parser.add_argument("--name", help="Card name to resolve oracle_id from bulk index")
    parser.add_argument("--oracle-id", help="Direct oracle_id to query")
    parser.add_argument("--illustration-id", help="Filter by illustration_id")
    parser.add_argument("--set", dest="set_code", help="Restrict to a set (e.g., mh3)")
    parser.add_argument(
        "--name-contains", dest="name_contains", help="Substring filter on name"
    )
    parser.add_argument("--artist", help="Substring filter on artist")
    parser.add_argument("--frame", help="Exact frame code (e.g., 2003, 2015)")
    parser.add_argument("--effect", help="Frame effect substring (e.g., showcase)")
    parser.add_argument(
        "--full-art", type=int, choices=[0, 1], help="Full-art filter (1/0)"
    )
    parser.add_argument(
        "--limit", type=int, default=25, help="Max rows to show (0 = all)"
    )
    parser.add_argument(
        "--counts", action="store_true", help="Show aggregate counts instead of rows"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text table"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Reduce non-essential output"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Increase logging detail"
    )
    args = parser.parse_args()

    pm_log = (os.environ.get("PM_LOG") or "").strip().lower()
    if pm_log == "json":
        args.json = True if not args.json else True

    if not BULK_DB_PATH or not os.path.exists(BULK_DB_PATH):
        print(
            "bulk.db is missing. Build it first (make bulk-index-build).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    full_art = None
    if args.full_art is not None:
        full_art = True if args.full_art == 1 else False

    try:
        if args.counts:
            # Determine oracle ids to count
            oracle_ids: List[str] = []
            if args.oracle_id:
                oracle_ids = [args.oracle_id]
            elif args.name:
                # Fallback: use name_contains search
                rows = query_unique_artworks(
                    oracle_id=None,
                    illustration_id=args.illustration_id,
                    set_filter=(args.set_code or None),
                    limit=None,
                    name_filter=(args.name_contains or args.name),
                    artist_filter=args.artist,
                    frame_filter=args.frame,
                    frame_effect_contains=args.effect,
                    full_art=full_art,
                )
                ids = {r.get("oracle_id") for r in rows if r.get("oracle_id")}
                oracle_ids = sorted(ids)[:50]  # cap to avoid surprises
            totals_all = 0
            totals_in_set = 0
            per: List[dict] = []
            for oid in oracle_ids:
                c_all = count_unique_artworks(oracle_id=oid)
                c_set = (
                    count_unique_artworks(
                        oracle_id=oid, set_filter=(args.set_code or None)
                    )
                    if args.set_code
                    else None
                )
                per.append(
                    {
                        "oracle_id": oid,
                        "all": int(c_all),
                        "in_set": int(c_set) if c_set is not None else None,
                    }
                )
                totals_all += int(c_all)
                if isinstance(c_set, int):
                    totals_in_set += c_set
            payload = {
                "oracle_ids": oracle_ids,
                "set_filter": (args.set_code or None),
                "totals": {
                    "all": totals_all,
                    "in_set": (totals_in_set if args.set_code else None),
                },
                "per_oracle": per,
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                if not args.quiet:
                    print(
                        f"oracle_ids: {', '.join(oracle_ids) or '—'} | set={args.set_code or '—'}"
                    )
                for row in per:
                    print(
                        f"- {row['oracle_id']}: all={row['all']} in_set={row['in_set'] if row['in_set'] is not None else '—'}"
                    )
                if args.set_code and not args.quiet:
                    print(f"Totals: all={totals_all} in_set={totals_in_set}")
            return

        rows = query_unique_artworks(
            oracle_id=(args.oracle_id or None),
            illustration_id=(args.illustration_id or None),
            set_filter=(args.set_code or None),
            limit=(None if args.limit == 0 else args.limit),
            name_filter=(args.name_contains or args.name),
            artist_filter=args.artist,
            frame_filter=args.frame,
            frame_effect_contains=args.effect,
            full_art=full_art,
        )
        if args.json:
            print(json.dumps({"count": len(rows), "items": rows}, indent=2))
        else:
            if not args.quiet:
                print(f"Rows: {len(rows)}\n")
            _print_table(rows)
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
