#!/usr/bin/env python3
"""Advanced search features.

Implements:
- Saved search queries
- Search history
- Complex boolean queries
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


SAVED_SEARCHES = Path("data/saved_searches.json")
SEARCH_HISTORY = Path("data/search_history.json")


def load_saved_searches() -> Dict:
    """Load saved searches from file."""
    if not SAVED_SEARCHES.exists():
        return {}

    with open(SAVED_SEARCHES) as f:
        return json.load(f)


def save_searches(searches: Dict):
    """Save searches to file."""
    SAVED_SEARCHES.parent.mkdir(parents=True, exist_ok=True)
    with open(SAVED_SEARCHES, "w") as f:
        json.dump(searches, f, indent=2)


def load_search_history() -> List[Dict]:
    """Load search history from file."""
    if not SEARCH_HISTORY.exists():
        return []

    with open(SEARCH_HISTORY) as f:
        return json.load(f)


def save_search_history(history: List[Dict]):
    """Save search history to file."""
    SEARCH_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with open(SEARCH_HISTORY, "w") as f:
        json.dump(history, f, indent=2)


def add_to_history(query: str, filters: Dict):
    """Add search to history."""
    history = load_search_history()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "filters": filters,
    }

    # Add to beginning
    history.insert(0, entry)

    # Keep only last 100
    history = history[:100]

    save_search_history(history)


def save_search(name: str, query: str, filters: Dict, description: str = ""):
    """Save a search query."""
    searches = load_saved_searches()

    searches[name] = {
        "query": query,
        "filters": filters,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "last_used": None,
        "use_count": 0,
    }

    save_searches(searches)
    print(f"[OK] Saved search: {name}")


def load_search(name: str) -> Optional[Dict]:
    """Load a saved search."""
    searches = load_saved_searches()

    if name not in searches:
        print(f"[ERROR] Search not found: {name}")
        return None

    search = searches[name]

    # Update usage stats
    search["last_used"] = datetime.now().isoformat()
    search["use_count"] = search.get("use_count", 0) + 1
    searches[name] = search
    save_searches(searches)

    return search


def list_saved_searches():
    """List all saved searches."""
    searches = load_saved_searches()

    print("\n" + "=" * 70)
    print("  SAVED SEARCHES")
    print("=" * 70)

    if not searches:
        print("\n[INFO] No saved searches")
        return

    print(f"\nTotal: {len(searches)}\n")

    for name, data in sorted(searches.items()):
        print(f"[{name}]")
        print(f"  Query: {data['query']}")
        if data.get("description"):
            print(f"  Description: {data['description']}")
        print(f"  Used: {data.get('use_count', 0)} times")
        if data.get("last_used"):
            print(f"  Last used: {data['last_used']}")
        print()

    print("=" * 70)


def show_search_history(limit: int = 20):
    """Show recent search history."""
    history = load_search_history()

    print("\n" + "=" * 70)
    print("  SEARCH HISTORY")
    print("=" * 70)

    if not history:
        print("\n[INFO] No search history")
        return

    print(f"\nShowing last {min(limit, len(history))} searches:\n")

    for i, entry in enumerate(history[:limit], 1):
        print(f"{i}. {entry['timestamp']}")
        print(f"   Query: {entry['query']}")
        if entry.get("filters"):
            print(f"   Filters: {entry['filters']}")
        print()

    print("=" * 70)


def parse_boolean_query(query: str) -> Dict:
    """Parse complex boolean query.

    Supports:
    - AND, OR, NOT operators
    - Parentheses for grouping
    - Field-specific searches (name:goblin, type:creature)

    Examples:
        "goblin AND (red OR black)"
        "type:creature AND cmc:3 NOT color:blue"
        "name:bolt OR name:shock"
    """
    # This is a simplified parser - full implementation would use proper parsing
    parsed = {"raw": query, "operators": [], "terms": [], "fields": {}}

    # Extract field searches
    import re

    field_pattern = r"(\w+):(\w+)"
    for match in re.finditer(field_pattern, query):
        field, value = match.groups()
        if field not in parsed["fields"]:
            parsed["fields"][field] = []
        parsed["fields"][field].append(value)

    # Extract operators
    if " AND " in query.upper():
        parsed["operators"].append("AND")
    if " OR " in query.upper():
        parsed["operators"].append("OR")
    if " NOT " in query.upper():
        parsed["operators"].append("NOT")

    # Extract terms (simplified)
    terms = re.sub(field_pattern, "", query)
    terms = re.sub(r"\b(AND|OR|NOT)\b", "", terms, flags=re.IGNORECASE)
    parsed["terms"] = [t.strip() for t in terms.split() if t.strip()]

    return parsed


def execute_search(
    query: str, filters: Optional[Dict] = None, save_to_history: bool = True
):
    """Execute a search query."""
    print("\n" + "=" * 70)
    print("  SEARCH RESULTS")
    print("=" * 70)

    # Parse query
    parsed = parse_boolean_query(query)

    print(f"\nQuery: {query}")
    if parsed["operators"]:
        print(f"Operators: {', '.join(parsed['operators'])}")
    if parsed["fields"]:
        print(f"Fields: {parsed['fields']}")
    if parsed["terms"]:
        print(f"Terms: {', '.join(parsed['terms'])}")

    # Add to history
    if save_to_history:
        add_to_history(query, filters or {})

    # This would execute the actual search against the database
    print("\n[INFO] Search execution not yet implemented")
    print("[INFO] This is a framework for advanced search features")

    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python advanced_search.py <command> [options]")
        print("\nCommands:")
        print("  search <query>              - Execute search query")
        print("  save <name> <query>         - Save search query")
        print("  load <name>                 - Load and execute saved search")
        print("  list                        - List saved searches")
        print("  history [limit]             - Show search history")
        print("\nExamples:")
        print("  python advanced_search.py search 'goblin AND red'")
        print(
            "  python advanced_search.py save red-goblins 'type:creature AND name:goblin AND color:red'"
        )
        print("  python advanced_search.py load red-goblins")
        print("  python advanced_search.py list")
        print("  python advanced_search.py history 10")
        return 1

    command = sys.argv[1]

    if command == "search":
        if len(sys.argv) < 3:
            print("[ERROR] Query required")
            return 1

        query = " ".join(sys.argv[2:])
        execute_search(query)
        return 0

    if command == "save":
        if len(sys.argv) < 4:
            print("[ERROR] Name and query required")
            return 1

        name = sys.argv[2]
        query = " ".join(sys.argv[3:])
        save_search(name, query, {})
        return 0

    if command == "load":
        if len(sys.argv) < 3:
            print("[ERROR] Search name required")
            return 1

        name = sys.argv[2]
        search = load_search(name)
        if search:
            execute_search(search["query"], search["filters"])
        return 0

    if command == "list":
        list_saved_searches()
        return 0

    if command == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_search_history(limit)
        return 0

    print(f"[ERROR] Unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
