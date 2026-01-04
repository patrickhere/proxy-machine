#!/usr/bin/env python3
"""Card Relationship Resolver using all_parts.

Resolves related cards (DFC faces, meld pairs, tokens, etc.) from all_parts field.
Can be used to enhance any fetch operation to include all related components.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Set

# Color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def get_database_path() -> Path:
    """Get path to bulk database."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root.parent / "magic-the-gathering" / "bulk-data" / "bulk.db"
    return db_path


def resolve_all_parts(
    card_ids: List[str], db_path: Path, include_tokens: bool = False
) -> Dict[str, List[Dict]]:
    """
    Resolve all related cards from all_parts field.

    Args:
        card_ids: List of card IDs to resolve
        db_path: Path to database
        include_tokens: Whether to include token components

    Returns:
        Dict mapping card_id -> list of related card dicts
    """
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    relationships = {}

    for card_id in card_ids:
        # Get the card's all_parts field
        cursor.execute("SELECT all_parts FROM prints WHERE id = ?", (card_id,))
        result = cursor.fetchone()

        if not result or not result[0]:
            continue

        try:
            all_parts = json.loads(result[0])
        except json.JSONDecodeError:
            continue

        if not isinstance(all_parts, list):
            continue

        related_cards = []

        for part in all_parts:
            if not isinstance(part, dict):
                continue

            component = part.get("component", "")
            part_id = part.get("id")
            part_name = part.get("name", "")

            # Skip tokens unless explicitly requested
            if component == "token" and not include_tokens:
                continue

            # Skip the card itself
            if part_id == card_id:
                continue

            related_cards.append(
                {
                    "id": part_id,
                    "name": part_name,
                    "component": component,
                    "uri": part.get("uri", ""),
                }
            )

        if related_cards:
            relationships[card_id] = related_cards

    conn.close()
    return relationships


def expand_card_list_with_relationships(
    card_ids: List[str],
    db_path: Path,
    include_tokens: bool = False,
    verbose: bool = False,
) -> Set[str]:
    """
    Expand a list of card IDs to include all related cards.

    Args:
        card_ids: Initial list of card IDs
        db_path: Path to database
        include_tokens: Whether to include tokens
        verbose: Print expansion details

    Returns:
        Set of all card IDs (original + related)
    """
    expanded = set(card_ids)
    relationships = resolve_all_parts(card_ids, db_path, include_tokens)

    for card_id, related in relationships.items():
        for rel in related:
            expanded.add(rel["id"])

    if verbose and relationships:
        print(
            f"Expanded from {len(card_ids)} to {len(expanded)} cards (+{len(expanded) - len(card_ids)})"
        )
        print()

    return expanded


def get_mdfc_lands(db_path: Path) -> List[Dict]:
    """
    Find all MDFCs where ANY face is a land.
    This catches cards where front is a spell but back is a land.

    Returns:
        List of card dicts with both faces
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Find cards with all_parts that have a land component
    cursor.execute(
        """
        SELECT DISTINCT p.id, p.name, p.all_parts, p.type_line
        FROM prints p
        WHERE p.all_parts IS NOT NULL
        AND p.all_parts != '[]'
        AND p.layout IN ('modal_dfc', 'transform', 'reversible_card')
    """
    )

    results = cursor.fetchall()
    mdfc_lands = []

    for card_id, name, all_parts_json, type_line in results:
        try:
            all_parts = json.loads(all_parts_json)
        except json.JSONDecodeError:
            continue

        # Check if any part is a land
        has_land_face = False
        for part in all_parts:
            if isinstance(part, dict):
                # Check component type or query the actual card
                part_id = part.get("id")
                if part_id:
                    cursor.execute(
                        "SELECT type_line FROM prints WHERE id = ?", (part_id,)
                    )
                    part_result = cursor.fetchone()
                    if part_result and "land" in part_result[0].lower():
                        has_land_face = True
                        break

        if has_land_face:
            mdfc_lands.append(
                {
                    "id": card_id,
                    "name": name,
                    "type_line": type_line,
                    "all_parts": all_parts,
                }
            )

    conn.close()
    return mdfc_lands


def main():
    """Main entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Resolve card relationships from all_parts"
    )
    parser.add_argument(
        "--test-mdfc-lands", action="store_true", help="Find all MDFC lands"
    )
    parser.add_argument(
        "--card-id", help="Test relationship resolution for a specific card ID"
    )
    parser.add_argument(
        "--include-tokens", action="store_true", help="Include tokens in relationships"
    )

    args = parser.parse_args()

    db_path = get_database_path()

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    if args.test_mdfc_lands:
        print("\nFinding all MDFC lands...")
        print("=" * 60)
        mdfc_lands = get_mdfc_lands(db_path)
        print(f"Found {len(mdfc_lands)} MDFCs with land faces:")
        for card in mdfc_lands[:20]:  # Show first 20
            print(f"  {card['name']} - {card['type_line']}")
        if len(mdfc_lands) > 20:
            print(f"  ... and {len(mdfc_lands) - 20} more")

    elif args.card_id:
        print(f"\nResolving relationships for card ID: {args.card_id}")
        print("=" * 60)
        relationships = resolve_all_parts([args.card_id], db_path, args.include_tokens)

        if args.card_id in relationships:
            print("Related cards:")
            for rel in relationships[args.card_id]:
                print(f"  - {rel['name']} ({rel['component']})")
        else:
            print("No related cards found")

    else:
        print("Usage:")
        print("  python resolve_card_relationships.py --test-mdfc-lands")
        print(
            "  python resolve_card_relationships.py --card-id <scryfall_id> [--include-tokens]"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
