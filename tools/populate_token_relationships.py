#!/usr/bin/env python3
"""Populate Token Relationships from all_parts Data.

Parses the all_parts field from cards and populates the created_tokens table
with relationships between cards and the tokens they create.
"""

import json
import sqlite3
import sys
from pathlib import Path

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


def populate_token_relationships(db_path: Path) -> int:
    """Extract token relationships from all_parts and populate created_tokens table."""
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print("\nPopulating token relationships from all_parts data...")
    print("=" * 60)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Clear existing relationships
    cursor.execute("DELETE FROM created_tokens")

    # Query all cards with all_parts data
    cursor.execute(
        """
        SELECT id, name, all_parts
        FROM prints
        WHERE all_parts IS NOT NULL AND all_parts != '[]'
    """
    )

    cards_with_parts = cursor.fetchall()
    print(f"Found {len(cards_with_parts):,} cards with all_parts data")

    relationships = []
    cards_processed = 0
    tokens_found = 0

    for card_id, card_name, all_parts_json in cards_with_parts:
        cards_processed += 1

        if cards_processed % 1000 == 0:
            print(f"  Processed {cards_processed:,} cards...")

        try:
            all_parts = json.loads(all_parts_json)
        except json.JSONDecodeError:
            continue

        if not isinstance(all_parts, list):
            continue

        # Look for token components
        for part in all_parts:
            if not isinstance(part, dict):
                continue

            component = part.get("component")
            part_id = part.get("id")
            part_name = part.get("name", "")

            # Check if this part is a token
            if component == "token" and part_id:
                relationships.append((card_id, part_id, "all_parts", 1.0))
                tokens_found += 1

    print(f"\n{YELLOW}Inserting relationships...{RESET}")
    cursor.executemany(
        "INSERT OR REPLACE INTO created_tokens (card_id, token_id, source, confidence) VALUES (?, ?, ?, ?)",
        relationships,
    )

    conn.commit()
    conn.close()

    print(f"\n{GREEN}Complete!{RESET}")
    print(f"Cards processed: {cards_processed:,}")
    print(f"Token relationships found: {tokens_found:,}")
    print(f"Unique card-token pairs: {len(relationships):,}")
    print()

    return 0


def main():
    """Main entry point."""
    db_path = get_database_path()
    return populate_token_relationships(db_path)


if __name__ == "__main__":
    sys.exit(main())
