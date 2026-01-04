#!/usr/bin/env python3
"""Enhanced version of bulk_index.py with progress bars for all-cards database building."""

import os
import json
import sqlite3
import gzip
import sys
import time
from typing import Any, Dict, Iterable

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bulk_paths import bulk_db_path, bulk_file_path, get_bulk_data_directory
from cli import apply_pm_log_overrides  # noqa: E402

# Paths are resolved via bulk_paths to support legacy layouts during migration
BULK_DIR = str(get_bulk_data_directory())
ALL_CARDS_GZ = str(bulk_file_path("all-cards.json.gz"))
ORACLE_GZ = str(bulk_file_path("oracle-cards.json.gz"))
DB_PATH = str(bulk_db_path())

SCHEMA_VERSION = 3


def _slugify(text: str | None) -> str:
    if not text:
        return ""
    return text.lower().replace(" ", "-").replace("'", "").replace(",", "")


def _progress_bar(
    current: int, total: int, prefix: str = "Progress", width: int = 50
) -> str:
    """Generate a progress bar string."""
    if total == 0:
        percent = 100
    else:
        percent = min(100, (current / total) * 100)

    filled = int(width * current // total) if total > 0 else width
    bar = "█" * filled + "░" * (width - filled)

    return f"\r{prefix}: |{bar}| {current}/{total} ({percent:.1f}%)"


def _iter_json_with_progress(json_path: str) -> Iterable[Dict[str, Any]]:
    """Iterate through JSON (gzipped or regular) with progress tracking."""
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    # Get total file size for progress estimation
    file_size = os.path.getsize(json_path)
    print(f"Processing {json_path} ({file_size / (1024**3):.1f} GB)...")

    # Try to detect if file is gzipped or regular JSON
    try:
        with gzip.open(json_path, "rt", encoding="utf-8") as f:
            f.read(1)  # Test if it's gzipped
        is_gzipped = True
    except (OSError, gzip.BadGzipFile):
        is_gzipped = False

    print(f"File format: {'gzipped JSON' if is_gzipped else 'regular JSON'}")

    def get_file_opener(path: str):
        if is_gzipped:
            return gzip.open(path, "rt", encoding="utf-8")
        else:
            return open(path, "r", encoding="utf-8")

    with get_file_opener(json_path) as f:
        data = json.load(f)
        if isinstance(data, list):
            total_cards = len(data)
            print(f"Found {total_cards:,} cards to process...")

            for i, card in enumerate(data):
                if i % 5000 == 0:  # Update every 5000 cards
                    progress = _progress_bar(i, total_cards, "Processing cards")
                    print(progress, end="", flush=True)
                yield card

            # Final progress
            progress = _progress_bar(total_cards, total_cards, "Processing cards")
            print(progress)
            print()  # New line after progress bar
        else:
            yield data


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure the database schema exists."""
    print("Setting up database schema...")
    cur = conn.cursor()
    cur.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prints (
          id TEXT PRIMARY KEY,
          name TEXT,
          name_slug TEXT,
          set_code TEXT,
          collector_number TEXT,
          type_line TEXT,
          is_basic_land INTEGER,
          is_token INTEGER,
          image_url TEXT,
          oracle_id TEXT,
          color_identity TEXT,
          keywords TEXT,
          oracle_text TEXT,
          frame TEXT,
          frame_effects TEXT,
          full_art INTEGER,
          lang TEXT DEFAULT 'en'
        );
    """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS unique_artworks (
          id TEXT PRIMARY KEY,
          name TEXT,
          name_slug TEXT,
          set_code TEXT,
          type_line TEXT,
          is_basic_land INTEGER,
          is_token INTEGER,
          image_url TEXT
        );
    """
    )

    # Create indexes for performance
    print("Creating database indexes...")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_prints_basic_land ON prints(is_basic_land);"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_token ON prints(is_token);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_name_slug ON prints(name_slug);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_set_code ON prints(set_code);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_lang ON prints(lang);")

    conn.commit()
    print("Database schema ready.")


def build_db_from_all_cards(db_path: str = DB_PATH) -> None:
    """Build database from all-cards.json.gz with progress indicators."""
    print("=== Building Database from All-Cards Data ===")
    start_time = time.time()

    os.makedirs(BULK_DIR, exist_ok=True)

    if os.path.exists(db_path):
        print(f"Removing existing database: {db_path}")
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        cur = conn.cursor()

        batch: list[tuple] = []
        batch_size = 1000
        total_processed = 0
        basic_lands = 0
        non_basic_lands = 0
        tokens = 0
        other_cards = 0

        def flush_batch() -> None:
            nonlocal total_processed
            if not batch:
                return
            cur.executemany(
                """
                INSERT OR REPLACE INTO prints (
                  id, name, name_slug, set_code, collector_number, type_line,
                  is_basic_land, is_token, image_url, oracle_id,
                  color_identity, keywords, oracle_text, frame, frame_effects,
                  full_art, lang
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                batch,
            )
            conn.commit()
            total_processed += len(batch)
            batch.clear()

        print("Processing all cards...")
        for card in _iter_json_with_progress(ALL_CARDS_GZ):
            cid = card.get("id")
            if not cid:
                continue

            name = (card.get("name") or "").strip()
            name_slug = _slugify(name)
            set_code = (card.get("set") or "").lower()
            collector = str(card.get("collector_number") or "").strip()
            type_line = card.get("type_line") or ""
            layout = (card.get("layout") or "").lower()
            lang = card.get("lang") or "en"

            is_token = (
                1 if (layout == "token" or card.get("component") == "token") else 0
            )
            is_basic = 1 if "basic land" in type_line.lower() else 0

            # Track statistics
            if is_basic:
                basic_lands += 1
            elif is_token:
                tokens += 1
            elif "land" in type_line.lower():
                non_basic_lands += 1
            else:
                other_cards += 1

            # Extract image URL
            image_url = None
            uris = card.get("image_uris") or {}
            if isinstance(uris, dict):
                image_url = uris.get("png") or uris.get("normal") or uris.get("large")
            if not image_url:
                faces = card.get("card_faces") or []
                if isinstance(faces, list) and faces:
                    face0 = faces[0]
                    f_uris = (
                        face0.get("image_uris") or {} if isinstance(face0, dict) else {}
                    )
                    if isinstance(f_uris, dict):
                        image_url = (
                            f_uris.get("png")
                            or f_uris.get("normal")
                            or f_uris.get("large")
                        )

            # Oracle data
            oracle_id = card.get("oracle_id")
            color_identity = json.dumps(card.get("color_identity") or [])
            keywords = json.dumps(card.get("keywords") or [])
            oracle_text = card.get("oracle_text") or ""
            frame = card.get("frame") or ""
            frame_effects = json.dumps(card.get("frame_effects") or [])
            full_art = 1 if card.get("full_art") else 0

            batch.append(
                (
                    cid,
                    name,
                    name_slug,
                    set_code,
                    collector,
                    type_line,
                    is_basic,
                    is_token,
                    image_url,
                    oracle_id,
                    color_identity,
                    keywords,
                    oracle_text,
                    frame,
                    frame_effects,
                    full_art,
                    lang,
                )
            )

            if len(batch) >= batch_size:
                flush_batch()

        # Final flush
        flush_batch()

        # Create final indexes and optimize
        print("Optimizing database...")
        cur.execute("ANALYZE;")
        cur.execute("VACUUM;")
        conn.commit()

        end_time = time.time()
        duration = end_time - start_time

        print("\n=== Database Build Complete ===")
        print(f"Total time: {duration:.1f} seconds")
        print(f"Total cards processed: {total_processed:,}")
        print(f"Basic lands: {basic_lands:,}")
        print(f"Non-basic lands: {non_basic_lands:,}")
        print(f"Tokens: {tokens:,}")
        print(f"Other cards: {other_cards:,}")
        print(f"Database size: {os.path.getsize(db_path) / (1024**2):.1f} MB")
        print(f"Database location: {db_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    apply_pm_log_overrides()

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build_db_from_all_cards()
    else:
        print("Usage: python bulk_index_progress.py build")
