#!/usr/bin/env python3
"""
Remote database client for Proxy Machine.

Queries Patrick's database over the network instead of maintaining a local copy.
Only downloads the actual card images needed.

Usage:
    export PM_REMOTE_DB_URL=http://100.64.1.5:8080
    uv run python remote_db_client.py search "Lightning Bolt"
    uv run python remote_db_client.py deck my-deck.txt
"""

import requests
import sys
import os
from typing import List, Dict, Any
from pathlib import Path


class RemoteDBClient:
    """Client for querying remote Proxy Machine database."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ProxyMachine-RemoteClient/1.0"})

    def health_check(self) -> Dict[str, Any]:
        """Check if server is reachable."""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def search_cards(
        self,
        name: str = "",
        set_code: str = "",
        type_line: str = "",
        rarity: str = "",
        lang: str = "en",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search for cards."""
        params = {
            "name": name,
            "set_code": set_code,
            "type_line": type_line,
            "rarity": rarity,
            "lang": lang,
            "limit": limit,
        }
        # Remove empty parameters
        params = {k: v for k, v in params.items() if v}

        response = self.session.get(f"{self.base_url}/api/search", params=params)
        response.raise_for_status()
        return response.json()["results"]

    def get_card(self, card_id: str) -> Dict[str, Any]:
        """Get a specific card by ID."""
        response = self.session.get(f"{self.base_url}/api/card/{card_id}")
        response.raise_for_status()
        return response.json()

    def list_sets(self) -> List[Dict[str, str]]:
        """List all available sets."""
        response = self.session.get(f"{self.base_url}/api/sets")
        response.raise_for_status()
        return response.json()["sets"]

    def parse_deck(
        self, decklist: str, prefer_set: str = None, lang: str = "en"
    ) -> Dict[str, Any]:
        """Parse a deck list and get card data."""
        data = {"decklist": decklist, "lang": lang}
        if prefer_set:
            data["prefer_set"] = prefer_set

        response = self.session.post(f"{self.base_url}/api/deck/parse", json=data)
        response.raise_for_status()
        return response.json()

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        response = self.session.get(f"{self.base_url}/api/stats")
        response.raise_for_status()
        return response.json()

    def download_image(self, image_url: str, output_path: Path) -> bool:
        """Download a card image."""
        try:
            response = self.session.get(image_url, stream=True)
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"Failed to download image: {e}")
            return False


def get_remote_url() -> str:
    """Get remote database URL from environment."""
    url = os.environ.get("PM_REMOTE_DB_URL")
    if not url:
        print("ERROR: PM_REMOTE_DB_URL not set")
        print("Set it to Patrick's server URL:")
        print("  export PM_REMOTE_DB_URL=http://100.64.1.5:8080")
        sys.exit(1)
    return url


def cmd_search(client: RemoteDBClient, args: List[str]):
    """Search for cards."""
    if not args:
        print(
            "Usage: remote_db_client.py search <name> [--set SET] [--type TYPE] [--limit N]"
        )
        return

    name = args[0]
    set_code = ""
    type_line = ""
    limit = 20

    # Parse additional arguments
    i = 1
    while i < len(args):
        if args[i] == "--set" and i + 1 < len(args):
            set_code = args[i + 1]
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            type_line = args[i + 1]
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"Searching for: {name}")
    if set_code:
        print(f"  Set: {set_code}")
    if type_line:
        print(f"  Type: {type_line}")
    print()

    results = client.search_cards(
        name=name, set_code=set_code, type_line=type_line, limit=limit
    )

    if not results:
        print("No cards found")
        return

    print(f"Found {len(results)} cards:\n")
    for card in results:
        print(f"  {card['name']} ({card['set_code'].upper()}) - {card['rarity']}")
        if card.get("image_uris"):
            print(f"    Image: {card['image_uris']}")

    print(f"\nShowing {len(results)} results")


