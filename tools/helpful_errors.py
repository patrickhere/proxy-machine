#!/usr/bin/env python3
"""Helpful error messages with suggestions for common mistakes."""

import os
import sys
import sqlite3
from typing import Optional, List, Tuple
from difflib import get_close_matches

# Add parent directory to path
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# Add parent directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))

from bulk_paths import bulk_db_path, get_bulk_data_directory

# Paths
BULK_DIR = str(get_bulk_data_directory())
DB_PATH = str(bulk_db_path())

# Common set code corrections
SET_CODE_CORRECTIONS = {
    # Common mistakes -> Correct code
    "lotr": "ltr",
    "lord of the rings": "ltr",
    "phyrexia": "one",
    "all will be one": "one",
    "dominaria united": "dmu",
    "dom united": "dmu",
    "brothers war": "bro",
    "brother's war": "bro",
    "kamigawa": "neo",
    "neon dynasty": "neo",
    "streets of new capenna": "snc",
    "new capenna": "snc",
    "baldurs gate": "clb",
    "baldur's gate": "clb",
    "commander legends": "cmr",
    "double masters": "2x2",
    "modern horizons": "mh3",
    "wilds of eldraine": "woe",
    "lost caverns": "lci",
    "murders at karlov manor": "mkm",
    "karlov manor": "mkm",
    "outlaws of thunder junction": "otj",
    "thunder junction": "otj",
    "bloomburrow": "blb",
    "duskmourn": "dsk",
    "foundations": "fdn",
}

# Common artist name variations
ARTIST_CORRECTIONS = {
    "rebecca": "Rebecca Guay",
    "guay": "Rebecca Guay",
    "terese": "Terese Nielsen",
    "nielsen": "Terese Nielsen",
    "seb": "Seb McKinnon",
    "mckinnon": "Seb McKinnon",
    "noah": "Noah Bradley",
    "bradley": "Noah Bradley",
}


def suggest_set_code(user_input: str) -> Optional[str]:
    """
    Suggest a correct set code based on user input.

    Args:
        user_input: User's set code input

    Returns:
        Suggested set code or None
    """
    normalized = user_input.lower().strip()

    # Check direct corrections
    if normalized in SET_CODE_CORRECTIONS:
        return SET_CODE_CORRECTIONS[normalized]

    # Try fuzzy matching against known set codes
    conn = _get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT set_code, set_name FROM prints LIMIT 1000")

        set_codes = []
        set_names = {}
        for row in cur.fetchall():
            code = row["set_code"]
            name = row["set_name"] or ""
            set_codes.append(code)
            set_names[code] = name

        # Try fuzzy matching on codes
        code_matches = get_close_matches(normalized, set_codes, n=1, cutoff=0.6)
        if code_matches:
            return code_matches[0]

        # Try fuzzy matching on names
        name_to_code = {name.lower(): code for code, name in set_names.items() if name}
        name_matches = get_close_matches(
            normalized, list(name_to_code.keys()), n=1, cutoff=0.6
        )
        if name_matches:
            return name_to_code[name_matches[0]]

        return None

    finally:
        conn.close()


def suggest_artist_name(user_input: str) -> Optional[str]:
    """
    Suggest a correct artist name based on user input.

    Args:
        user_input: User's artist name input

    Returns:
        Suggested artist name or None
    """
    normalized = user_input.lower().strip()

    # Check direct corrections
    if normalized in ARTIST_CORRECTIONS:
        return ARTIST_CORRECTIONS[normalized]

    # Try fuzzy matching against known artists
    conn = _get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT artist FROM prints WHERE artist IS NOT NULL LIMIT 5000"
        )

        artists = [row["artist"] for row in cur.fetchall() if row["artist"]]

        # Try fuzzy matching
        matches = get_close_matches(user_input, artists, n=3, cutoff=0.6)
        if matches:
            return matches[0]

        # Try partial matching (user typed part of the name)
        partial_matches = [a for a in artists if normalized in a.lower()]
        if partial_matches:
            return partial_matches[0]

        return None

    finally:
        conn.close()


