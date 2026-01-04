#!/usr/bin/env python3
"""Plugin Regression Test Suite.

Tests deck format parsers against canonical sample decks to prevent regressions.
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins.mtg import deck_formats

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


# Test fixtures - canonical deck samples
SAMPLE_DECKS = {
    "simple_list": {
        "content": """Isshin, Two Heavens as One
Arid Mesa
Battlefield Forge
Blazemire Verge
Blood Crypt""",
        "expected": {
            "cards": 5,
            "names": [
                "Isshin, Two Heavens as One",
                "Arid Mesa",
                "Battlefield Forge",
                "Blazemire Verge",
                "Blood Crypt",
            ],
        },
    },
    "mtga": {
        "content": """Deck
2 Arid Mesa (MH2) 244
1 Lion Sash (NEO) 26
1 Loran of the Third Path (BRO) 28
2 Witch Enchanter (WOE) 35

Sideboard
1 Containment Priest (M21) 13
2 Rest in Peace (A25) 32""",
        "expected": {
            "cards": 6,  # Sideboard section header is skipped
            "names": [
                "Arid Mesa",
                "Lion Sash",
                "Loran of the Third Path",
                "Witch Enchanter",
                "Containment Priest",
                "Rest in Peace",
            ],
        },
    },
    "moxfield": {
        "content": """1 Isshin, Two Heavens as One (NEO) 224
1 Arid Mesa (MH2) 244
1 Battlefield Forge (10E) 347
1 Blazemire Verge (BLB) 257
1 Blood Crypt (RNA) 245""",
        "expected": {
            "cards": 5,
            "names": [
                "Isshin, Two Heavens as One",
                "Arid Mesa",
                "Battlefield Forge",
                "Blazemire Verge",
                "Blood Crypt",
            ],
            "sets": ["NEO", "MH2", "10E", "BLB", "RNA"],
        },
    },
    "archidekt": {
        "content": """1x Isshin, Two Heavens as One (neo) 224
