"""Database type definitions and column name constants.

This module provides type safety and prevents column name mismatches
by centralizing all database column names as constants.
"""

from typing import TypedDict, Optional, Union, Any


# Database column name constants
class DBColumns:
    """Column names for the prints table.

    Use these constants instead of string literals to prevent typos
    and make refactoring easier.
    """

    # Primary fields
    ID = "id"
    NAME = "name"
    NAME_SLUG = "name_slug"
    SET_CODE = "set_code"  # NOT "set"
    COLLECTOR_NUMBER = "collector_number"
    TYPE_LINE = "type_line"

    # Boolean flags (stored as INTEGER 0/1)
    IS_BASIC_LAND = "is_basic_land"
    IS_TOKEN = "is_token"
    FULL_ART = "full_art"
    PROMO = "promo"
    TEXTLESS = "textless"

    # Image and visual
    IMAGE_URL = "image_url"  # NOT "image_uris_png" or "image_uris_large"
    ILLUSTRATION_ID = "illustration_id"
    FRAME = "frame"
    FRAME_EFFECTS = "frame_effects"
    BORDER_COLOR = "border_color"
    LAYOUT = "layout"

    # Oracle data
    ORACLE_ID = "oracle_id"
    ORACLE_TEXT = "oracle_text"
    KEYWORDS = "keywords"
    COLOR_IDENTITY = "color_identity"
    COLORS = "colors"
    PRODUCED_MANA = "produced_mana"

    # Card properties
    ARTIST = "artist"
    RARITY = "rarity"
    CMC = "cmc"
    MANA_COST = "mana_cost"
    LANG = "lang"

    # Set information
    SET_NAME = "set_name"
    RELEASED_AT = "released_at"

    # Additional data
    PRICES = "prices"
    LEGALITIES = "legalities"
    ALL_PARTS = "all_parts"


class CardRelationshipColumns:
    """Column names for the card_relationships table."""

    SOURCE_CARD_ID = "source_card_id"
    RELATED_CARD_ID = "related_card_id"
    RELATIONSHIP_TYPE = "relationship_type"
    RELATED_CARD_NAME = "related_card_name"


# Relationship type constants
class RelationshipType:
    """Valid relationship types in card_relationships table."""

    COMBO_PIECE = "combo_piece"  # MDFC, adventure, split cards
    MELD_PART = "meld_part"  # Cards that meld together
    MELD_RESULT = "meld_result"  # Result of melding
    TOKEN = "token"  # Tokens created by cards


class PrintRow(TypedDict, total=False):
    """Type definition for a row from the prints table.

    All fields are optional (total=False) since not all queries
    return all columns.
    """

    # Primary fields
    id: str
    name: str
    name_slug: str
    set_code: str
    collector_number: str
    type_line: str

    # Boolean flags (INTEGER 0/1 in database)
    is_basic_land: int
    is_token: int
    full_art: int
    promo: int
    textless: int

    # Image and visual
    image_url: str
    illustration_id: str
    frame: str
    frame_effects: str
    border_color: str
    layout: str

    # Oracle data
    oracle_id: str
    oracle_text: str
    keywords: str
    color_identity: str
    colors: str
    produced_mana: str

    # Card properties
    artist: str
    rarity: str
    cmc: float
    mana_cost: str
    lang: str

    # Set information
    set_name: str
    released_at: str

    # Additional data (JSON strings)
    prices: str
    legalities: str
    all_parts: str


class CardRelationshipRow(TypedDict):
    """Type definition for a row from the card_relationships table."""

    source_card_id: str
    related_card_id: str
    relationship_type: str
    related_card_name: Optional[str]


# Helper functions for type conversion
def bool_to_db(value: bool) -> int:
    """Convert Python boolean to database integer (0 or 1)."""
    return 1 if value else 0


def db_to_bool(value: Union[int, bool]) -> bool:
    """Convert database integer to Python boolean.

    Handles both int (0/1) and bool values for compatibility.
    """
    return bool(value)


def get_column(row: PrintRow, column: str, default: Any = None) -> Any:
    """Safely get a column value from a database row.

    Args:
        row: Database row dict
        column: Column name (use DBColumns constants)
        default: Default value if column is missing or None

    Returns:
        Column value or default

    Example:
        >>> name = get_column(row, DBColumns.NAME, "Unknown")
        >>> set_code = get_column(row, DBColumns.SET_CODE, "")
    """
    return row.get(column, default)


# Schema version tracking
SCHEMA_VERSION = 6
SCHEMA_DESCRIPTION = """
Schema v6 changes:
- Added card_relationships table
- Tracks combo_piece, meld_part, meld_result, token relationships
- Indexed on source_card_id, related_card_id, relationship_type
"""
