#!/usr/bin/env python3
"""
Reorganize card library from set-based to type-based organization.

Current structure: cards/<set>/<cardname>-<arttype>-<lang>-<set>.png
Target structure:  <cardtype>/<cardname>-<arttype>-<lang>-<set>.png

This groups all cards by their type (creatures, planeswalkers, artifacts, etc.)
regardless of set, making it easier to browse by card type.

Usage:
  python tools/reorganize_cards.py --dry-run  # Preview changes
  python tools/reorganize_cards.py            # Apply changes
"""

import argparse
import shutil
import sys
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from db.bulk_index import query_cards
except ImportError:
    query_cards = None


def extract_card_info(filename: str) -> Optional[Dict[str, str]]:
    """
    Extract card information from filename.

    Format: <cardname>-<arttype>-<lang>-<set>.png
    Example: lightning-bolt-standard-en-lea.png
    """
    stem = Path(filename).stem
    parts = stem.split("-")

    if len(parts) < 4:
        return None

    # Last part is set code
    set_code = parts[-1].lower()
    # Second to last is language
    lang = parts[-2].lower()
    # Third to last is art type
    art_type = parts[-3].lower()
    # Everything else is card name
    card_name = "-".join(parts[:-3])

    return {
        "name": card_name,
        "art_type": art_type,
        "lang": lang,
        "set": set_code,
        "stem": stem,
    }


def classify_card_type(card_name: str, set_code: str) -> str:
    """
    Classify card type from database or filename heuristics.

    Returns: creatures, planeswalkers, artifacts, enchantments, instants, sorceries, or other
    """
    # Try database lookup first (works even with "misc" set code)
    if query_cards:
        try:
            # Try exact name match first
            results = query_cards(
                name_filter=card_name.replace("-", " "),
                set_filter=None if set_code == "misc" else set_code,
                limit=1,
            )
            if results:
                type_line = results[0].get("type_line", "").lower()

                # Check primary types (order matters - creature artifacts should be creatures)
                if "creature" in type_line:
                    return "creatures"
                elif "planeswalker" in type_line:
                    return "planeswalkers"
                elif "instant" in type_line:
                    return "instants"
                elif "sorcery" in type_line:
                    return "sorceries"
                elif "artifact" in type_line:
                    return "artifacts"
                elif "enchantment" in type_line:
                    return "enchantments"
                elif "land" in type_line:
                    return "lands"
        except Exception:
            pass

    # Enhanced filename heuristics
    name_lower = card_name.lower()

    # Planeswalker indicators (check first - very specific)
    if any(
        word in name_lower
        for word in [
            "planeswalker",
            "jace",
            "chandra",
            "liliana",
            "garruk",
            "nissa",
            "ajani",
            "gideon",
            "teferi",
            "vraska",
            "karn",
            "ugin",
            "sorin",
            "elspeth",
            "nahiri",
            "tamiyo",
            "saheeli",
            "tezzeret",
            "ob",
            "nixilis",
            "ashiok",
            "domri",
            "kiora",
            "sarkhan",
            "narset",
            "vivien",
            "ral",
            "zarek",
            "angrath",
            "huatli",
            "kaya",
            "dovin",
            "baan",
            "kasmina",
            "rowan",
            "will",
            "kenrith",
            "lukka",
            "basri",
            "ket",
        ]
    ):
        return "planeswalkers"

    # Creature indicators
    creature_words = [
        "dragon",
        "knight",
        "wizard",
        "goblin",
        "elf",
        "angel",
        "demon",
        "beast",
        "zombie",
        "vampire",
        "merfolk",
        "soldier",
        "warrior",
        "shaman",
        "cleric",
        "rogue",
        "assassin",
        "berserker",
        "druid",
        "monk",
        "artificer",
        "advisor",
        "elemental",
        "spirit",
        "avatar",
        "hydra",
        "sphinx",
        "djinn",
        "giant",
        "troll",
        "orc",
        "faerie",
        "kithkin",
        "human",
        "dwarf",
        "cat",
        "dog",
        "bird",
        "snake",
        "wurm",
        "kraken",
        "leviathan",
        "octopus",
        "crab",
        "fish",
        "whale",
        "shark",
    ]
    if any(word in name_lower for word in creature_words):
        return "creatures"

    # Instant/Sorcery indicators
    if any(
        word in name_lower
        for word in [
            "bolt",
            "blast",
            "shock",
            "burn",
            "counter",
            "spell",
            "charm",
            "command",
            "ritual",
            "strike",
            "ray",
            "beam",
            "fire",
            "lightning",
            "thunder",
            "storm",
        ]
    ):
        # Distinguish instant vs sorcery by common patterns
        if any(
            word in name_lower
            for word in ["ritual", "wrath", "damnation", "rampant", "growth"]
        ):
            return "sorceries"
        return "instants"

    # Artifact indicators
    if any(
        word in name_lower
        for word in [
            "sword",
            "staff",
            "ring",
            "crown",
            "throne",
            "chalice",
            "orb",
            "mirror",
            "lens",
            "prism",
            "mox",
            "lotus",
            "vault",
            "chest",
            "golem",
            "construct",
            "myr",
        ]
    ):
        return "artifacts"

    # Enchantment indicators
    if any(
        word in name_lower
        for word in [
            "aura",
            "curse",
            "blessing",
            "oath",
            "pact",
            "ascendancy",
            "dominance",
            "presence",
            "leyline",
        ]
    ):
        return "enchantments"

    # Default to other
    return "other"


