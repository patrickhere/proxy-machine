#!/usr/bin/env python3
"""
Coverage Report tool (lands and tokens).

Computes coverage for:
- Basic/non-basic/all lands using the cached Scryfall bulk index from create_pdf.py
- Tokens from the cached token index
and reports which prints have local art in the shared libraries.

Outputs CSV/JSON under:
  magic-the-gathering/shared/reports/land-coverage/<timestamp>/  (lands)
  magic-the-gathering/shared/reports/token-coverage/<timestamp>/ (tokens)

Artifacts:
- land_coverage.csv / token_coverage.csv (row-level details)
- per_set_summary.csv (per-set totals, covered, missing, coverage pct)
- missing_only.csv (only missing entries)
- *_summary.json (full JSON payload)

Usage:
  uv run python coverage.py --type nonbasic [--set KHM]
  uv run python coverage.py --type basic
  uv run python coverage.py --type all
  uv run python coverage.py --type tokens [--set MH3]

"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Reuse logic and paths from create_pdf
import create_pdf

try:
    # Optional import; coverage will work without UA counts if unavailable
    from db.bulk_index import count_unique_artworks as db_count_unique_artworks
except Exception:

    def db_count_unique_artworks(*args, **kwargs) -> int:  # type: ignore
        return 0


@dataclass
class LandEntry:
    id: str
    name: str
    set: str
    collector_number: str
    is_basic_land: bool
    local_paths: list[str]
    oracle_id: str | None = None
    ua_all: int = 0
    ua_in_set: int = 0

    @property
    def has_art(self) -> bool:
        return len(self.local_paths) > 0

    @property
    def kind(self) -> str:
        return "basic" if self.is_basic_land else "nonbasic"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _iter_land_entries(kind: str, set_filter: Optional[str]) -> Iterable[dict]:
    """
    Yields bulk index entries restricted by kind and optional set filter.
    kind: 'basic' | 'nonbasic' | 'all'
    """
    set_norm = set_filter.lower() if set_filter else None

    def _db_call() -> list[dict]:
        entries: list[dict] = []
        if kind in {"basic", "all"}:
            entries.extend(
                create_pdf.db_query_basic_lands(
                    limit=None,
                    lang_filter=None,
                    set_filter=set_norm,
                )
            )
        if kind in {"nonbasic", "all"}:
            entries.extend(
                create_pdf.db_query_non_basic_lands(
                    limit=None,
                    lang_filter=None,
                    set_filter=set_norm,
                )
            )
        return entries

    def _json_fallback() -> list[dict]:
        index = create_pdf._load_bulk_index()
        results: list[dict] = []
        for entry in index.get("entries", {}).values():
            is_basic = bool(entry.get("is_basic_land"))
            if kind == "basic" and not is_basic:
                continue
            if kind == "nonbasic" and is_basic:
                continue
            if set_norm and (entry.get("set") or "").lower() != set_norm:
                continue
            type_line = (entry.get("type_line") or "").lower()
            if "land" not in type_line:
                continue
            results.append(entry)
        return results

    entries = create_pdf._db_first_fetch(
        "coverage land entries",
        _db_call,
        _json_fallback,
        allow_empty=True,
    )

    for entry in entries:
        type_line = (entry.get("type_line") or "").lower()
        if "land" not in type_line:
            continue
        yield entry


def _local_art_paths(entry: dict) -> list[str]:
    # Reuse create_pdf helper to compute expected shared paths
    return create_pdf._shared_land_art_paths(entry)


def _ensure_reports_dir(kind: str) -> Path:
    # kind: 'land-coverage' or 'token-coverage'
    root = (
        Path(create_pdf.project_root_directory)
        / "magic-the-gathering"
        / "shared"
        / "reports"
        / kind
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def compute_coverage(
    kind: str, set_filter: Optional[str]
) -> tuple[list[LandEntry], dict]:
    rows: list[LandEntry] = []
    total = 0
    covered = 0
    per_set = {}
    # Cache UA counts to avoid repeated DB hits per oracle
    ua_cache_all: dict[str, int] = {}
    ua_cache_by_set: dict[tuple[str, str], int] = {}

    for entry in _iter_land_entries(kind, set_filter):
        total += 1
        local_paths = _local_art_paths(entry)
        # Unique artwork counts (optional, guarded by cache)
        oid = entry.get("oracle_id") or None
        ua_all = 0
        ua_in_set = 0
        if oid:
            if oid in ua_cache_all:
                ua_all = ua_cache_all[oid]
            else:
                ua_all = db_count_unique_artworks(oracle_id=oid)
                ua_cache_all[oid] = ua_all
            key = (oid, (entry.get("set") or "").lower())
            if key in ua_cache_by_set:
                ua_in_set = ua_cache_by_set[key]
            else:
                ua_in_set = db_count_unique_artworks(oracle_id=oid, set_filter=key[1])
                ua_cache_by_set[key] = ua_in_set

        land = LandEntry(
            id=str(entry.get("id") or ""),
            name=str(entry.get("name") or ""),
            set=(entry.get("set") or "").lower(),
            collector_number=str(entry.get("collector_number") or ""),
            is_basic_land=bool(entry.get("is_basic_land")),
            local_paths=local_paths,
            oracle_id=entry.get("oracle_id"),
            ua_all=ua_all,
            ua_in_set=ua_in_set,
        )
        if land.has_art:
            covered += 1
        per_set.setdefault(land.set, {"total": 0, "covered": 0})
        per_set[land.set]["total"] += 1
        if land.has_art:
            per_set[land.set]["covered"] += 1
        rows.append(land)

    summary = {
        "kind": kind,
        "set_filter": set_filter,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "total": total,
        "covered": covered,
        "missing": total - covered,
        "coverage_pct": (covered / total * 100.0) if total else 100.0,
        "per_set": per_set,
    }
    return rows, summary


def _write_common_outputs(
    rows: list[LandEntry], summary: dict, out_dir: Optional[str], report_dir: str
) -> tuple[Path, Path]:
    reports_root = _ensure_reports_dir(report_dir)
    subdir = Path(out_dir) if out_dir else reports_root / _timestamp()
    subdir.mkdir(parents=True, exist_ok=True)

    # CSV
    base_csv_name = (
        "land_coverage.csv" if report_dir == "land-coverage" else "token_coverage.csv"
    )
    csv_path = subdir / base_csv_name
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "name",
                "set",
                "collector",
                "oracle_id",
                "ua_all",
                "ua_in_set",
                "kind",
                "has_art",
                "local_paths",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.name,
                    r.set.upper(),
                    r.collector_number,
                    r.oracle_id or "",
                    r.ua_all,
                    r.ua_in_set,
                    r.kind,
                    "yes" if r.has_art else "no",
                    " ".join(r.local_paths),
                ]
            )

    # Per-set breakdown
    per_set_path = subdir / "per_set_summary.csv"
    with open(per_set_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["set", "total", "covered", "missing", "coverage_pct"])
        for s, stats in sorted(summary.get("per_set", {}).items()):
            total = stats.get("total", 0)
            covered = stats.get("covered", 0)
            missing = total - covered
            pct = (covered / total * 100.0) if total else 100.0
            writer.writerow([s.upper(), total, covered, missing, f"{pct:.1f}"])

    # Missing-only
    missing_only_path = subdir / "missing_only.csv"
    with open(missing_only_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "set", "collector", "kind"])
        for r in rows:
            if not r.has_art:
                writer.writerow([r.name, r.set.upper(), r.collector_number, r.kind])

    # JSON
    json_path = subdir / (
        "land_coverage_summary.json"
        if report_dir == "land-coverage"
        else "token_coverage_summary.json"
    )
    payload = {
        "summary": summary,
        "rows": [asdict(r) for r in rows],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    return csv_path, json_path


def compute_token_coverage(set_filter: Optional[str]) -> tuple[list[LandEntry], dict]:
    set_norm = set_filter.lower() if set_filter else None

    def _db_call() -> list[dict]:
        return create_pdf.db_query_tokens(set_filter=set_norm, limit=None)

    def _json_fallback() -> list[dict]:
        index = create_pdf._load_bulk_index()
        entries = index.get("entries", {})
        token_ids = index.get("token_ids", [])
        return [entries.get(card_id) for card_id in token_ids if entries.get(card_id)]

    token_entries = create_pdf._db_first_fetch(
        "coverage token entries",
        _db_call,
        _json_fallback,
        allow_empty=True,
    )

    rows: list[LandEntry] = []
    total = 0
    covered = 0
    per_set: dict[str, dict] = {}

    for entry in token_entries:
        if not entry:
            continue
        if set_norm and (entry.get("set") or "").lower() != set_norm:
            continue

        total += 1
        local_path, has_local = create_pdf._token_entry_local_path(entry)
        name = entry.get("name") or ""
        card_id = entry.get("id") or entry.get("uuid") or entry.get("oracle_id") or ""
        rows.append(
            LandEntry(
                id=str(card_id),
                name=str(name or ""),
                set=(entry.get("set") or "").lower(),
                collector_number=str(entry.get("collector_number") or ""),
                is_basic_land=False,
                local_paths=[str(local_path)] if has_local else [],
                oracle_id=entry.get("oracle_id"),
            )
        )
        if has_local:
            covered += 1
        ps = per_set.setdefault(
            (entry.get("set") or "").lower(), {"total": 0, "covered": 0}
        )
        ps["total"] += 1
        if has_local:
            ps["covered"] += 1

    summary = {
        "kind": "tokens",
        "set_filter": set_filter,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "total": total,
        "covered": covered,
        "missing": total - covered,
        "coverage_pct": (covered / total * 100.0) if total else 100.0,
        "per_set": per_set,
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute coverage (lands or tokens) against shared libraries."
    )
    parser.add_argument(
        "--type",
        choices=["basic", "nonbasic", "all", "tokens"],
        default="nonbasic",
        help="Which items to include",
    )
    parser.add_argument(
        "--set",
        dest="set_code",
        help="Restrict to a specific set code (e.g., mh3) or multiple, comma-separated (e.g., mh3,khm)",
    )
    parser.add_argument(
        "--out",
        dest="out_dir",
        help="Optional directory to write reports into (default: shared/reports/<category>/<timestamp>)",
    )
    parser.add_argument(
        "--missing-only",
        dest="missing_only",
        action="store_true",
        help="Filter output rows to only missing entries (still writes full per-set and JSON summaries)",
    )
    parser.add_argument(
        "--open",
        dest="open_dir",
        action="store_true",
        help="Open the output folder in Finder after writing reports (macOS)",
    )
    args = parser.parse_args()
    # Support comma-separated sets
    set_list: list[str | None]
    if args.set_code and "," in args.set_code:
        set_list = [s.strip().lower() or None for s in args.set_code.split(",")]
    else:
        set_list = [args.set_code]

    for one_set in set_list:
        if args.type == "tokens":
            rows, summary = compute_token_coverage(one_set)
            if args.missing_only:
                rows = [r for r in rows if not r.has_art]
            csv_path, json_path = _write_common_outputs(
                rows, summary, args.out_dir, "token-coverage"
            )
            print(f"Wrote token coverage CSV: {csv_path}")
            print(f"Wrote token coverage JSON: {json_path}")
            print(
                f"Coverage: {summary['covered']}/{summary['total']} ({summary['coverage_pct']:.1f}%) kind={summary['kind']} set={one_set or 'ALL'}"
            )
            if args.open_dir:
                try:
                    create_pdf._reveal_in_finder(str(csv_path.parent))
                except Exception:
                    pass
            continue

        rows, summary = compute_coverage(args.type, one_set)
        if args.missing_only:
            rows = [r for r in rows if not r.has_art]
        csv_path, json_path = _write_common_outputs(
            rows, summary, args.out_dir, "land-coverage"
        )
        print(f"Wrote coverage CSV: {csv_path}")
        print(f"Wrote coverage JSON: {json_path}")
        print(
            f"Coverage: {summary['covered']}/{summary['total']} ({summary['coverage_pct']:.1f}%) kind={summary['kind']} set={one_set or 'ALL'}"
        )
        if args.open_dir:
            try:
                create_pdf._reveal_in_finder(str(csv_path.parent))
            except Exception:
                pass


if __name__ == "__main__":
    main()
