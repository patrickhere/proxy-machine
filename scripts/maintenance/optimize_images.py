#!/usr/bin/env python3
"""
Optimize shared PNG images (lossless) to reduce disk footprint.

- Scans magic-the-gathering/shared/* for .png images
- Rewrites each PNG with Pillow optimize=True to a temporary file and atomically replaces
  only if the optimized file is smaller
- Skips JPEG/WEBP to avoid quality changes

Usage:
  uv run python optimize_images.py [--root <path>] [--dry-run]

Notes:
- This intentionally keeps things conservative and lossless.
- If you want aggressive optimization, consider installing optipng/pngquant and extending this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image  # type: ignore

import create_pdf

IMAGE_EXTS = {".png"}  # conservative; do not touch JPEG/WEBP by default


def _shared_root() -> Path:
    return Path(create_pdf.project_root_directory) / "magic-the-gathering" / "shared"


def _iter_pngs(root: Path):
    for p in root.rglob("*"):
        if (
            p.is_file()
            and p.suffix.lower() in IMAGE_EXTS
            and not p.name.startswith(".")
        ):
            yield p


def optimize_png(path: Path, *, dry_run: bool = False) -> tuple[bool, int]:
    """Optimize a single PNG file. Returns (changed, bytes_saved)."""
    try:
        orig_size = path.stat().st_size
    except OSError:
        return False, 0

    tmp = path.with_suffix(path.suffix + ".opt")
    try:
        with Image.open(path) as im:
            im.save(tmp, format="PNG", optimize=True, compress_level=9)
        new_size = tmp.stat().st_size
        if new_size < orig_size:
            if dry_run:
                tmp.unlink(missing_ok=True)
                return False, orig_size - new_size
            # Replace atomically
            tmp.replace(path)
            return True, orig_size - new_size
        else:
            tmp.unlink(missing_ok=True)
            return False, 0
    except Exception:
        # Clean up tmp on any failure
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False, 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lossless PNG optimizer for shared libraries"
    )
    parser.add_argument("--root", help="Root directory to scan (default: shared/)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write changes; only report savings",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else _shared_root()
    if not root.exists():
        print(f"Root not found: {root}")
        sys.exit(1)

    total = 0
    changed = 0
    saved_bytes = 0

    for path in _iter_pngs(root):
        total += 1
        did_change, saved = optimize_png(path, dry_run=args.dry_run)
        if saved:
            saved_bytes += saved
        if did_change:
            changed += 1

    mb = saved_bytes / (1024 * 1024)
    print(f"Scanned {total} PNG(s). Optimized {changed}. Saved ~{mb:.2f} MiB.")
    if args.dry_run:
        print("(dry run: no files were modified)")


if __name__ == "__main__":
    main()