def main():
    parser = argparse.ArgumentParser(
        description="Reorganize cards from set-based to type-based structure"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without moving files"
    )
    parser.add_argument(
        "--cards-dir",
        default=None,
        help="Path to cards directory (default: auto-detect)",
    )
    args = parser.parse_args()

    # Find cards directory
    if args.cards_dir:
        cards_root = Path(args.cards_dir)
    else:
        # Auto-detect from project structure
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        cards_root = project_root / "magic-the-gathering" / "shared" / "cards"

    if not cards_root.exists():
        print(f"Error: Cards directory not found: {cards_root}")
        return 1

    print("=" * 70)
    print("Card Library Reorganization Tool")
    print("=" * 70)
    print()
    print("Current: cards/<set>/<cardname>-<arttype>-<lang>-<set>.png")
    print("Target:  <cardtype>/<cardname>-<arttype>-<lang>-<set>.png")
    print("=" * 70)
    print()

    if args.dry_run:
        print("[DRY RUN MODE] No files will be modified")
        print()

    # Scan cards directory
    print(f"Scanning cards directory: {cards_root}")
    print("=" * 70)

    moves: List[Tuple[Path, Path, str]] = []
    parse_errors = 0
    type_counts: Dict[str, int] = defaultdict(int)

    for set_dir in sorted(cards_root.iterdir()):
        if not set_dir.is_dir() or set_dir.name.startswith("."):
            continue

        # Handle both flat structure (set/file.png) and nested (set/cardname/file.png)
        for item in sorted(set_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }:
                files_to_process = [item]
            elif item.is_dir():
                # Nested directory (split/adventure cards)
                files_to_process = [
                    f
                    for f in item.iterdir()
                    if f.is_file()
                    and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                ]
            else:
                continue

            for file in files_to_process:
                # Parse filename
                info = extract_card_info(file.name)
                if not info:
                    parse_errors += 1
                    continue

                # Classify card type
                card_type = classify_card_type(info["name"], info["set"])
                type_counts[card_type] += 1
            info = extract_card_info(file.name)
            if not info:
                parse_errors += 1
                continue

            # Classify card type
            card_type = classify_card_type(info["name"], info["set"])
            type_counts[card_type] += 1

            # Determine new location
            type_dir = cards_root.parent / card_type
            new_path = type_dir / file.name

            moves.append((file, new_path, card_type))

    print(f"Found {len(moves)} card files to reorganize")
    print()
    print(f"Card types found: {len(type_counts)}")
    print(f"Parse errors: {parse_errors}")
    print()

    # Show top card types
    print("Top card types:")
    for card_type, count in sorted(
        type_counts.items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {card_type:20s} {count:4d} cards")
    print()

    if args.dry_run:
        print("=" * 70)
        print("[DRY RUN] Preview of directory structure:")
        print()
        for card_type in sorted(type_counts.keys()):
            print(f"  {card_type}/ ({type_counts[card_type]} cards)")
        print()
        print(f"Total: {len(moves)} files would be moved")
        return 0

    # Execute moves
    print("=" * 70)
    print("Reorganizing cards...")
    print()

    moved_count = 0
    for old_path, new_path, card_type in moves:
        # Create type directory
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # Move file
        shutil.move(str(old_path), str(new_path))
        moved_count += 1

    # Clean up empty set directories
    print()
    print("Cleaning up old set directories...")
    removed_dirs = 0
    for set_dir in cards_root.iterdir():
        if set_dir.is_dir() and not any(set_dir.iterdir()):
            set_dir.rmdir()
            removed_dirs += 1

    print(f"Removed {removed_dirs} empty directories")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Moved: {moved_count} files")
    print()
    print("Reorganization complete!")
    print()
    print("New structure allows easy browsing by card type:")
    for card_type in sorted(type_counts.keys()):
        print(f"  {card_type}/    - All {card_type}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
