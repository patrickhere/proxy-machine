#!/usr/bin/env python3
"""Advanced Token Pack Builder with Database Integration.

Analyzes decks using Scryfall database to:
- Auto-detect tokens from card oracle text
- Suggest quantities based on deck composition
- Integrate with deck analysis tools
- Query available token art from collection
"""

import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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


def extract_card_names(deck_content: str) -> List[str]:
    """Extract card names from deck file."""
    card_names = []

    for line in deck_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        # Remove quantity prefix (e.g., "4x" or "4 ")
        line = re.sub(r"^\d+x?\s+", "", line)

        # Remove set/collector info (e.g., "(NEO) 123")
        line = re.sub(r"\s*\([^)]+\)\s*\d*", "", line)

        # Remove category markers
        if line.lower() in ["deck", "sideboard", "commander", "companion"]:
            continue

        if line:
            card_names.append(line.strip())

    return card_names


def query_oracle_text(card_names: List[str], db_path: Path) -> Dict[str, str]:
    """Query database for oracle text of cards."""
    if not db_path.exists():
        return {}

    oracle_texts = {}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        for card_name in card_names:
            cursor.execute(
                "SELECT oracle_text FROM cards WHERE LOWER(name) = LOWER(?) LIMIT 1",
                (card_name,),
            )
            result = cursor.fetchone()
            if result and result[0]:
                oracle_texts[card_name] = result[0]

        conn.close()
    except Exception as e:
        print(f"Warning: Database query failed: {e}")

    return oracle_texts


def extract_tokens_from_oracle(oracle_text: str) -> List[Tuple[str, int]]:
    """Extract token types and quantities from oracle text."""
    tokens = []

    # Pattern: "create X Y token(s)"
    pattern = (
        r"create(?:s)?\s+(?:a|an|\d+|X|that many)\s+([\w/]+)\s+(?:creature\s+)?token"
    )
    matches = re.findall(pattern, oracle_text, re.IGNORECASE)

    for match in matches:
        # Clean up token type
        token_type = match.strip().lower()
        token_type = token_type.replace("/", " ")  # "Elf/Warrior" -> "Elf Warrior"

        # Try to extract quantity
        qty_pattern = r"create(?:s)?\s+(\d+)\s+" + re.escape(match)
        qty_match = re.search(qty_pattern, oracle_text, re.IGNORECASE)
        quantity = int(qty_match.group(1)) if qty_match else 1

        tokens.append((token_type, quantity))

    # Also check for specific token types
    token_keywords = [
        "treasure",
        "food",
        "clue",
        "blood",
        "shard",
        "goblin",
        "elf",
        "soldier",
        "zombie",
        "spirit",
        "dragon",
        "angel",
        "demon",
        "beast",
        "elemental",
    ]

    for keyword in token_keywords:
        if keyword in oracle_text.lower() and "token" in oracle_text.lower():
            # Avoid duplicates
            if not any(keyword in t[0] for t in tokens):
                tokens.append((keyword, 1))

    return tokens


def query_tokens_from_all_parts(
    card_names: List[str], db_path: Path
) -> Dict[str, List[Tuple[str, int]]]:
    """Query database for tokens using all_parts relationships (primary method)."""
    if not db_path.exists():
        return {}

    token_map = {}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        for card_name in card_names:
            # Query created_tokens table for this card
            cursor.execute(
                """
                SELECT t.name, t.type_line
                FROM prints c
                JOIN created_tokens ct ON c.id = ct.card_id
                JOIN prints t ON ct.token_id = t.id
                WHERE LOWER(c.name) = LOWER(?)
                AND t.is_token = 1
                """,
                (card_name,),
            )

            results = cursor.fetchall()
            if results:
                tokens = []
                for token_name, type_line in results:
                    # Extract token type from name or type_line
                    token_type = token_name.lower().split()[
                        0
                    ]  # First word usually the type
                    tokens.append((token_type, 1))

                if tokens:
                    token_map[card_name] = tokens

        conn.close()
    except Exception as e:
        print(f"Warning: all_parts query failed: {e}")

    return token_map


