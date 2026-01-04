#!/usr/bin/env python3
"""Migration helper to fix misclassified MDFC/special lands.

This script scans:
  shared/non-basic-lands/special/mdfc
and reclassifies each PNG using the existing `_classify_land_type` logic
from `create_pdf.py`. If the new classification is not a `special/*` bucket,
it proposes/moves the file into the appropriate dual/tri/other folder.

Usage (from proxy-machine/):
  python3 migrate_mdfc_lands.py           # dry run, shows planned moves
  python3 migrate_mdfc_lands.py --apply   # perform moves
"""

import argparse
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple

# Project-root-relative paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_ROOT = PROJECT_ROOT / "magic-the-gathering" / "shared"
NON_BASIC_ROOT = SHARED_ROOT / "non-basic-lands"
SPECIAL_MDFC_DIR = NON_BASIC_ROOT / "special" / "mdfc"

BULK_DB_PATH = PROJECT_ROOT / "magic-the-gathering" / "bulk-data" / "bulk.db"

# Regex to extract name slug, set code, and collector number from filenames like:
#   arcanesanctum-standard-en-dsc-259.png
FILENAME_RE = re.compile(
    r"^(?P<name_slug>[a-z0-9]+)(?:-[a-z0-9]+)*-standard-[a-z]{2}-(?P<set_code>[a-z0-9]+)-(?P<cn>[0-9]+)\.[a-z0-9]+$"
)


def _load_print_from_db(name_slug: str, set_code: str, cn: str) -> Optional[dict]:
    if not BULK_DB_PATH.exists():
        return None

    conn = sqlite3.connect(str(BULK_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT name, type_line, oracle_text
            FROM prints
            WHERE name_slug = ? AND set_code = ? AND collector_number = ?
            LIMIT 1
            """,
            (name_slug, set_code.upper(), cn),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def plan_moves() -> List[Tuple[Path, Path, str]]:
    """Return a list of (src, dest, reason) for files that should move.

    Strategy:
    - For each PNG in special/mdfc, search under NON_BASIC_ROOT for the same
      filename, excluding the special/mdfc subtree.
    - If exactly one match is found, propose moving the special/mdfc copy
      into that directory.
    - If zero or multiple matches exist, skip to avoid ambiguity.
    """

    moves: List[Tuple[Path, Path, str]] = []

    if not SPECIAL_MDFC_DIR.exists():
        return moves

    for file in sorted(SPECIAL_MDFC_DIR.iterdir()):
        if not file.is_file() or file.suffix.lower() != ".png":
            continue

        # Look for other copies of this filename under non-basic-lands,
        # excluding the special/mdfc subtree itself.
        matches: List[Path] = []
        for candidate in NON_BASIC_ROOT.rglob(file.name):
            try:
                # Skip the special/mdfc source directory
                candidate_rel = candidate.relative_to(NON_BASIC_ROOT)
            except ValueError:
                continue

            parts = candidate_rel.parts
            if len(parts) >= 2 and parts[0] == "special" and parts[1] == "mdfc":
                continue

            matches.append(candidate)

        if len(matches) != 1:
            # Zero or multiple possible destinations: skip to avoid bad moves.
            continue

        dest_path = matches[0]

        # Skip if src and dest are the same path
        if dest_path.resolve() == file.resolve():
            continue

        reason = f"match existing copy at {dest_path.relative_to(NON_BASIC_ROOT)}"
        moves.append((file, dest_path, reason))

    return moves


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate misclassified MDFC lands")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (move files). Without this flag, runs as dry-run.",
    )
    args = parser.parse_args()

    print("Scanning for misclassified MDFC lands in:")
    print(f"  {SPECIAL_MDFC_DIR}")

    moves = plan_moves()

    if not moves:
        print(
            "No moves needed. Either directory is empty or all cards are truly special."
        )
        return

    print()
    print(f"Planned moves: {len(moves)}")
    for src, dest, classification in moves[:50]:
        rel_src = src.relative_to(PROJECT_ROOT)
        rel_dest = dest.relative_to(PROJECT_ROOT)
        print(f"  {rel_src} -> {rel_dest}  ({classification})")
    if len(moves) > 50:
        print(f"  ... and {len(moves) - 50} more")

    if not args.apply:
        print()
        print("Dry run only. Re-run with --apply to perform these moves.")
        return

    print()
    print("Applying moves...")
    applied = 0
    for src, dest, classification in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        applied += 1
    print(f"Done. Moved {applied} files.")


if __name__ == "__main__":
    main()
