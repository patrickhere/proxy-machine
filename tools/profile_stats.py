#!/usr/bin/env python3
"""Profile statistics dashboard.

Generates comprehensive statistics for a profile including:
- Card counts by type
- Set distribution
- Color distribution
- Rarity breakdown
- Storage usage
- Token coverage
"""

import sys
from pathlib import Path
from collections import Counter
import json


def get_profile_paths(profile_name: str) -> dict:
    """Get all paths for a profile."""
    base = Path(f"profiles/{profile_name}")
    return {
        "base": base,
        "front": base / "pictures-of-cards" / "front",
        "back": base / "pictures-of-cards" / "back",
        "double_sided": base / "pictures-of-cards" / "double-sided",
        "to_print": base / "pictures-of-cards" / "to-print",
    }


def count_files_by_extension(directory: Path) -> dict:
    """Count files by extension in a directory."""
    if not directory.exists():
        return {}

    counts = Counter()
    for file in directory.rglob("*"):
        if file.is_file():
            counts[file.suffix.lower()] += 1
    return dict(counts)


def get_directory_size(directory: Path) -> int:
    """Get total size of directory in bytes."""
    if not directory.exists():
        return 0

    total = 0
    for file in directory.rglob("*"):
        if file.is_file():
            total += file.stat().st_size
    return total


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def analyze_card_files(directory: Path) -> dict:
    """Analyze card files in a directory."""
    if not directory.exists():
        return {"total": 0, "by_set": {}, "by_type": {}}

    by_set = Counter()
    by_type = Counter()
    total = 0

    for file in directory.rglob("*.jpg"):
        total += 1
        # Try to extract set code from filename
        # Common patterns: cardname_set.jpg, cardname-set-123.jpg
        parts = file.stem.split("_")
        if len(parts) >= 2:
            set_code = parts[-1].split("-")[0]
            if len(set_code) <= 5:  # Reasonable set code length
                by_set[set_code.upper()] += 1

    # Also check PNG files
    for file in directory.rglob("*.png"):
        total += 1
        parts = file.stem.split("_")
        if len(parts) >= 2:
            set_code = parts[-1].split("-")[0]
            if len(set_code) <= 5:
                by_set[set_code.upper()] += 1

    return {
        "total": total,
        "by_set": dict(by_set.most_common(10)),  # Top 10 sets
        "by_type": dict(by_type),
    }


def generate_profile_stats(profile_name: str) -> dict:
    """Generate comprehensive statistics for a profile."""
    paths = get_profile_paths(profile_name)

    stats = {
        "profile": profile_name,
        "exists": paths["base"].exists(),
        "cards": {},
        "storage": {},
        "files": {},
    }

    if not stats["exists"]:
        return stats

    # Card statistics
    stats["cards"]["front"] = analyze_card_files(paths["front"])
    stats["cards"]["back"] = analyze_card_files(paths["back"])
    stats["cards"]["double_sided"] = analyze_card_files(paths["double_sided"])
    stats["cards"]["to_print"] = analyze_card_files(paths["to_print"])

    # Total cards
    stats["cards"]["total"] = sum(
        stats["cards"][key]["total"]
        for key in ["front", "back", "double_sided", "to_print"]
    )

    # Storage statistics
    for key, path in paths.items():
        if key != "base":
            stats["storage"][key] = {
                "bytes": get_directory_size(path),
                "formatted": format_bytes(get_directory_size(path)),
            }

    stats["storage"]["total"] = {
        "bytes": sum(
            s["bytes"] for s in stats["storage"].values() if isinstance(s, dict)
        ),
        "formatted": format_bytes(
            sum(s["bytes"] for s in stats["storage"].values() if isinstance(s, dict))
        ),
    }

    # File type statistics
    stats["files"] = count_files_by_extension(paths["base"])

    return stats


def print_profile_stats(stats: dict):
    """Print profile statistics in a formatted way."""
    print("\n" + "=" * 70)
    print(f"  PROFILE STATISTICS: {stats['profile']}")
    print("=" * 70)

    if not stats["exists"]:
        print("\n[ERROR] Profile does not exist")
        return

    # Card statistics
    print("\n[CARDS]")
    print(f"  Total cards: {stats['cards']['total']:,}")
    print(f"  Front faces: {stats['cards']['front']['total']:,}")
    print(f"  Back faces: {stats['cards']['back']['total']:,}")
    print(f"  Double-sided: {stats['cards']['double_sided']['total']:,}")
    print(f"  To print: {stats['cards']['to_print']['total']:,}")

    # Top sets
    if stats["cards"]["front"]["by_set"]:
        print("\n[TOP SETS - Front]")
        for set_code, count in list(stats["cards"]["front"]["by_set"].items())[:5]:
            print(f"  {set_code}: {count:,} cards")

    # Storage statistics
    print("\n[STORAGE]")
    print(f"  Total: {stats['storage']['total']['formatted']}")
    print(f"  Front: {stats['storage']['front']['formatted']}")
    print(f"  Back: {stats['storage']['back']['formatted']}")
    print(f"  Double-sided: {stats['storage']['double_sided']['formatted']}")
    print(f"  To print: {stats['storage']['to_print']['formatted']}")

    # File types
    if stats["files"]:
        print("\n[FILE TYPES]")
        for ext, count in sorted(
            stats["files"].items(), key=lambda x: x[1], reverse=True
        )[:5]:
            print(f"  {ext or 'no extension'}: {count:,} files")

    print("\n" + "=" * 70)


def export_stats_json(stats: dict, output_file: str):
    """Export statistics to JSON file."""
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n[OK] Statistics exported to: {output_file}")


def compare_profiles(profile1: str, profile2: str):
    """Compare statistics between two profiles."""
    stats1 = generate_profile_stats(profile1)
    stats2 = generate_profile_stats(profile2)

    print("\n" + "=" * 70)
    print(f"  PROFILE COMPARISON: {profile1} vs {profile2}")
    print("=" * 70)

    print(f"\n{'Metric':<30} {profile1:<20} {profile2:<20}")
    print("-" * 70)
    print(
        f"{'Total cards':<30} {stats1['cards']['total']:<20,} {stats2['cards']['total']:<20,}"
    )
    print(
        f"{'Storage':<30} {stats1['storage']['total']['formatted']:<20} {stats2['storage']['total']['formatted']:<20}"
    )
    print(
        f"{'Front faces':<30} {stats1['cards']['front']['total']:<20,} {stats2['cards']['front']['total']:<20,}"
    )
    print(
        f"{'Back faces':<30} {stats1['cards']['back']['total']:<20,} {stats2['cards']['back']['total']:<20,}"
    )
    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(
            "Usage: python profile_stats.py <profile_name> [--export <file>] [--compare <profile2>]"
        )
        print("\nExamples:")
        print("  python profile_stats.py patrick")
        print("  python profile_stats.py patrick --export stats.json")
        print("  python profile_stats.py patrick --compare elijah")
        return 1

    profile_name = sys.argv[1]

    # Check for export flag
    if "--export" in sys.argv:
        idx = sys.argv.index("--export")
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]
            stats = generate_profile_stats(profile_name)
            print_profile_stats(stats)
            export_stats_json(stats, output_file)
            return 0

    # Check for compare flag
    if "--compare" in sys.argv:
        idx = sys.argv.index("--compare")
        if idx + 1 < len(sys.argv):
            profile2 = sys.argv[idx + 1]
            compare_profiles(profile_name, profile2)
            return 0

    # Default: just print stats
    stats = generate_profile_stats(profile_name)
    print_profile_stats(stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())
