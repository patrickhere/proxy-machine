"""Pure utility functions for PDF generation.

This module contains pure functions with no side effects:
- String sanitization and normalization
- Slug generation
- Set code normalization
- Language normalization

All functions are deterministic and have no external dependencies.
"""


def sanitize_profile_name(raw_name: str) -> str | None:
    """Sanitize a profile name to be filesystem-safe.

    Args:
        raw_name: Raw profile name from user input

    Returns:
        Sanitized profile name (lowercase, alphanumeric + dash/underscore)
        or None if invalid

    Examples:
        >>> sanitize_profile_name("My Profile")
        'my-profile'
        >>> sanitize_profile_name("test_123")
        'test_123'
        >>> sanitize_profile_name("invalid@#$")
        None
    """
    sanitized = raw_name.strip()

    if not sanitized:
        return None

    sanitized = sanitized.replace(" ", "-").lower()

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not all(char in allowed for char in sanitized):
        return None

    return sanitized


def normalize_set_code(set_code: str) -> str:
    """Normalize set codes to merge related sets into canonical folders.

    Handles variants like CED/CEI, sets with spaces/dashes, etc.

    Args:
        set_code: Set code from Scryfall data

    Returns:
        Normalized set code (canonical folder name)

    Examples:
        >>> normalize_set_code("CED")
        'ce'
        >>> normalize_set_code("eos 2")
        'eos-2'
        >>> normalize_set_code("ZNR")
        'znr'
    """
    if not set_code:
        return "misc"

    set_code = set_code.lower().strip()

    # Map of set code variants to their canonical name
    # Format: set_code -> canonical_folder_name
    set_normalizations = {
        # Collectors' Edition variants (domestic vs international)
        "ced": "ce",
        "cei": "ce",
        # Add other known variants here as needed
    }

    # Check for direct mapping first
    if set_code in set_normalizations:
        return set_normalizations[set_code]

    # For sets with spaces or special characters, slugify them
    # This handles cases like "eos 2" -> "eos-2"
    if " " in set_code or any(c in set_code for c in ["-", "/", "\u2014", "\u2013"]):
        return slugify(set_code)

    # Otherwise return as-is (already lowercase)
    return set_code


def slugify(value: str, *, allow_underscores: bool = False) -> str:
    """Convert a string to a URL/filesystem-safe slug.

    Args:
        value: String to slugify
        allow_underscores: Whether to preserve underscores (default: False)

    Returns:
        Slugified string (lowercase, alphanumeric + dashes)

    Examples:
        >>> slugify("Hello World")
        'hello-world'
        >>> slugify("test_file", allow_underscores=True)
        'test_file'
        >>> slugify("multiple---dashes")
        'multiple-dashes'
    """
    value = value.lower()
    result: list[str] = []
    previous_dash = False

    for char in value:
        if char.isalnum():
            result.append(char)
            previous_dash = False
        elif char in {" ", "-", "\u2014", "\u2013", "/"}:
            if not previous_dash:
                result.append("-")
                previous_dash = True
        elif char == "_" and allow_underscores:
            result.append("_")
            previous_dash = False
        else:
            continue

    slug = "".join(result).strip("-")

    while "--" in slug:
        slug = slug.replace("--", "-")

    return slug or "token"


def title_from_slug(slug: str) -> str:
    """Convert a slug back to a title-cased string.

    Args:
        slug: Slug string (lowercase with dashes/underscores)

    Returns:
        Title-cased string with spaces

    Examples:
        >>> title_from_slug("hello-world")
        'Hello World'
        >>> title_from_slug("test_file")
        'Test File'
    """
    return slug.replace("-", " ").replace("_", " ").title()


def normalize_langs(lang_preference: str) -> list[str]:
    """Normalize language preference into list of language codes.

    Supports:
    - Single language: "en" -> ["en"]
    - Multiple languages: "en,ja" -> ["en", "ja"]
    - Whitespace handling: "en, ja" -> ["en", "ja"]

    Args:
        lang_preference: Language preference string

    Returns:
        List of normalized language codes (lowercase, stripped)

    Examples:
        >>> normalize_langs("en")
        ['en']
        >>> normalize_langs("en,ja,ph")
        ['en', 'ja', 'ph']
        >>> normalize_langs("EN, JA")
        ['en', 'ja']
    """
    if not lang_preference:
        return ["en"]

    # Split on comma and normalize each language
    langs = [lang.strip().lower() for lang in lang_preference.split(",")]

    # Filter out empty strings
    langs = [lang for lang in langs if lang]

    return langs if langs else ["en"]


def parse_token_stem(stem: str) -> dict | None:
    """Parse token stem in new format: tokenname-arttype-language-set.

    Args:
        stem: Filename stem (without extension)

    Returns:
        Dict with parsed components or None if invalid format
        Keys: name, art_type, language, set_code

    Examples:
        >>> parse_token_stem("goblin-fullart-en-znr")
        {'name': 'goblin', 'art_type': 'fullart', 'language': 'en', 'set_code': 'znr'}
        >>> parse_token_stem("invalid")
        None
    """
    parts = stem.split("-")

    # Need at least 4 parts: name-arttype-lang-set
    if len(parts) < 4:
        return None

    # Last 3 parts are: arttype, language, set
    set_code = parts[-1]
    language = parts[-2]
    art_type = parts[-3]

    # Everything before that is the token name (may contain dashes)
    name = "-".join(parts[:-3])

    return {
        "name": name,
        "art_type": art_type,
        "language": language,
        "set_code": set_code,
    }


def parse_enhanced_stem_format(stem: str) -> tuple[str, str, str]:
    """Parse enhanced stem format: landname-arttype-language.

    Returns: (landname, arttype, language)

    Args:
        stem: Filename stem (without extension)

    Returns:
        Tuple of (land_name, art_type, language)

    Examples:
        >>> parse_enhanced_stem_format("island-fullart-en")
        ('island', 'fullart', 'en')
        >>> parse_enhanced_stem_format("mountain-showcase-ja")
        ('mountain', 'showcase', 'ja')
    """
    parts = stem.split("-")

    if len(parts) < 3:
        # Fallback: assume basic format
        return (stem, "normal", "en")

    language = parts[-1]
    art_type = parts[-2]
    land_name = "-".join(parts[:-2])

    return (land_name, art_type, language)
