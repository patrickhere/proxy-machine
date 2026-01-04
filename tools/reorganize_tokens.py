#!/usr/bin/env python3
"""
Reorganize token library from set-based to type-based organization.

Current structure: tokens/<set>/<tokenname>-<arttype>-<lang>-<set>.png
Target structure:  tokens/<tokentype>/<tokenname>-<arttype>-<lang>-<set>.png

This groups all tokens by their type (soldier, zombie, spirit, etc.) regardless
of set, making it much easier to find and compare tokens of the same type.

Usage:
  python tools/reorganize_tokens.py --dry-run  # Preview changes
  python tools/reorganize_tokens.py            # Apply changes
"""

import argparse
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List, Tuple, Any


def extract_token_type(filename: str) -> Optional[str]:
    """
    Extract token type from filename.

    Format: <tokenname>-<arttype>-<lang>-<set>.png
    Example: soldier-standard-en-tmd1-1.png -> soldier
    """
    stem = Path(filename).stem
    parts = stem.split("-")

    if len(parts) < 4:
        return None

    # First part is the token type/name
    token_type = parts[0].lower()

    return token_type


def parse_token_filename(filepath: Path) -> Optional[Dict[str, Any]]:
    """Parse token filename and extract components."""
    filename = filepath.name
    stem = filepath.stem

    # Expected format: <tokenname>-<arttype>-<lang>-<set>[-collector].png
    parts = stem.split("-")

    if len(parts) < 4:
        return None

    token_type = parts[0].lower()

    return {
        "token_type": token_type,
        "filename": filename,
        "current_set_dir": filepath.parent.name,
        "full_path": filepath,
    }


def build_new_path(tokens_root: Path, parsed: Dict[str, Any]) -> Path:
    """Build new path based on token type organization."""
    token_type = parsed["token_type"]
    filename = parsed["filename"]

    # New structure: tokens/<tokentype>/<filename>
    new_dir = tokens_root / token_type
    new_path = new_dir / filename

    return new_path


def reorganize_tokens(
    tokens_root: Path, dry_run: bool = True
) -> Tuple[int, int, List[str]]:
    """
    Reorganize all tokens from set-based to type-based structure.

    Returns: (moved_count, skipped_count, errors)
    """
    if not tokens_root.exists() or not tokens_root.is_dir():
        return 0, 0, [f"Tokens directory does not exist: {tokens_root}"]

    print(f"\nScanning tokens directory: {tokens_root}")
    print("=" * 70)

    # Find all token files
    token_files = []
    for set_dir in sorted(tokens_root.iterdir()):
        if not set_dir.is_dir():
            continue
        if set_dir.name.startswith("."):
            continue

        for file_path in set_dir.iterdir():
            if file_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                token_files.append(file_path)

    if not token_files:
        return 0, 0, [f"No token files found in {tokens_root}"]

    print(f"Found {len(token_files)} token files to reorganize\n")

    # Group by token type for reporting
    tokens_by_type = defaultdict(list)
    parse_errors = []

    for file_path in token_files:
        parsed = parse_token_filename(file_path)
        if parsed:
            tokens_by_type[parsed["token_type"]].append(parsed)
        else:
            parse_errors.append(f"Could not parse: {file_path.name}")

    print(f"Token types found: {len(tokens_by_type)}")
    print(f"Parse errors: {len(parse_errors)}\n")

    # Show top token types
    sorted_types = sorted(tokens_by_type.items(), key=lambda x: len(x[1]), reverse=True)
    print("Top 20 token types:")
    for token_type, tokens in sorted_types[:20]:
        print(f"  {token_type:20s} {len(tokens):4d} tokens")

    if len(sorted_types) > 20:
        remaining = sum(len(tokens) for _, tokens in sorted_types[20:])
        print(f"  ... and {len(sorted_types) - 20} more types ({remaining} tokens)")

    print("\n" + "=" * 70)

    if dry_run:
        print("[DRY RUN] Preview of directory structure:\n")
    else:
        print("Reorganizing tokens...\n")

    moved_count = 0
    skipped_count = 0
    errors = []

    # Track which old set directories will be empty
    old_set_dirs = set()

    for token_type, tokens in sorted(tokens_by_type.items()):
        new_dir = tokens_root / token_type

        if dry_run:
            print(f"  {token_type}/ ({len(tokens)} tokens)")
            moved_count += len(tokens)
        else:
            # Create new directory
            new_dir.mkdir(exist_ok=True)

            # Move files
            for parsed in tokens:
                old_path = parsed["full_path"]
                new_path = new_dir / parsed["filename"]

                # Track old directory for cleanup
                old_set_dirs.add(old_path.parent)

                # Check if target already exists
                if new_path.exists() and new_path != old_path:
                    # File already exists at destination
                    skipped_count += 1
                    errors.append(
                        f"Target exists: {new_path.name} (from {old_path.parent.name})"
                    )
                    continue

                try:
                    shutil.move(str(old_path), str(new_path))
                    moved_count += 1
                except Exception as e:
                    errors.append(f"Failed to move {old_path.name}: {e}")
                    skipped_count += 1

    # Clean up empty set directories
    if not dry_run and old_set_dirs:
        print(f"\nCleaning up {len(old_set_dirs)} old set directories...")
        removed_dirs = 0
        for old_dir in old_set_dirs:
            try:
                # Only remove if empty
                if old_dir.exists() and not any(old_dir.iterdir()):
                    old_dir.rmdir()
                    removed_dirs += 1
            except Exception as e:
                errors.append(f"Could not remove {old_dir.name}: {e}")
        print(f"Removed {removed_dirs} empty directories")

    return moved_count, skipped_count, errors + parse_errors


def main():
    parser = argparse.ArgumentParser(
        description="Reorganize token library from set-based to type-based structure"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )
    # Default to magic-the-gathering/shared/tokens relative to repo root
    repo_root = Path(__file__).parent.parent.parent
    default_tokens_dir = repo_root / "magic-the-gathering" / "shared" / "tokens"

    parser.add_argument(
        "--tokens-dir",
        type=Path,
        default=default_tokens_dir,
        help="Path to tokens directory (default: auto-detected)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Token Library Reorganization Tool")
    print("=" * 70)
    print("\nCurrent: tokens/<set>/<tokenname>-<arttype>-<lang>-<set>.png")
    print("Target:  tokens/<tokentype>/<tokenname>-<arttype>-<lang>-<set>.png")
    print("=" * 70)

    if args.dry_run:
        print("\n[DRY RUN MODE] No files will be modified\n")

    moved, skipped, errors = reorganize_tokens(args.tokens_dir, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if args.dry_run:
        print(f"Would move: {moved} files")
    else:
        print(f"Moved: {moved} files")

    print(f"Skipped: {skipped} files")

    if errors:
        print(f"\nIssues: {len(errors)}")
        for error in errors[:10]:
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

    if args.dry_run and moved > 0:
        print("\nRun without --dry-run to apply changes")
    elif moved > 0:
        print("\nReorganization complete!")
        print("\nNew structure allows easy browsing by token type:")
        print("  tokens/soldier/    - All soldier tokens")
        print("  tokens/zombie/     - All zombie tokens")
        print("  tokens/spirit/     - All spirit tokens")
        print("  etc.")


if __name__ == "__main__":
    main()
