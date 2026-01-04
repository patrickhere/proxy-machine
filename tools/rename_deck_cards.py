#!/usr/bin/env python3
"""
Rename deck card files to match project naming conventions.

Current format: <set>-<collector>-<cardname>.png
Target format: <cardname>-<arttype>-<lang>-<set>[-<collector>].png

Usage:
  python tools/rename_deck_cards.py <directory> --dry-run  # Preview
  python tools/rename_deck_cards.py <directory>            # Apply
"""

import argparse
from pathlib import Path
from collections import defaultdict
from typing import Optional


def parse_current_filename(filename: str) -> Optional[dict]:
    """Parse current filename format: <set>-<collector>-<cardname>.png"""
    stem = Path(filename).stem
    parts = stem.split("-", 2)  # Split on first 2 hyphens only

    if len(parts) < 3:
        return None

    set_code = parts[0]
    collector = parts[1]
    cardname = parts[2]

    return {
        "set": set_code,
        "collector": collector,
        "cardname": cardname,
        "ext": Path(filename).suffix,
    }


def slugify_cardname(cardname: str) -> str:
    """Convert card name to slug format (lowercase, hyphens)."""
    # Already in slug format from filename
    return cardname.lower()


def determine_art_type(filename: str, cardname: str) -> str:
    """
    Determine art type from filename or card name.

    Without Scryfall data, we default to 'standard' unless we can infer
    from the filename or card characteristics.
    """
    filename_lower = filename.lower()
    cardname_lower = cardname.lower()

    # Check for art type indicators in filename
    if "fullart" in filename_lower or "full-art" in filename_lower:
        return "fullart"
    if "borderless" in filename_lower:
        return "borderless"
    if "showcase" in filename_lower:
        return "showcase"
    if "extended" in filename_lower or "extendedart" in filename_lower:
        return "extended"
    if "textless" in filename_lower:
        return "textless"
    if "retro" in filename_lower:
        return "retro"

    # Default to standard
    return "standard"


def build_new_filename(
    parsed: dict, art_type: str = "standard", lang: str = "en"
) -> str:
    """Build new filename in project format."""
    cardname_slug = slugify_cardname(parsed["cardname"])
    set_code = parsed["set"].lower()
    collector = parsed["collector"]
    ext = parsed["ext"]

    # Format: <cardname>-<arttype>-<lang>-<set>[-<collector>].ext
    # Include collector number to avoid collisions
    new_name = f"{cardname_slug}-{art_type}-{lang}-{set_code}-{collector}{ext}"

    return new_name


def rename_files(directory: Path, dry_run: bool = True) -> tuple[int, int, list[str]]:
    """
    Rename all PNG files in directory to match project conventions.

    Returns: (renamed_count, skipped_count, errors)
    """
    if not directory.exists() or not directory.is_dir():
        return 0, 0, [f"Directory does not exist: {directory}"]

    files = sorted(
        [
            f
            for f in directory.iterdir()
            if f.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
    )

    if not files:
        return 0, 0, [f"No image files found in {directory}"]

    print(f"\nProcessing {len(files)} files in: {directory.name}/")
    print("=" * 70)

    renamed_count = 0
    skipped_count = 0
    errors = []

    # Track new filenames to detect collisions
    new_names = defaultdict(list)

    for file_path in files:
        parsed = parse_current_filename(file_path.name)

        if not parsed:
            skipped_count += 1
            errors.append(f"Could not parse: {file_path.name}")
            continue

        # Determine art type (default to standard without Scryfall data)
        art_type = determine_art_type(file_path.name, parsed["cardname"])

        # Build new filename
        new_name = build_new_filename(parsed, art_type=art_type, lang="en")
        new_path = file_path.parent / new_name

        # Track for collision detection
        new_names[new_name].append(file_path.name)

        # Check if already correctly named
        if file_path.name == new_name:
            skipped_count += 1
            continue

        # Check if target already exists
        if new_path.exists() and new_path != file_path:
            skipped_count += 1
            errors.append(f"Target exists: {new_name} (source: {file_path.name})")
            continue

        if dry_run:
            print(f"  {file_path.name}")
            print(f"    -> {new_name}")
            renamed_count += 1
        else:
            try:
                file_path.rename(new_path)
                renamed_count += 1
                print(f"[OK] {file_path.name} -> {new_name}")
            except Exception as e:
                errors.append(f"Failed to rename {file_path.name}: {e}")
                skipped_count += 1

    # Report collisions
    collisions = {k: v for k, v in new_names.items() if len(v) > 1}
    if collisions:
        print("\n" + "=" * 70)
        print("WARNING: Filename collisions detected:")
        for new_name, sources in collisions.items():
            print(f"\n  {new_name} would be created from:")
            for src in sources:
                print(f"    - {src}")

    return renamed_count, skipped_count, errors


def main():
    parser = argparse.ArgumentParser(
        description="Rename deck card files to match project naming conventions"
    )
    parser.add_argument(
        "directory", type=Path, help="Directory containing files to rename"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Deck Card Renaming Tool")
    print("=" * 70)

    if args.dry_run:
        print("\n[DRY RUN MODE] No files will be modified\n")

    renamed, skipped, errors = rename_files(args.directory, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if args.dry_run:
        print(f"Would rename: {renamed} files")
    else:
        print(f"Renamed: {renamed} files")

    print(f"Skipped: {skipped} files")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for error in errors[:10]:
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

    if args.dry_run and renamed > 0:
        print("\nRun without --dry-run to apply changes")
    elif renamed > 0:
        print("\nRenaming complete!")


if __name__ == "__main__":
    main()
