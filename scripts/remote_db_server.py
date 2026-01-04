#!/usr/bin/env python3
"""
Remote database server for Proxy Machine.

Allows friends to query your database over the network without downloading it.
They only download the actual card images they need.

Usage:
    uv run python remote_db_server.py

Friends connect via:
    PM_REMOTE_DB_URL=http://your-tailscale-ip:8080
"""

from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
import sqlite3
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bulk_paths import bulk_db_path, get_bulk_data_directory

app = Flask(__name__)

# Configuration
DB_PATH = str(bulk_db_path())
BULK_DIR = Path(get_bulk_data_directory())
PORT = 8080
HOST = "0.0.0.0"  # Listen on all interfaces (Tailscale will handle security)


# Enable CORS for all routes
@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "ok",
            "database": os.path.exists(DB_PATH),
            "db_size_mb": (
                os.path.getsize(DB_PATH) / (1024 * 1024)
                if os.path.exists(DB_PATH)
                else 0
            ),
        }
    )


@app.route("/api/search", methods=["GET", "POST"])
def search_cards():
    """
    Search for cards by name, set, type, etc.

    Query parameters:
        name: Card name (partial match)
        set_code: Set code (exact match)
        type_line: Type line (partial match)
        rarity: Rarity (exact match)
        colors: Color identity (exact match)
        lang: Language code (default: en)
        limit: Max results (default: 100)
    """
    # Get parameters from query string or JSON body
    if request.method == "POST":
        params = request.get_json() or {}
    else:
        params = request.args.to_dict()

    name = params.get("name", "")
    set_code = params.get("set_code", "")
    type_line = params.get("type_line", "")
    rarity = params.get("rarity", "")
    colors = params.get("colors", "")
    lang = params.get("lang", "en")
    limit = int(params.get("limit", 100))

    # Build query
    query = "SELECT * FROM prints WHERE 1=1"
    query_params = []

    if name:
        query += " AND name LIKE ?"
        query_params.append(f"%{name}%")

    if set_code:
        query += " AND set_code = ?"
        query_params.append(set_code.lower())

    if type_line:
        query += " AND type_line LIKE ?"
        query_params.append(f"%{type_line}%")

    if rarity:
        query += " AND rarity = ?"
        query_params.append(rarity.lower())

    if colors:
        query += " AND colors = ?"
        query_params.append(colors)

    if lang:
        query += " AND lang = ?"
        query_params.append(lang)

    query += f" LIMIT {limit}"

    # Execute query
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, query_params)

    results = []
    for row in cursor.fetchall():
        results.append(dict(row))

    conn.close()

    return jsonify({"count": len(results), "results": results})


@app.route("/api/card/<card_id>")
def get_card(card_id):
    """Get a specific card by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM prints WHERE id = ?", (card_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify(dict(row))
    else:
        return jsonify({"error": "Card not found"}), 404


@app.route("/api/sets")
def list_sets():
    """List all available sets."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT set_code, set_name
        FROM prints
        ORDER BY set_code
    """
    )

    sets = [{"code": row[0], "name": row[1]} for row in cursor.fetchall()]
    conn.close()

    return jsonify({"count": len(sets), "sets": sets})


@app.route("/api/deck/parse", methods=["POST"])
def parse_deck():
    """
    Parse a deck list and return card data.

    Request body:
        {
            "decklist": "4 Lightning Bolt\n4 Counterspell\n...",
            "prefer_set": "optional set code",
            "lang": "en"
        }
    """
    data = request.get_json()
    decklist = data.get("decklist", "")
    prefer_set = data.get("prefer_set")
    lang = data.get("lang", "en")

    if not decklist:
        return jsonify({"error": "No decklist provided"}), 400

    # Parse deck list
    lines = decklist.strip().split("\n")
    cards = []
    not_found = []

    conn = get_db()
    cursor = conn.cursor()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse "4 Lightning Bolt" or "Lightning Bolt"
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            quantity = int(parts[0])
            card_name = parts[1]
        else:
            quantity = 1
            card_name = line

        # Search for card
        query = "SELECT * FROM prints WHERE name = ? AND lang = ?"
        params = [card_name, lang]

        if prefer_set:
            query += " AND set_code = ?"
            params.append(prefer_set.lower())

        query += " LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()

        if row:
            card_data = dict(row)
            card_data["quantity"] = quantity
            cards.append(card_data)
        else:
            not_found.append({"name": card_name, "quantity": quantity})

    conn.close()

    return jsonify(
        {
            "found": len(cards),
            "not_found": len(not_found),
            "cards": cards,
            "missing": not_found,
        }
    )


@app.route("/api/stats")
def get_stats():
    """Get database statistics."""
    conn = get_db()
    cursor = conn.cursor()

    # Total cards
    cursor.execute("SELECT COUNT(*) FROM prints")
    total_cards = cursor.fetchone()[0]

    # Unique card names
    cursor.execute("SELECT COUNT(DISTINCT name) FROM prints")
    unique_names = cursor.fetchone()[0]

    # Sets
    cursor.execute("SELECT COUNT(DISTINCT set_code) FROM prints")
    total_sets = cursor.fetchone()[0]

    # Languages
    cursor.execute(
        "SELECT lang, COUNT(*) as count FROM prints GROUP BY lang ORDER BY count DESC"
    )
    languages = [{"lang": row[0], "count": row[1]} for row in cursor.fetchall()]

    conn.close()

    return jsonify(
        {
            "total_cards": total_cards,
            "unique_names": unique_names,
            "total_sets": total_sets,
            "languages": languages,
            "database_size_mb": os.path.getsize(DB_PATH) / (1024 * 1024),
        }
    )


@app.route("/images/<path:filename>")
def serve_image(filename):
    """Serve card images (if available)."""
    # This would serve from your local image cache
    # Adjust path as needed
    image_dir = BULK_DIR.parent.parent / "magic-the-gathering" / "shared"
    return send_from_directory(image_dir, filename)


@app.route("/")
def index():
    """Simple API documentation."""
    return jsonify(
        {
            "name": "Proxy Machine Remote Database API",
            "version": "1.0",
            "endpoints": {
                "/health": "Health check",
                "/api/search": "Search cards (GET or POST)",
                "/api/card/<id>": "Get card by ID",
                "/api/sets": "List all sets",
                "/api/deck/parse": "Parse deck list (POST)",
                "/api/stats": "Database statistics",
            },
            "example_search": "/api/search?name=Lightning%20Bolt&lang=en&limit=10",
            "example_deck": {
                "method": "POST",
                "url": "/api/deck/parse",
                "body": {"decklist": "4 Lightning Bolt\n4 Counterspell", "lang": "en"},
            },
        }
    )


def main():
    """Start the server."""
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print(
            'Run: uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"'
        )
        return 1

    print("=" * 60)
    print("Proxy Machine Remote Database Server")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Size: {os.path.getsize(DB_PATH) / (1024 * 1024):.1f} MB")
    print(f"Listening on: http://{HOST}:{PORT}")
    print()
    print("Tailscale IP:", end=" ")
    try:
        import subprocess

        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True
        )
        if result.returncode == 0:
            tailscale_ip = result.stdout.strip()
            print(tailscale_ip)
            print(
                f"\nFriends should use: PM_REMOTE_DB_URL=http://{tailscale_ip}:{PORT}"
            )
        else:
            print("Not available (Tailscale not running?)")
    except Exception:
        print("Not available")

    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    app.run(host=HOST, port=PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
