#!/usr/bin/env python3
"""
Rules Delta Reporter

- Compares current Scryfall oracle data with the last saved snapshot
- Emits CSV/JSON under magic-the-gathering/shared/reports/deltas_<timestamp>/
- Persists a new snapshot after reporting, to be the baseline for next run

Usage:
  uv run python rules_delta.py

This module exposes generate_reports() used by the dashboard.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import create_pdf


@dataclass
class DeltaRow:
    oracle_id: str
    oracle_name: str
    change_type: str  # changed|added|removed
    prev_text: str | None
    new_text: str | None


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _paths() -> dict[str, str]:
    project_root = create_pdf.project_root_directory
    bulk_dir = create_pdf.BULK_DATA_DIRECTORY
    reports_root = os.path.join(
        project_root, "magic-the-gathering", "shared", "reports"
    )
    out_dir = os.path.join(reports_root, f"deltas_{_timestamp()}")
    snapshot_path = os.path.join(bulk_dir, "oracle_snapshot.json")
    return {
        "project_root": project_root,
        "bulk_dir": bulk_dir,
        "reports_root": reports_root,
        "out_dir": out_dir,
        "snapshot": snapshot_path,
    }


def _load_snapshot(path: str) -> dict[str, dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data  # oracle_id -> {oracle_text, oracle_name, ...}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _current_oracle_map() -> dict[str, dict]:
    oracle_map, _meta = create_pdf._load_oracle_data(force_refresh=False)
    # Keep only fields needed for comparison/snapshot to minimize storage
    slim: dict[str, dict] = {}
    for oid, row in oracle_map.items():
        slim[oid] = {
            "oracle_text": row.get("oracle_text"),
            "oracle_name": row.get("oracle_name"),
            "keywords": row.get("keywords") or [],
            "color_identity": row.get("color_identity") or [],
            "type_line": row.get("type_line"),
        }
    return slim


def _compute_deltas(prev: dict[str, dict], curr: dict[str, dict]) -> list[DeltaRow]:
    rows: list[DeltaRow] = []

    prev_ids = set(prev.keys())
    curr_ids = set(curr.keys())

    # Added
    for oid in sorted(curr_ids - prev_ids):
        r = curr[oid]
        rows.append(
            DeltaRow(
                oracle_id=oid,
                oracle_name=str(r.get("oracle_name") or ""),
                change_type="added",
                prev_text=None,
                new_text=str(r.get("oracle_text") or ""),
            )
        )

    # Removed
    for oid in sorted(prev_ids - curr_ids):
        r = prev[oid]
        rows.append(
            DeltaRow(
                oracle_id=oid,
                oracle_name=str(r.get("oracle_name") or ""),
                change_type="removed",
                prev_text=str(r.get("oracle_text") or ""),
                new_text=None,
            )
        )

    # Changed oracle text
    for oid in sorted(prev_ids & curr_ids):
        a = str(prev[oid].get("oracle_text") or "")
        b = str(curr[oid].get("oracle_text") or "")
        if a.strip() != b.strip():
            rows.append(
                DeltaRow(
                    oracle_id=oid,
                    oracle_name=str(
                        curr[oid].get("oracle_name")
                        or prev[oid].get("oracle_name")
                        or ""
                    ),
                    change_type="changed",
                    prev_text=a,
                    new_text=b,
                )
            )

    return rows


def _write_outputs(rows: list[DeltaRow], out_dir: str) -> tuple[Path, Path]:
    os.makedirs(out_dir, exist_ok=True)
    csv_path = Path(out_dir) / "oracle_deltas.csv"
    json_path = Path(out_dir) / "oracle_deltas.json"

    # CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["oracle_id", "oracle_name", "change_type", "prev_text", "new_text"]
        )
        for r in rows:
            writer.writerow(
                [
                    r.oracle_id,
                    r.oracle_name,
                    r.change_type,
                    r.prev_text or "",
                    r.new_text or "",
                ]
            )

    # JSON
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(rows),
        "rows": [asdict(r) for r in rows],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    return csv_path, json_path


def generate_reports() -> dict[str, Any]:
    p = _paths()
    prev = _load_snapshot(p["snapshot"])  # may be empty on first run
    curr = _current_oracle_map()

    rows = _compute_deltas(prev, curr)

    out_dir = p["out_dir"]
    csv_path, json_path = _write_outputs(rows, out_dir)

    # Persist new snapshot for next comparison
    try:
        with open(p["snapshot"], "w", encoding="utf-8") as fh:
            json.dump(curr, fh)
            fh.write("\n")
    except OSError:
        pass

    return {
        "out_dir": out_dir,
        "csv": str(csv_path),
        "json": str(json_path),
        "count": len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rules (oracle text) delta reporter")
    _ = parser.parse_args()
    result = generate_reports()
    print(
        f"Wrote rules delta report: CSV={result['csv']} JSON={result['json']} (rows={result['count']})"
    )


if __name__ == "__main__":
    main()
