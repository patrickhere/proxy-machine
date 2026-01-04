#!/usr/bin/env python3
"""
De-duplicate identical images in shared libraries using content hashes and hardlinks.

- Scans magic-the-gathering/shared/* for image files
- Computes SHA-256 hash per file (with size pre-check)
- For files with identical hashes, replaces duplicates with hard links to a canonical file
- Skips linking across filesystems (different st_dev)

Usage:
  uv run python dedupe_shared_images.py [--root <path>] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Dict, List

import create_pdf


def _shared_root() -> Path:
    return Path(create_pdf.project_root_directory) / "magic-the-gathering" / "shared"


essential_exts = {".png", ".jpg", ".jpeg", ".webp"}


def file_hash(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def group_by_hash(root: Path) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = {}
    size_map: Dict[int, List[Path]] = {}

    for p in root.rglob("*"):
        if not (
            p.is_file()
            and p.suffix.lower() in essential_exts
            and not p.name.startswith(".")
        ):
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        size_map.setdefault(sz, []).append(p)

    # Only hash files that share a size with at least one other
    for size, files in size_map.items():
        if len(files) < 2:
            continue
        for path in files:
            try:
                digest = file_hash(path)
            except OSError:
                continue
            groups.setdefault(digest, []).append(path)

    return groups


def dedupe_groups(
    groups: Dict[str, List[Path]], *, dry_run: bool = False
) -> tuple[int, int]:
    changed = 0
    removed = 0

    for digest, files in groups.items():
        if len(files) < 2:
            continue
        # Choose canonical (shortest path for stability)
        files_sorted = sorted(files, key=lambda p: (len(str(p)), str(p)))
        canon = files_sorted[0]
        try:
            canon_stat = canon.stat()
        except OSError:
            continue
        for dup in files_sorted[1:]:
            try:
                st = dup.stat()
            except OSError:
                continue
            # Skip if already hardlinked to canon (same inode)
            if (st.st_ino == canon_stat.st_ino) and (st.st_dev == canon_stat.st_dev):
                continue
            # Only link if same device
            if st.st_dev != canon_stat.st_dev:
                continue
            if dry_run:
                removed += 1
                continue
            try:
                # Remove and link to canonical
                dup.unlink(missing_ok=True)
                os.link(canon, dup)
                changed += 1
                removed += 1
            except OSError:
                # Best-effort; skip failures
                continue

    return changed, removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hardlink de-duplication for shared images"
    )
    parser.add_argument("--root", help="Root directory to scan (default: shared/)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report only; do not modify files"
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else _shared_root()
    if not root.exists():
        print(f"Root not found: {root}")
        return

    groups = group_by_hash(root)
    changed, removed = dedupe_groups(groups, dry_run=args.dry_run)
    print(f"Duplicate groups: {sum(1 for v in groups.values() if len(v) > 1)}")
    print(
        f"Hardlinked {changed} groups; removed {removed} duplicate file(s).{' (dry run)' if args.dry_run else ''}"
    )


if __name__ == "__main__":
    main()
