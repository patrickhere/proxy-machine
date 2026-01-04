#!/usr/bin/env python3
"""
One-time migration script to normalize set folder names.
Consolidates folders like 'eos 2' into 'eos' for both basic and non-basic lands.
"""

from pathlib import Path
from create_pdf import _slugify


def normalize_set_folders(base_path: Path, dry_run: bool = True) -> None:
    """Normalize set folder names in the given base path."""
    print(f"\n🔍 Scanning {base_path}")

    if not base_path.exists():
        print(f"❌ Path doesn't exist: {base_path}")
        return

    # Find all set directories
    set_dirs = [d for d in base_path.iterdir() if d.is_dir()]

    # Group folders by their normalized slug
    normalized_groups: dict[str, list[Path]] = {}

    for set_dir in set_dirs:
        original_name = set_dir.name
        normalized_name = _slugify(original_name).lower()

        if normalized_name not in normalized_groups:
            normalized_groups[normalized_name] = []
        normalized_groups[normalized_name].append(set_dir)

    # Find groups with multiple folders (duplicates to merge)
    merges_needed = {
        norm: folders for norm, folders in normalized_groups.items() if len(folders) > 1
    }

    if not merges_needed:
        print("✅ No duplicate set folders found")
        return

    print(f"Found {len(merges_needed)} sets with duplicate folders:")

    for normalized_name, folders in merges_needed.items():
        print(f"\n📁 Set '{normalized_name}' has {len(folders)} folders:")
        for folder in folders:
            file_count = len(list(folder.glob("*.png"))) + len(
                list(folder.glob("*.jpg"))
            )
            print(f"   - {folder.name} ({file_count} images)")

        if dry_run:
            print(f"   → Would merge into: {normalized_name}/")
            continue

        # Find the target folder (prefer the normalized name if it exists)
        target_folder = None
        for folder in folders:
            if folder.name == normalized_name:
                target_folder = folder
                break

        # If no exact match, use the first folder as target
        if not target_folder:
            target_folder = folders[0]

        # Ensure target has the correct normalized name
        if target_folder.name != normalized_name:
            new_target = base_path / normalized_name
            print(f"   ✅ Renaming {target_folder.name} → {normalized_name}")
            target_folder.rename(new_target)
            target_folder = new_target

        # Merge other folders into target
        for folder in folders:
            if folder == target_folder:
                continue

            print(f"   🔄 Merging {folder.name} → {target_folder.name}")

            # Move all files from source to target
            for file_path in folder.iterdir():
                if file_path.is_file():
                    target_path = target_folder / file_path.name
                    if target_path.exists():
                        print(f"      ⚠️  Skipping {file_path.name} (already exists)")
                    else:
                        file_path.rename(target_path)
                        print(f"      ✅ Moved {file_path.name}")

            # Remove empty source folder
            try:
                folder.rmdir()
                print(f"      🗑️  Removed empty folder {folder.name}")
            except OSError as e:
                print(f"      ⚠️  Could not remove {folder.name}: {e}")


def main():
    """Main migration function."""
    print("🔧 SET FOLDER NORMALIZATION MIGRATION")
    print("=" * 50)

    # Paths to check
    basic_lands_path = Path("../magic-the-gathering/shared/basic-lands")
    non_basic_lands_path = Path("../magic-the-gathering/shared/non-basic-lands")

    # First, run in dry-run mode to show what would happen
    print("\n🔍 DRY RUN - Checking for duplicate folders...")
    normalize_set_folders(basic_lands_path, dry_run=True)
    normalize_set_folders(non_basic_lands_path, dry_run=True)

    # Ask for confirmation
    response = input("\n❓ Apply these changes? [y/N]: ").strip().lower()
    if response in ("y", "yes"):
        print("\n🔧 APPLYING CHANGES...")
        normalize_set_folders(basic_lands_path, dry_run=False)
        normalize_set_folders(non_basic_lands_path, dry_run=False)
        print("\n✅ Migration complete!")
    else:
        print("\n❌ Migration cancelled")


if __name__ == "__main__":
    main()
