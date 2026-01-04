#!/usr/bin/env python3
"""Shared card library sync between profiles.

Syncs cards from shared directories to profile-specific directories,
avoiding duplicates and maintaining organization.
"""

import sys
import shutil
from pathlib import Path
from typing import Set, Tuple


SHARED_DIRS = {
    "basics": Path("shared/basic-lands"),
    "nonbasics": Path("shared/non-basic-lands"),
    "tokens": Path("shared/tokens"),
}


def get_profile_dirs(profile_name: str) -> dict:
    """Get profile directories."""
    base = Path(f"profiles/{profile_name}/pictures-of-cards")
    return {
        "front": base / "front",
        "back": base / "back",
        "double_sided": base / "double-sided",
    }


def get_file_hash_set(directory: Path) -> Set[str]:
    """Get set of file names (without path) in directory."""
    if not directory.exists():
        return set()

    files = set()
    for file in directory.rglob("*"):
        if file.is_file():
            files.add(file.name)
    return files


def sync_shared_to_profile(
    profile_name: str, shared_type: str, dry_run: bool = True
) -> Tuple[int, int]:
    """Sync shared library to profile.

    Returns: (copied, skipped)
    """
    if shared_type not in SHARED_DIRS:
        print(f"[ERROR] Unknown shared type: {shared_type}")
        return 0, 0

    shared_dir = SHARED_DIRS[shared_type]
    if not shared_dir.exists():
        print(f"[ERROR] Shared directory not found: {shared_dir}")
        return 0, 0

    profile_dirs = get_profile_dirs(profile_name)
    target_dir = profile_dirs["front"]  # Default to front

    if not target_dir.exists():
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"[OK] Created directory: {target_dir}")

    # Get existing files in profile
    existing_files = get_file_hash_set(target_dir)

    # Find files to copy
    to_copy = []
    for file in shared_dir.rglob("*"):
        if file.is_file() and file.suffix.lower() in {".jpg", ".png", ".jpeg"}:
            if file.name not in existing_files:
                to_copy.append(file)

    copied = 0
    skipped = len(existing_files)

    if dry_run:
        print(f"\n[DRY RUN] Would copy {len(to_copy)} files")
        for file in to_copy[:10]:  # Show first 10
            print(f"  {file.name}")
        if len(to_copy) > 10:
            print(f"  ... and {len(to_copy) - 10} more")
    else:
        print(f"\nCopying {len(to_copy)} files...")
        for file in to_copy:
            dest = target_dir / file.name
            shutil.copy2(file, dest)
            copied += 1
            if copied % 100 == 0:
                print(f"  Copied {copied}/{len(to_copy)}...")
        print(f"[OK] Copied {copied} files")

    return copied, skipped


def sync_all_shared(profile_name: str, dry_run: bool = True):
    """Sync all shared libraries to profile."""
    print(f"\n{'=' * 70}")
    print(f"  SHARED LIBRARY SYNC: {profile_name}")
    print(f"{'=' * 70}")

    if dry_run:
        print("\n[DRY RUN MODE] No files will be copied")

    total_copied = 0
    total_skipped = 0

    for shared_type in SHARED_DIRS:
        print(f"\n[{shared_type.upper()}]")
        copied, skipped = sync_shared_to_profile(profile_name, shared_type, dry_run)
        total_copied += copied
        total_skipped += skipped
        print(f"  Copied: {copied}")
        print(f"  Skipped: {skipped} (already exist)")

    print(f"\n{'=' * 70}")
    print(f"  TOTAL: {total_copied} copied, {total_skipped} skipped")
    print(f"{'=' * 70}\n")


def list_shared_contents():
    """List contents of shared directories."""
    print(f"\n{'=' * 70}")
    print("  SHARED LIBRARY CONTENTS")
    print(f"{'=' * 70}")

    for shared_type, shared_dir in SHARED_DIRS.items():
        print(f"\n[{shared_type.upper()}]")
        if not shared_dir.exists():
            print("  [NOT FOUND]")
            continue

        files = list(shared_dir.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        dir_count = sum(1 for f in files if f.is_dir())

        print(f"  Files: {file_count:,}")
        print(f"  Directories: {dir_count:,}")
        print(f"  Path: {shared_dir}")

    print(f"\n{'=' * 70}\n")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python shared_library_sync.py <command> [options]")
        print("\nCommands:")
        print("  list                    - List shared library contents")
        print("  sync <profile>          - Sync shared to profile (dry run)")
        print("  sync <profile> --apply  - Sync shared to profile (apply changes)")
        print("\nExamples:")
        print("  python shared_library_sync.py list")
        print("  python shared_library_sync.py sync patrick")
        print("  python shared_library_sync.py sync patrick --apply")
        return 1

    command = sys.argv[1]

    if command == "list":
        list_shared_contents()
        return 0

    if command == "sync":
        if len(sys.argv) < 3:
            print("[ERROR] Profile name required")
            return 1

        profile_name = sys.argv[2]
        dry_run = "--apply" not in sys.argv

        sync_all_shared(profile_name, dry_run)

        if dry_run:
            print("\n[INFO] This was a dry run. Use --apply to actually copy files.")

        return 0

    print(f"[ERROR] Unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