def analyze_deck_for_tokens(
    deck_path: str, db_path: Path
) -> Tuple[Dict[str, int], Dict[str, List[Tuple[str, int]]]]:
    """Analyze deck using database and suggest tokens with quantities."""
    try:
        with open(deck_path, "r") as f:
            content = f.read()

        # Extract card names
        card_names = extract_card_names(content)
        print(f"Analyzing {len(card_names)} cards...")

        # Primary method: Query all_parts relationships
        card_token_map = query_tokens_from_all_parts(card_names, db_path)
        print(f"Found {len(card_token_map)} cards with token relationships (all_parts)")

        # Fallback: Query oracle texts for cards not found via all_parts
        cards_without_tokens = [
            name for name in card_names if name not in card_token_map
        ]
        if cards_without_tokens:
            print(
                f"Checking {len(cards_without_tokens)} cards via oracle text (fallback)..."
            )
            oracle_texts = query_oracle_text(cards_without_tokens, db_path)

            for card_name, oracle_text in oracle_texts.items():
                tokens = extract_tokens_from_oracle(oracle_text)
                if tokens:
                    card_token_map[card_name] = tokens

        # Aggregate token suggestions
        token_suggestions = Counter()
        for card_name, tokens in card_token_map.items():
            for token_type, qty in tokens:
                token_suggestions[token_type] += qty

        return dict(token_suggestions), card_token_map

    except Exception as e:
        print(f"Error analyzing deck: {e}")
        return {}, {}


def check_token_availability(token_type: str, db_path: Path) -> int:
    """Check how many versions of a token are available."""
    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Search for tokens matching this type
        cursor.execute(
            "SELECT COUNT(*) FROM cards WHERE type_line LIKE '%Token%' AND LOWER(name) LIKE LOWER(?)",
            (f"%{token_type}%",),
        )
        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 0
    except Exception:
        return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python smart_token_pack.py <deck_file> [--verbose]")
        print("\nAdvanced token pack builder with database integration.")
        print("Analyzes deck and suggests tokens with quantities.")
        return 1

    deck_path = sys.argv[1]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    if not Path(deck_path).exists():
        print(f"Error: Deck file not found: {deck_path}")
        return 1

    db_path = get_database_path()
    if not db_path.exists():
        print(f"Warning: Database not found at {db_path}")
        print(
            "Token suggestions will be limited. Run 'make bulk-index-build' to enable full analysis."
        )
        print()

    print(f"\nAnalyzing deck: {deck_path}")
    print("=" * 60)

    token_suggestions, card_token_map = analyze_deck_for_tokens(deck_path, db_path)

    if not token_suggestions:
        print("\nNo token-generating cards detected.")
        print("This deck may not require tokens, or cards weren't found in database.")
        return 0

    print(f"\n{YELLOW}Token Suggestions:{RESET}")
    print("-" * 60)

    for token_type, suggested_qty in sorted(
        token_suggestions.items(), key=lambda x: -x[1]
    ):
        available = check_token_availability(token_type, db_path)
        status = (
            f"{GREEN}[{available} available]{RESET}"
            if available > 0
            else "[not in collection]"
        )
        print(f"  {token_type.title():20s} x{suggested_qty:2d}  {status}")

    if verbose and card_token_map:
        print(f"\n{YELLOW}Token Sources:{RESET}")
        print("-" * 60)
        for card_name, tokens in sorted(card_token_map.items()):
            token_list = ", ".join([f"{t[0]} x{t[1]}" for t in tokens])
            print(f"  {card_name}: {token_list}")

    print(f"\n{YELLOW}Fetch Commands:{RESET}")
    print("-" * 60)
    for token_type in sorted(token_suggestions.keys()):
        # Convert multi-word tokens to single word for SUBTYPE
        subtype = token_type.split()[0].capitalize()
        print(f"  make fetch-tokens SUBTYPE={subtype}")

    print(f"\n{GREEN}Analysis complete!{RESET}")
    print(f"Total token types: {len(token_suggestions)}")
    print(f"Total suggested copies: {sum(token_suggestions.values())}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
