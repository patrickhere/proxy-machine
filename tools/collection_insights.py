#!/usr/bin/env python3
"""Collection Insights Tool.

Analyzes collection composition and provides statistics:
- Total cards by type
- Set distribution
- Art type breakdown
- Language distribution
- Disk usage
"""

import sys
from collections import Counter
from pathlib import Path
from typing import Dict

# Color codes
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def analyze_directory(directory: Path) -> Dict:
    """Analyze a single directory for card statistics."""
    stats = {
        "total_files": 0,
        "total_size_mb": 0,
        "sets": Counter(),
        "art_types": Counter(),
        "languages": Counter(),
    }

    if not directory.exists():
        return stats

    for file in directory.rglob("*.png"):
        stats["total_files"] += 1
        stats["total_size_mb"] += file.stat().st_size / (1024 * 1024)

        # Parse filename for metadata
        stem = file.stem
        parts = stem.split("-")

        # Try to extract set code (usually last part before collector number)
        if len(parts) >= 2:
            # Art type is usually second-to-last or third-to-last
            potential_art_type = parts[-2] if len(parts) > 2 else "unknown"
            if potential_art_type in [
                "standard",
                "fullart",
                "showcase",
                "borderless",
                "extended",
                "retro",
                "textless",
            ]:
                stats["art_types"][potential_art_type] += 1

            # Language code (usually 2 letters)
            for part in parts:
                if len(part) == 2 and part.isalpha():
                    stats["languages"][part] += 1
                    break

        # Extract set from parent directory name
        if file.parent.name != directory.name:
            stats["sets"][file.parent.name] += 1

    return stats


def print_collection_report(profile: str | None = None):
    """Generate and print collection insights report."""
    # Determine paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    shared_root = project_root.parent / "magic-the-gathering" / "shared"

    if not shared_root.exists():
        print(f"❌ Shared directory not found: {shared_root}")
        return 1

    print(f"\n{'='*60}")
    print(f"{BLUE} Collection Insights Report{RESET}")
    if profile:
        print(f"Profile: {profile}")
    print(f"{'='*60}\n")

    # Analyze each card type
    card_types = [
        ("Basic Lands", "basic-lands"),
        ("Non-Basic Lands", "non-basic-lands"),
        ("Tokens", "tokens"),
        ("Creatures", "creatures"),
        ("Enchantments", "enchantments"),
        ("Artifacts", "artifacts"),
        ("Instants", "instants"),
        ("Sorceries", "sorceries"),
        ("Planeswalkers", "planeswalkers"),
    ]

    total_files = 0
    total_size_mb = 0
    all_sets = Counter()
    all_art_types = Counter()
    all_languages = Counter()

    print(f"{YELLOW}Card Type Breakdown:{RESET}")
    print(f"{'─'*60}")

    for display_name, dir_name in card_types:
        directory = shared_root / dir_name
        stats = analyze_directory(directory)

        if stats["total_files"] > 0:
            print(
                f"  {display_name:20s}: {stats['total_files']:>6,} cards ({stats['total_size_mb']:>7.1f} MB)"
            )
            total_files += stats["total_files"]
            total_size_mb += stats["total_size_mb"]
            all_sets.update(stats["sets"])
            all_art_types.update(stats["art_types"])
            all_languages.update(stats["languages"])

    print(f"{'─'*60}")
    print(f"  {'Total':20s}: {total_files:>6,} cards ({total_size_mb:>7.1f} MB)")
    print()

    # Top sets
    if all_sets:
        print(f"{YELLOW}Top 10 Sets:{RESET}")
        print(f"{'─'*60}")
        for set_code, count in all_sets.most_common(10):
            print(f"  {set_code.upper():8s}: {count:>6,} cards")
        print()

    # Art type distribution
    if all_art_types:
        print(f"{YELLOW}Art Type Distribution:{RESET}")
        print(f"{'─'*60}")
        for art_type, count in all_art_types.most_common():
            pct = (count / total_files * 100) if total_files > 0 else 0
            print(f"  {art_type.capitalize():15s}: {count:>6,} ({pct:>5.1f}%)")
        print()

    # Language distribution
    if all_languages:
        print(f"{YELLOW}Language Distribution:{RESET}")
        print(f"{'─'*60}")
        for lang, count in all_languages.most_common(10):
            pct = (count / total_files * 100) if total_files > 0 else 0
            print(f"  {lang.upper():8s}: {count:>6,} ({pct:>5.1f}%)")
        print()

    # Disk usage summary
    print(f"{YELLOW}Storage Summary:{RESET}")
    print(f"{'─'*60}")
    print(f"  Total Size: {total_size_mb:,.1f} MB ({total_size_mb/1024:.2f} GB)")
    print(
        f"  Average per card: {total_size_mb/total_files:.2f} MB"
        if total_files > 0
        else "  No cards"
    )
    print()

    print(f"{'='*60}")
    print(f"{GREEN}✓ Report complete{RESET}\n")

    return 0


def main():
    """Main entry point."""
    profile = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        profile = sys.argv[1]

    return print_collection_report(profile)


if __name__ == "__main__":
    sys.exit(main())
