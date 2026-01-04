#!/usr/bin/env python3
"""
Cards Search CLI

Search cards by oracle text/type/name using the local SQLite bulk index when
available, with a fallback to LIKE search. Outputs a concise text table or JSON.

Examples:
  uv run python tools/cards.py --query "destroy all creatures" --set mh3 --include-tokens --limit 10
  uv run python tools/cards.py --query "spirit" --type-contains land --limit 50 --json
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

try:
    from db.bulk_index import (
        DB_PATH as BULK_DB_PATH,
        query_oracle_fts,
        query_oracle_text,
    )
except Exception:
    BULK_DB_PATH = None  # type: ignore

    def query_oracle_fts(*args, **kwargs):  # type: ignore
        return []

    def query_oracle_text(*args, **kwargs):  # type: ignore
        return []


def _print_table(rows: List[dict]) -> None:
    cols = [
        ("name", 34),
        ("set", 5),
        ("collector_number", 6),
        ("type_line", 26),
        ("is_token", 5),
    ]
    header = " ".join([f"{k.upper():<{w}}" for k, w in cols])
    print(header)
    print("-" * len(header))
    for r in rows:
        line = []
        for k, w in cols:
            val: Any = r.get(k)
            if k == "is_token":
                val = "yes" if r.get("is_token") else "no"
            s = str(val or "")
            if len(s) > w:
                s = s[: max(0, w - 1)] + "…"
            line.append(f"{s:<{w}}")
        print(" ".join(line))


def _normalize_colors(val: str | None) -> List[str]:
    if not val:
        return []
    s = val.replace(",", "").strip().lower()
    keep = []
    for ch in s:
        if ch in {"w", "u", "b", "r", "g"} and ch not in keep:
            keep.append(ch)
    return keep


def _row_colors(row: dict) -> List[str]:
    ci = row.get("color_identity")
    if isinstance(ci, list):
        vals = [str(x).lower() for x in ci]
        # Normalize 'u' for blue if someone stored 'U'
        return ["u" if x == "u" else x for x in vals]
    if isinstance(ci, str):
        return _normalize_colors(ci)
    return []


def _contains(hay: Any, needle: str | None) -> bool:
    if not needle:
        return True
    text = str(hay or "").lower()
    return needle.lower() in text


def _apply_filters(
    rows: List[dict],
    *,
    name_contains: str | None,
    oracle_contains: str | None,
    type_contains: str | None,
    colors: List[str],
) -> List[dict]:
    out: List[dict] = []
    for r in rows:
        if not _contains(r.get("name"), name_contains):
            continue
        if not _contains(r.get("oracle_text"), oracle_contains):
            continue
        if not _contains(r.get("type_line"), type_contains):
            continue
        if colors:
            rc = _row_colors(r)
            ok = all(c in rc for c in colors)
            if not ok:
                continue
        out.append(r)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Cards search CLI")
    parser.add_argument(
        "--query", required=True, help="Search string (name/oracle/type)"
    )
    parser.add_argument(
        "--set", dest="set_code", help="Restrict to set code (e.g., mh3)"
    )
    parser.add_argument(
        "--include-tokens", action="store_true", help="Include token entries"
    )
    parser.add_argument(
        "--limit", type=int, default=25, help="Max rows to show (0 = all)"
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
    parser.add_argument(
        "--name-contains", dest="name_contains", help="Substring filter against name"
    )
    parser.add_argument(
        "--oracle-contains",
        dest="oracle_contains",
        help="Substring filter against oracle text",
    )
    parser.add_argument(
        "--type-contains",
        dest="type_contains",
        help="Substring filter against type line",
    )
    parser.add_argument(
        "--colors", help="Require these color identity letters (e.g., wub, or w,u)"
    )
    args = parser.parse_args()

    # PM_LOG support
    pm_log = (os.environ.get("PM_LOG") or "").strip().lower()
    if pm_log == "json":
        args.json = True if not args.json else True

    set_filter = args.set_code or None
    include_tokens = bool(args.include_tokens)
    limit = None if args.limit == 0 else args.limit

    rows = query_oracle_fts(
        query=args.query,
        set_filter=set_filter,
        include_tokens=include_tokens,
        limit=limit,
    )
    if not rows:
        rows = query_oracle_text(
            query=args.query,
            set_filter=set_filter,
            include_tokens=include_tokens,
            limit=limit,
        )

    # Client-side filters
    filtered = _apply_filters(
        rows,
        name_contains=(args.name_contains or None),
        oracle_contains=(args.oracle_contains or None),
        type_contains=(args.type_contains or None),
        colors=_normalize_colors(args.colors),
    )

    if args.json:
        print(json.dumps({"count": len(filtered), "items": filtered}, indent=2))
    else:
        if not args.quiet:
            print(f"Rows: {len(filtered)}\n")
        _print_table(filtered)


if __name__ == "__main__":
    main()