def cmd_deck(client: RemoteDBClient, args: List[str]):
    """Parse a deck list."""
    if not args:
        print("Usage: remote_db_client.py deck <deck-file.txt> [--set SET]")
        return

    deck_file = Path(args[0])
    if not deck_file.exists():
        print(f"ERROR: Deck file not found: {deck_file}")
        return

    prefer_set = None
    if "--set" in args:
        idx = args.index("--set")
        if idx + 1 < len(args):
            prefer_set = args[idx + 1]

    decklist = deck_file.read_text()

    print(f"Parsing deck: {deck_file}")
    if prefer_set:
        print(f"  Preferred set: {prefer_set}")
    print()

    result = client.parse_deck(decklist, prefer_set=prefer_set)

    print(f"Found: {result['found']} cards")
    print(f"Missing: {result['not_found']} cards")
    print()

    if result["cards"]:
        print("Cards found:")
        for card in result["cards"]:
            qty = card.get("quantity", 1)
            print(f"  {qty}x {card['name']} ({card['set_code'].upper()})")

    if result["missing"]:
        print("\nCards not found:")
        for card in result["missing"]:
            qty = card.get("quantity", 1)
            print(f"  {qty}x {card['name']}")


def cmd_stats(client: RemoteDBClient, args: List[str]):
    """Show database statistics."""
    print("Fetching database statistics...")
    stats = client.get_stats()

    print("\nDatabase Statistics:")
    print(f"  Total cards: {stats['total_cards']:,}")
    print(f"  Unique names: {stats['unique_names']:,}")
    print(f"  Total sets: {stats['total_sets']:,}")
    print(f"  Database size: {stats['database_size_mb']:.1f} MB")

    print("\nLanguages:")
    for lang_info in stats["languages"][:10]:  # Top 10
        print(f"  {lang_info['lang']}: {lang_info['count']:,} cards")


def cmd_sets(client: RemoteDBClient, args: List[str]):
    """List all sets."""
    print("Fetching sets...")
    sets = client.list_sets()

    print(f"\nAvailable sets ({len(sets)}):\n")
    for set_info in sets:
        print(f"  {set_info['code'].upper()}: {set_info['name']}")


def cmd_health(client: RemoteDBClient, args: List[str]):
    """Check server health."""
    print("Checking server health...")
    health = client.health_check()

    print("\nServer Status:")
    print(f"  Status: {health['status']}")
    print(f"  Database: {'OK' if health['database'] else 'NOT FOUND'}")
    print(f"  Database size: {health['db_size_mb']:.1f} MB")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Proxy Machine Remote Database Client")
        print("\nUsage:")
        print("  remote_db_client.py search <name> [--set SET] [--type TYPE]")
        print("  remote_db_client.py deck <deck-file.txt> [--set SET]")
        print("  remote_db_client.py sets")
        print("  remote_db_client.py stats")
        print("  remote_db_client.py health")
        print("\nEnvironment:")
        print("  PM_REMOTE_DB_URL - Patrick's server URL (required)")
        print("\nExample:")
        print("  export PM_REMOTE_DB_URL=http://100.64.1.5:8080")
        print("  remote_db_client.py search 'Lightning Bolt'")
        return 1

    command = sys.argv[1]
    args = sys.argv[2:]

    # Get remote URL
    remote_url = get_remote_url()

    # Create client
    client = RemoteDBClient(remote_url)

    # Test connection
    try:
        client.health_check()
    except Exception as e:
        print(f"ERROR: Cannot connect to server at {remote_url}")
        print(f"  {e}")
        print("\nMake sure:")
        print("  1. You're connected to Tailscale")
        print("  2. Patrick's server is running")
        print("  3. PM_REMOTE_DB_URL is correct")
        return 1

    # Execute command
    commands = {
        "search": cmd_search,
        "deck": cmd_deck,
        "stats": cmd_stats,
        "sets": cmd_sets,
        "health": cmd_health,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        print(f"Available commands: {', '.join(commands.keys())}")
        return 1

    try:
        commands[command](client, args)
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
