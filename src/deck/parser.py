"""Deck file parsing for various formats.

Supports:
- MTGA format: "4 Lightning Bolt (M10) 146"
- Simple format: "4 Lightning Bolt"
- Arena export format
- Moxfield/Archidekt formats

All parsers return a list of deck entries with count, name, and optional set.
"""

import re
from typing import List, Dict, Any

from errors import DeckParsingError


def parse_deck_file(path: str) -> List[Dict[str, Any]]:
    """Parse a deck file and return list of card entries.

    Supports multiple formats:
    - MTGA: "4 Lightning Bolt (M10) 146"
    - Simple: "4 Lightning Bolt"
    - Comments: Lines starting with // or #
    - Sideboard: Lines starting with "SB:" or "Sideboard"

    Args:
        path: Path to deck file

    Returns:
        List of dicts with keys: count, name, set (optional)

    Raises:
        FileNotFoundError: If deck file doesn't exist
        ValueError: If line cannot be parsed

    Examples:
        >>> parse_deck_file("deck.txt")
        [{'count': 4, 'name': 'Lightning Bolt', 'set': 'm10'}, ...]
    """
    deck_entries: List[Dict] = []

    # Pattern matches:
    # - Required: count and name
    # - Optional: set code in parentheses
    # - Optional: collector number after set
    pattern = re.compile(
        r"^(?P<count>\d+)\s+(?P<name>[^\(]+?)(?:\s+\((?P<set>[A-Za-z0-9]{2,})\))?(?:\s+\d+)?\s*$"
    )

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line_num, line in enumerate(handle, 1):
                stripped = line.strip()

                # Skip empty lines and comments
                if (
                    not stripped
                    or stripped.startswith("//")
                    or stripped.startswith("#")
                ):
                    continue

                # Skip sideboard entries (for now)
                if stripped.lower().startswith("sb:"):
                    continue

                # Skip section headers
                if stripped.lower() in ["deck", "sideboard", "commander", "companion"]:
                    continue

                match = pattern.match(stripped)
                if not match:
                    raise DeckParsingError(
                        f"Could not parse deck line {line_num}: '{stripped}'\n"
                        f"Expected format: '4 Card Name' or '4 Card Name (SET)'"
                    )

                count = int(match.group("count"))
                name = match.group("name").strip()
                set_code = match.group("set")

                deck_entries.append(
                    {
                        "count": count,
                        "name": name,
                        "set": set_code.lower() if set_code else None,
                    }
                )

    except FileNotFoundError:
        raise FileNotFoundError(f"Deck file not found: {path}")
    except OSError as error:
        raise OSError(f"Could not read deck file '{path}': {error}")

    return deck_entries


def validate_deck_entry(entry: Dict) -> bool:
    """Validate a deck entry has required fields.

    Args:
        entry: Deck entry dict

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_deck_entry({'count': 4, 'name': 'Lightning Bolt'})
        True
        >>> validate_deck_entry({'count': 4})
        False
    """
    if not isinstance(entry, dict):
        return False

    if "count" not in entry or "name" not in entry:
        return False

    if not isinstance(entry["count"], int) or entry["count"] < 1:
        return False

    if not isinstance(entry["name"], str) or not entry["name"].strip():
        return False

    return True


def count_cards(deck_entries: List[Dict]) -> int:
    """Count total cards in deck.

    Args:
        deck_entries: List of deck entries

    Returns:
        Total card count

    Examples:
        >>> count_cards([{'count': 4, 'name': 'Bolt'}, {'count': 3, 'name': 'Path'}])
        7
    """
    return sum(entry.get("count", 0) for entry in deck_entries)


def group_by_name(deck_entries: List[Dict]) -> Dict[str, List[Dict]]:
    """Group deck entries by card name.

    Args:
        deck_entries: List of deck entries

    Returns:
        Dict mapping card name to list of entries

    Examples:
        >>> group_by_name([{'count': 4, 'name': 'Bolt', 'set': 'lea'}])
        {'Bolt': [{'count': 4, 'name': 'Bolt', 'set': 'lea'}]}
    """
    grouped: Dict[str, List[Dict]] = {}

    for entry in deck_entries:
        name = entry.get("name", "")
        if name not in grouped:
            grouped[name] = []
        grouped[name].append(entry)

    return grouped


def deduplicate_entries(deck_entries: List[Dict]) -> List[Dict]:
    """Combine duplicate entries (same name and set).

    Args:
        deck_entries: List of deck entries

    Returns:
        Deduplicated list with combined counts

    Examples:
        >>> deduplicate_entries([
        ...     {'count': 2, 'name': 'Bolt', 'set': 'lea'},
        ...     {'count': 2, 'name': 'Bolt', 'set': 'lea'}
        ... ])
        [{'count': 4, 'name': 'Bolt', 'set': 'lea'}]
    """
    # Use (name, set) as key
    combined: Dict[tuple, Dict] = {}

    for entry in deck_entries:
        name = entry.get("name", "")
        set_code = entry.get("set")
        key = (name, set_code)

        if key in combined:
            combined[key]["count"] += entry.get("count", 0)
        else:
            combined[key] = entry.copy()

    return list(combined.values())
