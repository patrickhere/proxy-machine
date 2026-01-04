#!/usr/bin/env python3
"""
Migration script to merge set code variants into canonical folders.
Handles CED/CEI -> CE and other related sets.
"""

import os
import sys
from pathlib import Path

# Add proxy-machine to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from create_pdf import _normalize_set_code


def merge_set_variants(base_path: Path, dry_run: bool = True) -> None:
    """Merge set code variants into canonical folders."""
    print(f"\n🔍 Scanning {base_path}")

    if not base_path.exists():
        print(f"❌ Path doesn't exist: {base_path}")
        return

    # Find all set directories
    set_dirs = [d for d in base_path.iterdir() if d.is_dir()]

    # Group folders by their normalized name
    normalized_map: dict[str, list[Path]] = {}

    for set_dir in set_dirs:
        original_name = set_dir.name
        normalized_name = _normalize_set_code(original_name)

        if normalized_name not in normalized_map:
            normalized_map[normalized_name] = []
        normalized_map[normalized_name].append(set_dir)

    # Find groups that need merging (multiple source folders -> one canonical)
    merges_needed = {
        norm: folders for norm, folders in normalized_map.items() if len(folders) > 1
    }

    if not merges_needed:
        print("✅ No set variants found that need merging")
        return

    print(f"Found {len(merges_needed)} sets with variants to merge:")
    total_files = 0

    for normalized_name, folders in sorted(merges_needed.items()):
        print(f"\n📁 Merging into '{normalized_name}/':")
        for folder in folders:
            file_count = len(list(folder.glob("*.png"))) + len(
                list(folder.glob("*.jpg"))
            )
            total_files += file_count
            print(f"   - {folder.name}/ ({file_count} files)")

        if dry_run:
            continue

        # Find or create the target folder
        target_folder = base_path / normalized_name

        # If target doesn't exist, rename the first source to it
        if not target_folder.exists():
            first_source = folders[0]
            print(f"   ✅ Creating {normalized_name}/ from {first_source.name}/")
            first_source.rename(target_folder)
            folders = folders[1:]  # Remove the renamed one from list

        # Merge remaining folders into target
        for source_folder in folders:
            if not source_folder.exists():  # May have been renamed already
                continue

            if source_folder == target_folder:
                continue

            print(f"   🔄 Merging {source_folder.name}/ -> {target_folder.name}/")

            # Move all files from source to target
            moved = 0
            skipped = 0
            for file_path in source_folder.iterdir():
                if file_path.is_file():
                    target_path = target_folder / file_path.name
                    if target_path.exists():
                        skipped += 1
                    else:
                        file_path.rename(target_path)
                        moved += 1

            print(f"      ✅ Moved {moved} files, skipped {skipped} duplicates")

            # Remove empty source folder
            try:
                source_folder.rmdir()
                print(f"      🗑️  Removed {source_folder.name}/")
            except OSError as e:
                remaining = len(list(source_folder.iterdir()))
                print(
                    f"      ⚠️  Could not remove {source_folder.name}/ ({remaining} items remain): {e}"
                )

    if dry_run:
        print(f"\n📊 Total: Would merge {total_files} files")
    else:
        print("\n✅ Merge complete!")


def main():
    """Main migration function."""
    print("🔧 SET VARIANT MERGER")
    print("=" * 50)
    print("This will merge related sets (e.g., CED/CEI -> CE)")
    print()

    # Paths to check (relative to repo root)
    repo_root = Path(__file__).parent.parent
    basic_lands_path = repo_root / "magic-the-gathering" / "shared" / "basic-lands"
    non_basic_lands_path = (
        repo_root / "magic-the-gathering" / "shared" / "non-basic-lands"
    )

    # First, run in dry-run mode to show what would happen
    print("🔍 DRY RUN - Checking for set variants to merge...")
    merge_set_variants(basic_lands_path, dry_run=True)
    merge_set_variants(non_basic_lands_path, dry_run=True)

    # Ask for confirmation
    print()
    response = input("❓ Apply these merges? [y/N]: ").strip().lower()
    if response in ("y", "yes"):
        print("\n🔧 APPLYING MERGES...")
        merge_set_variants(basic_lands_path, dry_run=False)
        merge_set_variants(non_basic_lands_path, dry_run=False)
        print("\n✅ Migration complete!")
    else:
        print("\n❌ Migration cancelled")


if __name__ == "__main__":
    main()
