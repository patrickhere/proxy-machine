#!/usr/bin/env python3
"""Query and analyze card relationships from the database.

This tool provides various queries for analyzing card relationships
tracked in the card_relationships table.
"""

import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.card_types import DBColumns, CardRelationshipColumns, RelationshipType

DB_PATH = (
    Path(__file__).parent.parent.parent
    / "magic-the-gathering"
    / "bulk-data"
    / "bulk.db"
)


def get_relationship_stats(db_path: Path = DB_PATH) -> Dict[str, int]:
    """Get statistics on relationship types.

    Returns:
        Dict mapping relationship type to count
    """
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT {CardRelationshipColumns.RELATIONSHIP_TYPE}, COUNT(*)
        FROM card_relationships
        GROUP BY {CardRelationshipColumns.RELATIONSHIP_TYPE}
        ORDER BY COUNT(*) DESC
    """
    )

    stats = dict(cur.fetchall())
    conn.close()
    return stats


def find_meld_pairs(db_path: Path = DB_PATH) -> List[Tuple[str, str, str]]:
    """Find all meld card pairs.

    Returns:
        List of (card1_name, card2_name, result_name) tuples
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Find meld parts and their results
    cur.execute(
        f"""
        SELECT DISTINCT
            p1.{DBColumns.NAME} as part1,
            p2.{DBColumns.NAME} as part2,
            r.{CardRelationshipColumns.RELATED_CARD_NAME} as result
        FROM card_relationships r1
        JOIN card_relationships r2 ON r1.{CardRelationshipColumns.SOURCE_CARD_ID} = r2.{CardRelationshipColumns.SOURCE_CARD_ID}
        JOIN prints p1 ON r1.{CardRelationshipColumns.SOURCE_CARD_ID} = p1.{DBColumns.ID}
        JOIN prints p2 ON r2.{CardRelationshipColumns.RELATED_CARD_ID} = p2.{DBColumns.ID}
        JOIN card_relationships r ON r1.{CardRelationshipColumns.SOURCE_CARD_ID} = r.{CardRelationshipColumns.SOURCE_CARD_ID}
        WHERE r1.{CardRelationshipColumns.RELATIONSHIP_TYPE} = ?
        AND r2.{CardRelationshipColumns.RELATIONSHIP_TYPE} = ?
        AND r.{CardRelationshipColumns.RELATIONSHIP_TYPE} = ?
        AND r1.{CardRelationshipColumns.RELATED_CARD_ID} != r2.{CardRelationshipColumns.RELATED_CARD_ID}
        LIMIT 100
    """,
        (
            RelationshipType.MELD_PART,
            RelationshipType.MELD_PART,
            RelationshipType.MELD_RESULT,
        ),
    )

    results = cur.fetchall()
    conn.close()
    return results


def find_mdfc_cards(
    set_code: Optional[str] = None, db_path: Path = DB_PATH
) -> List[Tuple[str, str, str]]:
    """Find all MDFC (Modal Double-Faced Card) pairs.

    Args:
        set_code: Optional set code filter

    Returns:
        List of (front_face, back_face, set_code) tuples
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    query = f"""
        SELECT DISTINCT
            p.{DBColumns.NAME} as source,
            r.{CardRelationshipColumns.RELATED_CARD_NAME} as related,
            p.{DBColumns.SET_CODE}
        FROM card_relationships r
        JOIN prints p ON r.{CardRelationshipColumns.SOURCE_CARD_ID} = p.{DBColumns.ID}
        WHERE r.{CardRelationshipColumns.RELATIONSHIP_TYPE} = ?
        AND p.{DBColumns.LAYOUT} IN ('modal_dfc', 'transform', 'reversible_card')
    """

    params = [RelationshipType.COMBO_PIECE]

    if set_code:
        query += f" AND p.{DBColumns.SET_CODE} = ?"
        params.append(set_code.lower())

    query += " ORDER BY p.{DBColumns.NAME} LIMIT 100"

    cur.execute(query, params)
    results = cur.fetchall()
    conn.close()
    return results


def find_token_producers(
    token_name: str, db_path: Path = DB_PATH
) -> List[Tuple[str, str, str]]:
    """Find all cards that produce a specific token.

    Args:
        token_name: Name of the token to search for

    Returns:
        List of (card_name, set_code, rarity) tuples
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT DISTINCT
            p.{DBColumns.NAME},
            p.{DBColumns.SET_CODE},
            p.{DBColumns.RARITY}
        FROM card_relationships r
        JOIN prints p ON r.{CardRelationshipColumns.SOURCE_CARD_ID} = p.{DBColumns.ID}
        WHERE r.{CardRelationshipColumns.RELATIONSHIP_TYPE} = ?
        AND LOWER(r.{CardRelationshipColumns.RELATED_CARD_NAME}) LIKE ?
        ORDER BY p.{DBColumns.NAME}
        LIMIT 100
    """,
        (RelationshipType.TOKEN, f"%{token_name.lower()}%"),
    )

    results = cur.fetchall()
    conn.close()
    return results


def find_card_relationships(
    card_name: str, db_path: Path = DB_PATH
) -> Dict[str, List[str]]:
    """Find all relationships for a specific card.

    Args:
        card_name: Name of the card to search for

    Returns:
        Dict mapping relationship type to list of related card names
    """
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT
            r.{CardRelationshipColumns.RELATIONSHIP_TYPE},
            r.{CardRelationshipColumns.RELATED_CARD_NAME}
        FROM card_relationships r
        JOIN prints p ON r.{CardRelationshipColumns.SOURCE_CARD_ID} = p.{DBColumns.ID}
        WHERE LOWER(p.{DBColumns.NAME}) = ?
        ORDER BY r.{CardRelationshipColumns.RELATIONSHIP_TYPE}
    """,
        (card_name.lower(),),
    )

    results = {}
    for rel_type, related_name in cur.fetchall():
        if rel_type not in results:
            results[rel_type] = []
        results[rel_type].append(related_name)

    conn.close()
    return results