1x Arid Mesa (mh2) 244
2x Battlefield Forge (10e) 347
1x Blood Crypt (rna) 245""",
        "expected": {
            "cards": 4,  # 4 unique cards
            "total_quantity": 5,  # 5 total copies
            "names": [
                "Isshin, Two Heavens as One",
                "Arid Mesa",
                "Battlefield Forge",
                "Blood Crypt",
            ],
        },
    },
    "deckstats": {
        "content": """1 [MID#159] Smoldering Egg // Ashmouth Dragon
1 [NEO#224] Isshin, Two Heavens as One
1 Arid Mesa
2 Battlefield Forge""",
        "expected": {
            "cards": 4,
            "names": [
                "Smoldering Egg // Ashmouth Dragon",
                "Isshin, Two Heavens as One",
                "Arid Mesa",
                "Battlefield Forge",
            ],
        },
    },
}


class CardCollector:
    """Helper to collect parsed card data."""

    def __init__(self):
        self.cards: List[Dict] = []
        self.errors: List[str] = []

    def handle_card(
        self, index: int, name: str, set_code: str, collector_number: str, quantity: int
    ):
        """Callback for deck parsers."""
        self.cards.append(
            {
                "index": index,
                "name": name,
                "set_code": set_code,
                "collector_number": collector_number,
                "quantity": quantity,
            }
        )

    def reset(self):
        """Clear collected data."""
        self.cards = []
        self.errors = []


def test_simple_list() -> Tuple[bool, str]:
    """Test simple list parser."""
    sample = SAMPLE_DECKS["simple_list"]
    collector = CardCollector()

    try:
        # Suppress print output
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            deck_formats.parse_simple_list(sample["content"], collector.handle_card)

        # Verify results
        if len(collector.cards) != sample["expected"]["cards"]:
            return (
                False,
                f"Expected {sample['expected']['cards']} cards, got {len(collector.cards)}",
            )

        parsed_names = [c["name"] for c in collector.cards]
        for expected_name in sample["expected"]["names"]:
            if expected_name not in parsed_names:
                return False, f"Missing card: {expected_name}"

        return True, "All cards parsed correctly"

    except Exception as e:
        return False, f"Parser error: {str(e)}"


def test_mtga() -> Tuple[bool, str]:
    """Test MTGA format parser."""
    sample = SAMPLE_DECKS["mtga"]
    collector = CardCollector()

    try:
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            deck_formats.parse_mtga(sample["content"], collector.handle_card)

        if len(collector.cards) != sample["expected"]["cards"]:
            return (
                False,
                f"Expected {sample['expected']['cards']} cards, got {len(collector.cards)}",
            )

        parsed_names = [c["name"] for c in collector.cards]
        for expected_name in sample["expected"]["names"]:
            if expected_name not in parsed_names:
                return False, f"Missing card: {expected_name}"

        return True, "MTGA format parsed correctly"

    except Exception as e:
        return False, f"Parser error: {str(e)}"


def test_moxfield() -> Tuple[bool, str]:
    """Test Moxfield format parser."""
    sample = SAMPLE_DECKS["moxfield"]
    collector = CardCollector()

    try:
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            deck_formats.parse_moxfield(sample["content"], collector.handle_card)

        if len(collector.cards) != sample["expected"]["cards"]:
            return (
                False,
                f"Expected {sample['expected']['cards']} cards, got {len(collector.cards)}",
            )

        parsed_names = [c["name"] for c in collector.cards]
        for expected_name in sample["expected"]["names"]:
            if expected_name not in parsed_names:
                return False, f"Missing card: {expected_name}"

        # Verify set codes are parsed
        parsed_sets = [c["set_code"] for c in collector.cards if c["set_code"]]
        if len(parsed_sets) != len(sample["expected"]["sets"]):
            return (
                False,
                f"Expected {len(sample['expected']['sets'])} set codes, got {len(parsed_sets)}",
            )

        return True, "Moxfield format parsed correctly"

    except Exception as e:
        return False, f"Parser error: {str(e)}"


def test_archidekt() -> Tuple[bool, str]:
    """Test Archidekt format parser."""
    sample = SAMPLE_DECKS["archidekt"]
    collector = CardCollector()

    try:
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            deck_formats.parse_archidekt(sample["content"], collector.handle_card)

        if len(collector.cards) != sample["expected"]["cards"]:
            return (
                False,
                f"Expected {sample['expected']['cards']} cards, got {len(collector.cards)}",
            )

        total_qty = sum(c["quantity"] for c in collector.cards)
        if total_qty != sample["expected"]["total_quantity"]:
            return (
                False,
                f"Expected total quantity {sample['expected']['total_quantity']}, got {total_qty}",
            )

        return True, "Archidekt format parsed correctly"

    except Exception as e:
        return False, f"Parser error: {str(e)}"


def test_deckstats() -> Tuple[bool, str]:
    """Test Deckstats format parser."""
    sample = SAMPLE_DECKS["deckstats"]
    collector = CardCollector()

    try:
        import io
        import contextlib

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            deck_formats.parse_deckstats(sample["content"], collector.handle_card)

        if len(collector.cards) != sample["expected"]["cards"]:
            return (
                False,
                f"Expected {sample['expected']['cards']} cards, got {len(collector.cards)}",
            )

        parsed_names = [c["name"] for c in collector.cards]
        for expected_name in sample["expected"]["names"]:
            if expected_name not in parsed_names:
                return False, f"Missing card: {expected_name}"

        return True, "Deckstats format parsed correctly"

    except Exception as e:
        return False, f"Parser error: {str(e)}"


def main():
    """Run all plugin tests."""
    print(" Running Plugin Regression Tests\n")

    tests = [
        ("Simple List", test_simple_list),
        ("MTGA Format", test_mtga),
        ("Moxfield Format", test_moxfield),
        ("Archidekt Format", test_archidekt),
        ("Deckstats Format", test_deckstats),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            success, message = test_func()
            if success:
                print(f"{GREEN}✓{RESET} {test_name}: {message}")
                passed += 1
            else:
                print(f"{RED}✗{RESET} {test_name}: {message}")
                failed += 1
        except Exception as e:
            print(f"{RED}✗{RESET} {test_name}: Unexpected error: {str(e)}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {GREEN}{passed} passed{RESET}, {RED}{failed} failed{RESET}")
    print(f"{'='*50}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
