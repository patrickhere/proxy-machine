#!/usr/bin/env python3
"""
Organize SLD (Secret Lair Drop) cards into subdirectories by drop name.

This tool scans loose SLD image files and organizes them into subdirectories
based on their collector number, using official drop names from Scryfall.

Usage:
  python tools/organize_sld.py --dry-run  # Preview changes
  python tools/organize_sld.py            # Apply changes
"""

import sys
from pathlib import Path
from collections import defaultdict

# Import collector range mapping
from sld_collector_ranges import get_drop_name_by_collector

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "proxy-machine"))

SHARED_ROOT = PROJECT_ROOT / "magic-the-gathering" / "shared"


def extract_collector_number(filename: str) -> str | None:
    """Extract collector number from filename.

    Expected format: cardname-arttype-lang-collector.png
    Example: forest-fullart-en-1092.png -> 1092
    """
    stem = Path(filename).stem
    parts = stem.split("-")

    if len(parts) >= 4:
        # Last part should be collector number
        collector = parts[-1]
        # Handle special characters (s=star, t=dagger, d=double-dagger)
        return collector

    return None


def organize_sld_directory(
    directory: Path, dry_run: bool = True
) -> tuple[int, int, list[str]]:
    """Organize SLD files in a directory into drop subdirectories.

    Args:
        directory: Base directory containing SLD folder
        dry_run: If True, preview changes without modifying files

    Returns: (moved_count, skipped_count, errors)
    """
    if not directory.exists():
        return 0, 0, [f"Directory does not exist: {directory}"]

    sld_dir = directory / "sld"
    if not sld_dir.exists():
        return 0, 0, [f"No SLD directory found: {sld_dir}"]

    print(f"\nProcessing: {sld_dir}")

    # Group files by drop name (based on collector number)
    files_by_drop = defaultdict(list)
    skipped_files = []

    for file_path in sorted(sld_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if file_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue

        collector_num = extract_collector_number(file_path.name)
        if not collector_num:
            skipped_files.append(
                f"Could not extract collector number: {file_path.name}"
            )
            continue

        drop_name = get_drop_name_by_collector(collector_num)
        if not drop_name:
            skipped_files.append(
                f"No drop mapping for collector #{collector_num}: {file_path.name}"
            )
            continue

        files_by_drop[drop_name].append(file_path)

    # Report groupings
    print(f"\nFound {len(files_by_drop)} distinct drops:")
    for drop_name in sorted(files_by_drop.keys()):
        print(f"  {drop_name}: {len(files_by_drop[drop_name])} files")

    if skipped_files:
        print(f"\nSkipped {len(skipped_files)} files:")
        for msg in skipped_files[:10]:
            print(f"  - {msg}")
        if len(skipped_files) > 10:
            print(f"  ... and {len(skipped_files) - 10} more")

    # Move files into drop subdirectories
    moved_count = 0
    errors = []

    if dry_run:
        print("\n[DRY RUN] Would create the following structure:")
    else:
        print("\nOrganizing files...")

    for drop_name, files in sorted(files_by_drop.items()):
        drop_dir = sld_dir / drop_name

        if dry_run:
            print(f"  {drop_dir.name}/ ({len(files)} files)")
        else:
            drop_dir.mkdir(exist_ok=True)

            for file_path in files:
                dest_path = drop_dir / file_path.name

                try:
                    file_path.rename(dest_path)
                    moved_count += 1
                except Exception as e:
                    errors.append(f"Failed to move {file_path.name}: {e}")

    return moved_count, len(skipped_files), errors


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Organize SLD cards into drop-specific subdirectories"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--type",
        choices=["basic", "nonbasic", "tokens", "all"],
        default="all",
        help="Which card type to organize (default: all)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("SLD Organization Tool")
    print("=" * 70)

    if args.dry_run:
        print("\n[DRY RUN MODE] No files will be modified\n")

    # Determine which directories to process
    directories = []
    if args.type in ["basic", "all"]:
        directories.append(("Basic Lands", SHARED_ROOT / "basic-lands"))
    if args.type in ["nonbasic", "all"]:
        directories.append(("Non-Basic Lands", SHARED_ROOT / "non-basic-lands"))
    if args.type in ["tokens", "all"]:
        directories.append(("Tokens", SHARED_ROOT / "tokens"))

    total_moved = 0
    total_skipped = 0
    all_errors = []

    for label, directory in directories:
        moved, skipped, errors = organize_sld_directory(directory, dry_run=args.dry_run)
        total_moved += moved
        total_skipped += skipped
        all_errors.extend(errors)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if args.dry_run:
        print(f"Would move: {total_moved} files")
    else:
        print(f"Moved: {total_moved} files")

    print(f"Skipped: {total_skipped} files")

    if all_errors:
        print(f"\nErrors: {len(all_errors)}")
        for error in all_errors[:5]:
            print(f"  - {error}")
        if len(all_errors) > 5:
            print(f"  ... and {len(all_errors) - 5} more")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes")
    else:
        print("\nOrganization complete!")


if __name__ == "__main__":
    main()