def find_sets_with_mdfcs(db_path: Path = DB_PATH) -> List[Tuple[str, str, int]]:
    """Find all sets that contain MDFC cards.

    Returns:
        List of (set_code, set_name, mdfc_count) tuples
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT
            p.{DBColumns.SET_CODE},
            p.{DBColumns.SET_NAME},
            COUNT(DISTINCT p.{DBColumns.ID}) as mdfc_count
        FROM card_relationships r
        JOIN prints p ON r.{CardRelationshipColumns.SOURCE_CARD_ID} = p.{DBColumns.ID}
        WHERE r.{CardRelationshipColumns.RELATIONSHIP_TYPE} = ?
        AND p.{DBColumns.LAYOUT} IN ('modal_dfc', 'transform', 'reversible_card')
        GROUP BY p.{DBColumns.SET_CODE}, p.{DBColumns.SET_NAME}
        ORDER BY mdfc_count DESC
        LIMIT 50
    """,
        (RelationshipType.COMBO_PIECE,),
    )

    results = cur.fetchall()
    conn.close()
    return results


def main():
    """CLI interface for relationship queries."""
    import argparse

    parser = argparse.ArgumentParser(description="Query card relationships")
    parser.add_argument(
        "--stats", action="store_true", help="Show relationship statistics"
    )
    parser.add_argument(
        "--meld-pairs", action="store_true", help="List meld card pairs"
    )
    parser.add_argument(
        "--mdfcs",
        metavar="SET",
        nargs="?",
        const="",
        help="List MDFC cards (optionally filtered by set)",
    )
    parser.add_argument(
        "--token-producers", metavar="TOKEN", help="Find cards that produce a token"
    )
    parser.add_argument(
        "--card", metavar="NAME", help="Show all relationships for a card"
    )
    parser.add_argument(
        "--mdfc-sets", action="store_true", help="List sets with MDFC cards"
    )

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        print("Run 'make bulk-index-rebuild' to create it.")
        sys.exit(1)

    if args.stats:
        print("Relationship Statistics")
        print("=" * 60)
        stats = get_relationship_stats()
        total = sum(stats.values())
        for rel_type, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {rel_type:20s}: {count:6,d} ({pct:5.1f}%)")
        print(f"  {'TOTAL':20s}: {total:6,d}")

    elif args.meld_pairs:
        print("Meld Card Pairs")
        print("=" * 60)
        pairs = find_meld_pairs()
        for part1, part2, result in pairs:
            print(f"  {part1} + {part2} -> {result}")
        print(f"\nFound {len(pairs)} meld pairs")

    elif args.mdfcs is not None:
        set_filter = args.mdfcs if args.mdfcs else None
        title = f"MDFC Cards in {set_filter.upper()}" if set_filter else "MDFC Cards"
        print(title)
        print("=" * 60)
        mdfcs = find_mdfc_cards(set_filter)
        for front, back, set_code in mdfcs:
            print(f"  [{set_code.upper()}] {front} // {back}")
        print(f"\nFound {len(mdfcs)} MDFC cards")

    elif args.token_producers:
        print(f"Cards that produce '{args.token_producers}' tokens")
        print("=" * 60)
        producers = find_token_producers(args.token_producers)
        for card_name, set_code, rarity in producers:
            print(f"  [{set_code.upper()}] {card_name} ({rarity})")
        print(f"\nFound {len(producers)} cards")

    elif args.card:
        print(f"Relationships for '{args.card}'")
        print("=" * 60)
        relationships = find_card_relationships(args.card)
        if not relationships:
            print("  No relationships found")
        else:
            for rel_type, related_cards in relationships.items():
                print(f"\n  {rel_type}:")
                for card in related_cards:
                    print(f"    - {card}")

    elif args.mdfc_sets:
        print("Sets with MDFC Cards")
        print("=" * 60)
        sets = find_sets_with_mdfcs()
        for set_code, set_name, count in sets:
            print(f"  [{set_code.upper():5s}] {set_name:40s} {count:3d} MDFCs")
        print(f"\nFound {len(sets)} sets with MDFCs")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
