"""Magic: The Gathering Plugin

Primary plugin for MTG card management, deck parsing, and card fetching.
"""

from typing import Dict, Any
from ..registry import PluginRegistry

# Plugin metadata
PLUGIN: Dict[str, Any] = {
    "name": "mtg",
    "version": "2.0.0",
    "description": "Magic: The Gathering card management and deck parsing",
    "author": "Proxy Machine Team",
    "games": ["mtg", "magic", "magic-the-gathering"],
    "features": ["deck_parsing", "card_fetching", "scryfall_integration"],
}


def register_with_registry(registry: PluginRegistry) -> None:
    """Register MTG functionality with the plugin registry."""
    try:
        # Import and register deck parsers
        from .deck_formats import (
            parse_moxfield,
            parse_archidekt,
            parse_mtga,
            parse_simple_list,
            parse_mtgo,
            parse_deckstats,
            parse_scryfall_json,
        )

        # Register parsers for different formats
        registry.register_parser("moxfield", parse_moxfield, "mtg")
        registry.register_parser("archidekt", parse_archidekt, "mtg")
        registry.register_parser("mtga", parse_mtga, "mtg")
        registry.register_parser("mtgo", parse_mtgo, "mtg")
        registry.register_parser("deckstats", parse_deckstats, "mtg")
        registry.register_parser("scryfall", parse_scryfall_json, "mtg")
        registry.register_parser("simple", parse_simple_list, "mtg")
        registry.register_parser("mtg", parse_simple_list, "mtg")  # Default MTG parser

        # Import and register fetchers (fetch.py is a CLI script, so we'll skip for now)
        # TODO: Refactor fetch.py to expose reusable functions
        # registry.register_fetcher("mtg", fetch_mtg_cards, "mtg")

        print(f"✓ Registered MTG plugin with {len(PLUGIN['games'])} game aliases")

    except ImportError as e:
        print(f"Warning: Could not register some MTG functionality: {e}")
    except Exception as e:
        print(f"Error registering MTG plugin: {e}")


# Auto-register when imported directly
if __name__ != "__main__":
    from ..registry import registry

    register_with_registry(registry)