def suggest_card_name(user_input: str, limit: int = 5) -> List[str]:
    """
    Suggest card names based on user input.

    Args:
        user_input: User's card name input
        limit: Maximum number of suggestions

    Returns:
        List of suggested card names
    """
    conn = _get_db_connection()
    if not conn:
        return []

    try:
        cur = conn.cursor()

        # Try exact match first
        cur.execute(
            "SELECT DISTINCT name FROM prints WHERE name LIKE ? LIMIT ?",
            (f"%{user_input}%", limit),
        )

        matches = [row["name"] for row in cur.fetchall()]

        if not matches:
            # Try fuzzy matching on name_slug
            cur.execute("SELECT DISTINCT name FROM prints LIMIT 10000")
            all_names = [row["name"] for row in cur.fetchall()]
            matches = get_close_matches(user_input, all_names, n=limit, cutoff=0.6)

        return matches

    finally:
        conn.close()


def format_error_with_suggestion(
    error_type: str,
    user_input: str,
    suggestion: Optional[str] = None,
    suggestions: Optional[List[str]] = None,
) -> str:
    """
    Format an error message with helpful suggestions.

    Args:
        error_type: Type of error (set_code, artist, card_name)
        user_input: What the user typed
        suggestion: Single suggestion
        suggestions: Multiple suggestions

    Returns:
        Formatted error message
    """
    messages = {
        "set_code": f"⚠️  Set code '{user_input}' not found.",
        "artist": f"⚠️  Artist '{user_input}' not found.",
        "card_name": f"⚠️  Card '{user_input}' not found.",
    }

    error_msg = messages.get(error_type, f"⚠️  '{user_input}' not found.")

    if suggestion:
        error_msg += f"\n   💡 Did you mean '{suggestion}'?"
    elif suggestions:
        error_msg += "\n   💡 Did you mean one of these?"
        for s in suggestions[:5]:
            error_msg += f"\n      • {s}"

    return error_msg


def _get_db_connection() -> Optional[sqlite3.Connection]:
    """Get a database connection if available."""
    if not os.path.exists(DB_PATH):
        return None

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def validate_set_code(set_code: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a set code and provide suggestions if invalid.

    Args:
        set_code: Set code to validate

    Returns:
        Tuple of (is_valid, suggestion)
    """
    conn = _get_db_connection()
    if not conn:
        return (False, None)

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as count FROM prints WHERE set_code = ?",
            (set_code.lower(),),
        )

        row = cur.fetchone()
        if row and row["count"] > 0:
            return (True, None)

        # Not found, try to suggest
        suggestion = suggest_set_code(set_code)
        return (False, suggestion)

    finally:
        conn.close()


def validate_artist(artist: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an artist name and provide suggestions if invalid.

    Args:
        artist: Artist name to validate

    Returns:
        Tuple of (is_valid, suggestion)
    """
    conn = _get_db_connection()
    if not conn:
        return (False, None)

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as count FROM prints WHERE artist LIKE ?",
            (f"%{artist}%",),
        )

        row = cur.fetchone()
        if row and row["count"] > 0:
            return (True, None)

        # Not found, try to suggest
        suggestion = suggest_artist_name(artist)
        return (False, suggestion)

    finally:
        conn.close()


if __name__ == "__main__":
    import click

    @click.group()
    def cli():
        """Helpful error message utilities."""
        pass

    @cli.command()
    @click.argument("set_code")
    def check_set(set_code):
        """Check if a set code is valid and suggest corrections."""
        is_valid, suggestion = validate_set_code(set_code)

        if is_valid:
            click.echo(f"✓ '{set_code}' is a valid set code")
        else:
            msg = format_error_with_suggestion("set_code", set_code, suggestion)
            click.echo(msg)

    @cli.command()
    @click.argument("artist")
    def check_artist(artist):
        """Check if an artist name is valid and suggest corrections."""
        is_valid, suggestion = validate_artist(artist)

        if is_valid:
            click.echo(f"✓ Found cards by '{artist}'")
        else:
            msg = format_error_with_suggestion("artist", artist, suggestion)
            click.echo(msg)

    @cli.command()
    @click.argument("card_name")
    def check_card(card_name):
        """Check if a card name exists and suggest corrections."""
        suggestions = suggest_card_name(card_name)

        if suggestions and suggestions[0].lower() == card_name.lower():
            click.echo(f"✓ Found '{suggestions[0]}'")
        else:
            msg = format_error_with_suggestion(
                "card_name", card_name, suggestions=suggestions
            )
            click.echo(msg)

    cli()
