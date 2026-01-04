#!/usr/bin/env python3
"""
Plugin Registry Demonstration

Shows how to use the new centralized plugin registry system.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins.registry import registry, list_available_games


def main():
    """Demonstrate plugin registry functionality."""
    print("Plugin Registry Demonstration")
    print("=" * 40)

    # Show discovered plugins
    plugins = registry.list_plugins()
    print(f"\nDiscovered Plugins: {len(plugins)}")
    for plugin in plugins:
        status = "enabled" if plugin.enabled else "disabled"
        print(f"  - {plugin.name} v{plugin.version} [{status}]")
        print(f"    {plugin.description}")

    # Show available parsers
    parsers = registry.list_parsers()
    print(f"\nAvailable Parsers: {len(parsers)}")
    for parser_name in sorted(parsers):
        print(f"  - {parser_name}")

    # Show available fetchers
    fetchers = registry.list_fetchers()
    print(f"\nAvailable Fetchers: {len(fetchers)}")
    for fetcher_name in sorted(fetchers):
        print(f"  - {fetcher_name}")

    # Show games with functionality
    games = list_available_games()
    print(f"\nGames with Functionality: {len(games)}")
    for game, features in games.items():
        parser_status = "✓" if features["parser"] else "✗"
        fetcher_status = "✓" if features["fetcher"] else "✗"
        print(f"  - {game}: Parser {parser_status}, Fetcher {fetcher_status}")

    # Demonstrate parser lookup
    print("\nParser Lookup Examples:")
    test_games = ["mtg", "moxfield", "archidekt", "nonexistent"]
    for game in test_games:
        parser = registry.get_parser(game)
        status = "Found" if parser else "Not found"
        print(f"  - {game}: {status}")


if __name__ == "__main__":
    main()
