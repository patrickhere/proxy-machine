#!/usr/bin/env python3
"""Asset sync helpers for shared libraries (tokens, lands, card backs)."""

import os
import shutil
import hashlib
from pathlib import Path

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SHARED_ROOT = os.path.join(PROJECT_ROOT, "magic-the-gathering", "shared")


def get_file_hash(filepath: Path) -> str:
    """Get MD5 hash of a file for duplicate detection."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def sync_shared_assets(
    source_dir: str,
    target_dir: str,
    *,
    dry_run: bool = False,
    skip_duplicates: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Sync assets from source to target directory.

    Args:
        source_dir: Source directory path
        target_dir: Target directory path
        dry_run: If True, show what would be synced without actually syncing
        skip_duplicates: If True, skip files that already exist with same hash
        verbose: If True, show detailed progress

    Returns:
        Dictionary with sync statistics
    """
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    if not source_path.exists():
        return {"error": f"Source directory not found: {source_dir}"}

    # Create target directory if it doesn't exist
    if not dry_run and not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    stats = {
        "copied": 0,
        "skipped": 0,
        "errors": 0,
        "total_size": 0,
    }

    # Get all files in source
    files = list(source_path.rglob("*"))
    files = [f for f in files if f.is_file()]

    for source_file in files:
        # Get relative path
        rel_path = source_file.relative_to(source_path)
        target_file = target_path / rel_path

        # Check if file already exists
        if target_file.exists():
            if skip_duplicates:
                # Compare hashes
                source_hash = get_file_hash(source_file)
                target_hash = get_file_hash(target_file)

                if source_hash == target_hash:
                    stats["skipped"] += 1
                    if verbose:
                        print(f"  ⏭️  Skipped (duplicate): {rel_path}")
                    continue

        # Copy file
        if dry_run:
            print(f"  [DRY RUN] Would copy: {rel_path}")
            stats["copied"] += 1
        else:
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)
                stats["copied"] += 1
                stats["total_size"] += source_file.stat().st_size
                if verbose:
                    print(f"  ✓ Copied: {rel_path}")
            except Exception as e:
                stats["errors"] += 1
                print(f"  ✗ Error copying {rel_path}: {e}")

    return stats


def sync_tokens_to_profile(
    profile_name: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Sync shared tokens to a specific profile.

    Args:
        profile_name: Name of the profile
        dry_run: If True, show what would be synced
        verbose: If True, show detailed progress

    Returns:
        Dictionary with sync statistics
    """
    shared_tokens = os.path.join(SHARED_ROOT, "tokens")
    profile_tokens = os.path.join(
        PROJECT_ROOT, "magic-the-gathering", "proxied-decks", profile_name, "tokens"
    )

    print(f"\n🔄 Syncing tokens to profile '{profile_name}'...")
    print(f"   Source: {shared_tokens}")
    print(f"   Target: {profile_tokens}")

    stats = sync_shared_assets(
        shared_tokens,
        profile_tokens,
        dry_run=dry_run,
        skip_duplicates=True,
        verbose=verbose,
    )

    if "error" not in stats:
        print("\n✓ Sync complete!")
        print(f"   Copied: {stats['copied']} files")
        print(f"   Skipped: {stats['skipped']} duplicates")
        if stats["errors"] > 0:
            print(f"   Errors: {stats['errors']}")
        if not dry_run and stats["total_size"] > 0:
            size_mb = stats["total_size"] / (1024 * 1024)
            print(f"   Total size: {size_mb:.1f} MB")

    return stats


def sync_lands_to_profile(
    profile_name: str,
    land_type: str = "all",
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Sync shared lands to a specific profile.

    Args:
        profile_name: Name of the profile
        land_type: Type of lands to sync (basic, nonbasic, all)
        dry_run: If True, show what would be synced
        verbose: If True, show detailed progress

    Returns:
        Dictionary with sync statistics
    """
    profile_lands = os.path.join(
        PROJECT_ROOT, "magic-the-gathering", "proxied-decks", profile_name, "lands"
    )

    stats = {"copied": 0, "skipped": 0, "errors": 0, "total_size": 0}

    if land_type in ("basic", "all"):
        shared_basic = os.path.join(SHARED_ROOT, "basic-lands")
        print(f"\n🔄 Syncing basic lands to profile '{profile_name}'...")

        basic_stats = sync_shared_assets(
            shared_basic,
            os.path.join(profile_lands, "basic"),
            dry_run=dry_run,
            skip_duplicates=True,
            verbose=verbose,
        )

        if "error" not in basic_stats:
            for key in stats:
                stats[key] += basic_stats[key]

    if land_type in ("nonbasic", "all"):
        shared_nonbasic = os.path.join(SHARED_ROOT, "non-basic-lands")
        print(f"\n🔄 Syncing non-basic lands to profile '{profile_name}'...")

        nonbasic_stats = sync_shared_assets(
            shared_nonbasic,
            os.path.join(profile_lands, "nonbasic"),
            dry_run=dry_run,
            skip_duplicates=True,
            verbose=verbose,
        )

        if "error" not in nonbasic_stats:
            for key in stats:
                stats[key] += nonbasic_stats[key]

    if "error" not in stats:
        print("\n✓ Land sync complete!")
        print(f"   Copied: {stats['copied']} files")
        print(f"   Skipped: {stats['skipped']} duplicates")
        if stats["errors"] > 0:
            print(f"   Errors: {stats['errors']}")
        if not dry_run and stats["total_size"] > 0:
            size_mb = stats["total_size"] / (1024 * 1024)
            print(f"   Total size: {size_mb:.1f} MB")

    return stats


def list_profiles() -> list[str]:
    """List all available profiles."""
    proxied_decks = os.path.join(PROJECT_ROOT, "magic-the-gathering", "proxied-decks")

    if not os.path.exists(proxied_decks):
        return []

    profiles = []
    for item in os.listdir(proxied_decks):
        item_path = os.path.join(proxied_decks, item)
        if os.path.isdir(item_path):
            profiles.append(item)

    return sorted(profiles)


if __name__ == "__main__":
    import click

    @click.group()
    def cli():
        """Asset sync helpers for shared libraries."""
        pass

    @cli.command()
    @click.argument("profile")
    @click.option(
        "--dry-run", is_flag=True, help="Show what would be synced without syncing"
    )
    @click.option("--verbose", is_flag=True, help="Show detailed progress")
    def sync_tokens(profile, dry_run, verbose):
        """Sync shared tokens to a profile."""
        sync_tokens_to_profile(profile, dry_run=dry_run, verbose=verbose)

    @cli.command()
    @click.argument("profile")
    @click.option(
        "--type", "land_type", default="all", help="Land type: basic, nonbasic, all"
    )
    @click.option(
        "--dry-run", is_flag=True, help="Show what would be synced without syncing"
    )
    @click.option("--verbose", is_flag=True, help="Show detailed progress")
    def sync_lands(profile, land_type, dry_run, verbose):
        """Sync shared lands to a profile."""
        sync_lands_to_profile(profile, land_type, dry_run=dry_run, verbose=verbose)

    @cli.command()
    def profiles():
        """List all available profiles."""
        profile_list = list_profiles()

        if not profile_list:
            click.echo("No profiles found.")
            return

        click.echo("\n📁 Available Profiles:\n")
        for profile in profile_list:
            click.echo(f"  • {profile}")
        click.echo(f"\n✓ Found {len(profile_list)} profiles")

    cli()
