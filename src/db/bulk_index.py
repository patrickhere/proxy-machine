"""
Bulk index builder and query interface for Scryfall data.
"""

import gzip
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from bulk_paths import bulk_db_path, bulk_file_path, get_bulk_data_directory

# Disk-based caching for query results
try:
    from diskcache import Cache
    from functools import wraps

    query_cache = Cache(".cache/db_queries", size_limit=100_000_000)  # 100MB cache
    CACHE_ENABLED = True

    def cached_query(expire=3600):
        """Decorator to cache query results for specified time (default 1 hour)."""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                cache_key = (
                    f"{func.__name__}:{repr(args)}:{repr(sorted(kwargs.items()))}"
                )

                # Check cache first
                if cache_key in query_cache:
                    return query_cache.get(cache_key)

                # Execute query
                result = func(*args, **kwargs)

                # Store in cache
                query_cache.set(cache_key, result, expire=expire)

                return result

            return wrapper

        return decorator

except ImportError:
    query_cache = None  # type: ignore
    CACHE_ENABLED = False

    def cached_query(expire=3600):
        """No-op decorator when caching unavailable."""

        def decorator(func):
            return func

        return decorator


# Expected schema version - must match database
EXPECTED_SCHEMA_VERSION = 6  # Added card_relationships table

# Paths are resolved via bulk_paths to support legacy layouts during migration
BULK_DIR = str(get_bulk_data_directory())
ALL_CARDS_GZ = str(bulk_file_path("all-cards.json.gz"))
ORACLE_GZ = str(bulk_file_path("oracle-cards.json.gz"))
DB_PATH = str(bulk_db_path())

SCHEMA_VERSION = 6  # Added card_relationships table


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create SQLite connection with foreign keys enabled.

    This ensures referential integrity is enforced for all operations.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _slugify(text: str | None) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_"}:
            out.append("_")
        else:
            # drop accents/punct
            pass
    # collapse repeats
    s = "".join(out)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _iter_json_gz(path: str) -> Iterable[Dict[str, Any]]:
    if not os.path.exists(path):
        return

    def _iter_from_handle(f) -> Iterable[Dict[str, Any]]:
        # Peek a small chunk to detect format, tolerating leading whitespace/BOM
        head = f.read(4096)
        f.seek(0)
        if not head:
            return
        first_non_ws = None
        for ch in head:
            if ch == "\ufeff":
                continue
            if ch.isspace():
                continue
            first_non_ws = ch
            break
        if first_non_ws == "[":
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                f.seek(0)
            else:
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            yield item
                return
        if first_non_ws == "{":
            # Object wrapper, e.g., {"data": [...]}
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    arr = data.get("data") or data.get("cards")
                    if isinstance(arr, list):
                        for item in arr:
                            if isinstance(item, dict):
                                yield item
                        return
                    if data:
                        yield data  # type: ignore[generator-type]
                        return
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            yield item
                    return
            except json.JSONDecodeError:
                f.seek(0)
        # NDJSON fallback
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line in {"[", "]", "]]"}:
                continue
            if line.endswith(","):
                line = line[:-1].strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj

    # Try gzip first, then fall back to plain text if gzip fails
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            yield from _iter_from_handle(f)
            return
    except OSError:
        pass
    try:
        with open(path, "rt", encoding="utf-8") as f:
            yield from _iter_from_handle(f)
            return
    except OSError:
        return


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    # Each PRAGMA must be executed separately in sqlite3
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prints (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          name_slug TEXT NOT NULL,
          set_code TEXT NOT NULL,
          collector_number TEXT,
          type_line TEXT,
          is_basic_land INTEGER NOT NULL DEFAULT 0,
          is_token INTEGER NOT NULL DEFAULT 0,
          image_url TEXT,
          oracle_id TEXT,
          color_identity TEXT,
          keywords TEXT,
          oracle_text TEXT,
          frame TEXT,
          frame_effects TEXT,
          full_art INTEGER NOT NULL DEFAULT 0,
          lang TEXT NOT NULL DEFAULT 'en',
          artist TEXT,
          rarity TEXT,
          cmc REAL,
          mana_cost TEXT,
          colors TEXT,
          border_color TEXT,
          layout TEXT,
          released_at TEXT,
          set_name TEXT,
          prices TEXT,
          legalities TEXT,
          produced_mana TEXT,
          illustration_id TEXT,
          promo INTEGER NOT NULL DEFAULT 0,
          textless INTEGER NOT NULL DEFAULT 0,
          power TEXT,
          toughness TEXT
        );
        """
    )
    # Backfill columns when upgrading existing DBs
    cur.execute("PRAGMA table_info('prints');")
    cols = {row[1] for row in cur.fetchall()}
    desired = [
        ("frame", "TEXT", None),
        ("frame_effects", "TEXT", None),
        ("full_art", "INTEGER NOT NULL DEFAULT 0", 0),
        ("lang", "TEXT NOT NULL DEFAULT 'en'", "en"),
        ("artist", "TEXT", None),
        ("rarity", "TEXT", None),
        ("cmc", "REAL", None),
        ("mana_cost", "TEXT", None),
        ("colors", "TEXT", None),
        ("border_color", "TEXT", None),
        ("layout", "TEXT", None),
        ("released_at", "TEXT", None),
        ("set_name", "TEXT", None),
        ("prices", "TEXT", None),
        ("legalities", "TEXT", None),
        ("produced_mana", "TEXT", None),
        ("illustration_id", "TEXT", None),
        ("promo", "INTEGER NOT NULL DEFAULT 0", 0),
        ("textless", "INTEGER NOT NULL DEFAULT 0", 0),
        ("all_parts", "TEXT", None),  # JSON array of related cards/tokens
        ("power", "TEXT", None),
        ("toughness", "TEXT", None),
    ]
    for col, decl, _default in desired:
        if col not in cols:
            cur.execute(f"ALTER TABLE prints ADD COLUMN {col} {decl};")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_set ON prints(set_code);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_name_slug ON prints(name_slug);")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_prints_is_basic ON prints(is_basic_land);"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_type ON prints(type_line);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_lang ON prints(lang);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_rarity ON prints(rarity);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_artist ON prints(artist);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_cmc ON prints(cmc);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_layout ON prints(layout);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prints_frame ON prints(frame);")
    # Unique artworks table (from unique-artwork bulk dump)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS unique_artworks (
          id TEXT PRIMARY KEY,
          oracle_id TEXT,
          illustration_id TEXT,
          name TEXT,
          name_slug TEXT,
          set_code TEXT,
          collector_number TEXT,
          type_line TEXT,
          image_url TEXT,
          artist TEXT,
          frame TEXT,
          frame_effects TEXT,
          full_art INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_artworks_oracle ON unique_artworks(oracle_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_artworks_illustration ON unique_artworks(illustration_id);"
    )

    # Source files tracking for incremental updates (ETag-based)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS source_files (
          name TEXT PRIMARY KEY,
          etag TEXT,
          last_modified TEXT,
          sha256 TEXT,
          imported_at TEXT
        );
        """
    )

    # Token creation relationships (from all_parts field)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS created_tokens (
          card_id TEXT NOT NULL,
          token_id TEXT NOT NULL,
          source TEXT DEFAULT 'all_parts',
          confidence REAL DEFAULT 1.0,
          PRIMARY KEY (card_id, token_id)
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_created_tokens_card ON created_tokens(card_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_created_tokens_token ON created_tokens(token_id);"
    )

    # Card relationships (all types from all_parts field)
    # Tracks: combo_piece (MDFC/adventure/split), meld_part, meld_result, token
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS card_relationships (
          source_card_id TEXT NOT NULL,
          related_card_id TEXT NOT NULL,
          relationship_type TEXT NOT NULL,
          related_card_name TEXT,
          PRIMARY KEY (source_card_id, related_card_id, relationship_type)
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_relationships_source ON card_relationships(source_card_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_relationships_related ON card_relationships(related_card_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_relationships_type ON card_relationships(relationship_type);"
    )

    # Asset metadata for quality scoring and duplicate detection
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
          path TEXT PRIMARY KEY,
          phash TEXT,
          dhash TEXT,
          width INTEGER,
          height INTEGER,
          quality_score REAL,
          file_size INTEGER,
          created_at TEXT
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_phash ON assets(phash);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assets_dhash ON assets(dhash);")

    # Asset aliases for duplicate tracking
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_aliases (
          alias_path TEXT PRIMARY KEY,
          canonical_path TEXT NOT NULL,
          similarity_score REAL,
          FOREIGN KEY (canonical_path) REFERENCES assets(path)
        );
        """
    )

    # FTS5 virtual table for fast text search over prints
    try:
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS prints_fts USING fts5(
              name, oracle_text, type_line, set_code, name_slug,
              content='prints', content_rowid='rowid'
            );
            """
        )
    except sqlite3.DatabaseError:
        # FTS5 not available in this SQLite build; proceed without it
        pass
    cur.execute(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def _load_oracle_map() -> dict[str, dict]:
    oracle: dict[str, dict] = {}
    for card in _iter_json_gz(ORACLE_GZ):
        oid = card.get("oracle_id")
        if not oid:
            continue
        oracle[oid] = {
            "oracle_text": card.get("oracle_text"),
            "keywords": card.get("keywords") or [],
            "color_identity": card.get("color_identity") or [],
            "type_line": card.get("type_line"),
            "oracle_name": card.get("name"),
        }
    return oracle


def _populate_card_relationships(conn: sqlite3.Connection) -> None:
    """Populate card_relationships table from all_parts field in prints table.

    Extracts all relationship types: combo_piece, meld_part, meld_result, token.
    """
    cur = conn.cursor()

    # Clear existing relationships
    cur.execute("DELETE FROM card_relationships;")

    # Get all cards with all_parts data
    cur.execute(
        "SELECT id, all_parts FROM prints WHERE all_parts IS NOT NULL AND all_parts != '[]';"
    )

    relationship_batch = []
    batch_size = 1000
    total_relationships = 0

    for row in cur.fetchall():
        card_id, all_parts_json = row

        try:
            all_parts = json.loads(all_parts_json)
        except json.JSONDecodeError:
            continue

        if not isinstance(all_parts, list):
            continue

        for part in all_parts:
            if not isinstance(part, dict):
                continue

            related_id = part.get("id")
            related_name = part.get("name", "")
            component = part.get("component", "")

            # Skip if no ID or component
            if not related_id or not component:
                continue

            # Skip self-references
            if related_id == card_id:
                continue

            relationship_batch.append((card_id, related_id, component, related_name))

            if len(relationship_batch) >= batch_size:
                cur.executemany(
                    "INSERT OR IGNORE INTO card_relationships (source_card_id, related_card_id, relationship_type, related_card_name) VALUES (?,?,?,?)",
                    relationship_batch,
                )
                total_relationships += len(relationship_batch)
                relationship_batch.clear()

    # Flush remaining
    if relationship_batch:
        cur.executemany(
            "INSERT OR IGNORE INTO card_relationships (source_card_id, related_card_id, relationship_type, related_card_name) VALUES (?,?,?,?)",
            relationship_batch,
        )
        total_relationships += len(relationship_batch)

    conn.commit()

    # Report statistics
    cur.execute("SELECT COUNT(*) FROM card_relationships;")
    count = cur.fetchone()[0]

    cur.execute(
        "SELECT relationship_type, COUNT(*) FROM card_relationships GROUP BY relationship_type ORDER BY COUNT(*) DESC;"
    )
    type_counts = cur.fetchall()

    print(f"    Populated {count:,} card relationships")
    for rel_type, rel_count in type_counts:
        print(f"      {rel_type}: {rel_count:,}")


def build_db_from_bulk_json(db_path: str = DB_PATH) -> None:
    print("Building bulk database from JSON data...")
    os.makedirs(BULK_DIR, exist_ok=True)

    # Check available disk space before starting
    import shutil

    free_bytes = shutil.disk_usage(BULK_DIR).free
    free_gb = free_bytes / (1024**3)
    print(f"  Available disk space: {free_gb:.1f} GB")
    if free_gb < 3.0:
        print("⚠️  WARNING: Less than 3GB available. Database build may fail.")

    conn = _get_connection(db_path)
    try:
        print("  Initializing database schema...")
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM prints;")
        cur.execute("DELETE FROM unique_artworks;")
        conn.commit()

        print("  Loading oracle data...")
        oracle_map = _load_oracle_map()
        oracle_count = len(oracle_map)
        print(f"    Loaded {oracle_count:,} oracle entries")

        batch: list[tuple] = []
        batch_size = 500  # Reduced from 1000 for lower memory usage

        def flush() -> None:
            if not batch:
                return
            cur.executemany(
                """
                INSERT OR REPLACE INTO prints (
                  id, name, name_slug, set_code, collector_number, type_line,
                  is_basic_land, is_token, image_url, oracle_id,
                  color_identity, keywords, oracle_text, frame, frame_effects, full_art, lang,
                  artist, rarity, cmc, mana_cost, colors, border_color, layout,
                  released_at, set_name, prices, legalities, produced_mana,
                  illustration_id, promo, textless, all_parts,
                  power, toughness
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                batch,
            )
            conn.commit()
            batch.clear()

        print("  Processing card data from all-cards bulk JSON...")
        total_cards = 0
        progress_interval = 10000  # Report progress every 10k cards

        for card in _iter_json_gz(ALL_CARDS_GZ):
            cid = card.get("id")
            if not cid:
                continue
            total_cards += 1

            # Progress reporting
            if total_cards % progress_interval == 0:
                print(f"    Processed {total_cards:,} cards...")
            name = (card.get("name") or "").strip()
            name_slug = _slugify(name)
            set_code = (card.get("set") or "").lower()
            collector = str(card.get("collector_number") or "").strip()
            type_line = card.get("type_line") or ""
            # Add a check for the "layout" key in the card data
            layout = (card.get("layout") or "").lower()
            is_token = (
                1 if (layout == "token" or card.get("component") == "token") else 0
            )
            is_basic = 1 if "basic land" in type_line.lower() else 0

            image_url = None
            uris = card.get("image_uris") or {}
            if isinstance(uris, dict):
                image_url = uris.get("png") or uris.get("normal") or uris.get("large")
            # Prefer the Land face for double-faced cards (DFC) when present
            faces = card.get("card_faces") or []
            land_face = None
            if isinstance(faces, list) and faces:
                for face in faces:
                    if isinstance(face, dict):
                        f_type = (face.get("type_line") or "").lower()
                        if "land" in f_type:
                            land_face = face
                            break
            if land_face:
                # Use the land face art, falling back to front if URLs missing
                f_uris = (
                    land_face.get("image_uris") if isinstance(land_face, dict) else None
                )
                if isinstance(f_uris, dict):
                    image_url = f_uris.get("png") or f_uris.get("normal") or image_url
                # Also use the land face name for better folder/file naming
                lf_name = (land_face.get("name") or "").strip()
                if lf_name:
                    name = lf_name
                    name_slug = _slugify(name)

            oracle_id = card.get("oracle_id")
            o = oracle_map.get(oracle_id or "")
            color_identity = json.dumps(o.get("color_identity") if o else [])
            keywords = json.dumps(o.get("keywords") if o else [])
            oracle_text = o.get("oracle_text") if o else None
            frame = card.get("frame")
            frame_effects = json.dumps(card.get("frame_effects") or [])
            full_art = 1 if card.get("full_art") else 0

            lang = card.get("lang", "en")
            artist = card.get("artist")
            rarity = card.get("rarity")
            cmc = card.get("cmc", 0.0)
            mana_cost = card.get("mana_cost")
            colors = json.dumps(card.get("colors") or [])
            border_color = card.get("border_color")
            layout = card.get("layout")
            released_at = card.get("released_at")
            set_name = card.get("set_name")
            prices = json.dumps(card.get("prices") or {})
            legalities = json.dumps(card.get("legalities") or {})
            produced_mana = json.dumps(card.get("produced_mana") or [])
            illustration_id = card.get("illustration_id")
            promo = 1 if card.get("promo") else 0
            textless = 1 if card.get("textless") else 0
            all_parts = json.dumps(card.get("all_parts") or [])

            # Power/toughness (primarily for creature tokens)
            power = card.get("power")
            toughness = card.get("toughness")

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
                    artist,
                    rarity,
                    cmc,
                    mana_cost,
                    colors,
                    border_color,
                    layout,
                    released_at,
                    set_name,
                    prices,
                    legalities,
                    produced_mana,
                    illustration_id,
                    promo,
                    textless,
                    all_parts,
                    power,
                    toughness,
                )
            )
            if len(batch) >= batch_size:
                flush()
        flush()
        print(f"    Completed processing {total_cards:,} cards")

        # Rebuild FTS over prints
        print("  Building full-text search index...")
        try:
            cur.execute("DELETE FROM prints_fts;")
            cur.execute(
                "INSERT INTO prints_fts(rowid,name,oracle_text,type_line,set_code,name_slug) "
                "SELECT rowid,name,oracle_text,type_line,set_code,name_slug FROM prints;"
            )
            conn.commit()
        except sqlite3.DatabaseError:
            # FTS not available or disabled, continue without failing build
            pass

        # Populate card relationships from all_parts
        print("  Populating card relationships...")
        _populate_card_relationships(conn)

        # All artwork data is now included in all-cards.json.gz
        # No separate unique artwork processing needed

        # metadata
        meta = {
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        cur.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
            ("build_info", json.dumps(meta)),
        )
        conn.commit()
        # Simple build summary
        cur.execute("SELECT COUNT(*) FROM prints;")
        count = cur.fetchone()[0]
        try:
            a_sz = os.path.getsize(ALL_CARDS_GZ) if os.path.exists(ALL_CARDS_GZ) else 0
        except OSError:
            a_sz = 0
        try:
            o_sz = os.path.getsize(ORACLE_GZ) if os.path.exists(ORACLE_GZ) else 0
        except OSError:
            o_sz = 0
        print("Database build completed successfully!")
        print("  Summary:")
        print(f"    Cards processed: {total_cards:,}")
        print(f"    Oracle entries: {oracle_count:,}")
        print(f"    Database rows: {count:,}")
        print(f"    Data sources: all-cards.gz={a_sz:,}B, oracle.gz={o_sz:,}B")

        # Optional debug preview when no records parsed
        want_debug = os.environ.get("PM_BULK_DEBUG", "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if want_debug and (total_cards == 0 or oracle_count == 0):

            def _peek(path: str) -> str:
                try:
                    with gzip.open(path, "rb") as fh:
                        raw = fh.read(256)
                except Exception:
                    try:
                        with open(path, "rb") as fh:
                            raw = fh.read(256)
                    except Exception:
                        return "<unreadable>"
                try:
                    return raw.decode("utf-8", errors="replace")
                except Exception:
                    return str(raw[:64]) + " ..."

            if total_cards == 0:
                head = _peek(ALL_CARDS_GZ)
                print("[debug] all-cards head sample:\n" + head)
            if oracle_count == 0:
                head = _peek(ORACLE_GZ)
                print("[debug] oracle-cards head sample:\n" + head)
    finally:
        conn.close()


def verify(db_path: str = DB_PATH) -> int:
    """Return 0 if the DB looks healthy, non-zero otherwise.

    Checks:
    - DB exists and is readable
    - schema_version matches SCHEMA_VERSION
    - prints table has rows
    - FTS table presence
    - Bulk JSON files present (warn-only if missing)
    """
    if not os.path.exists(db_path):
        print("DB not found. Build it first.")
        return 2
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        ok = True
        # prints count
        try:
            cur.execute("SELECT COUNT(*) FROM prints;")
            prints = int(cur.fetchone()[0])
        except Exception as e:
            print(f"FAIL: cannot read prints table: {e}")
            return 3

        # schema version
        cur.execute("SELECT value FROM metadata WHERE key='schema_version';")
        row = cur.fetchone()
        try:
            schema_version = int(row[0]) if row and row[0] is not None else None
        except Exception:
            schema_version = None
        has_schema = schema_version == SCHEMA_VERSION

        # FTS table present
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='prints_fts';"
        )
        has_fts = bool(cur.fetchone()[0])

        # unique_artworks (informational)
        ua_count = 0
        try:
            cur.execute("SELECT COUNT(*) FROM unique_artworks;")
            ua_count = int(cur.fetchone()[0])
        except sqlite3.DatabaseError:
            ua_count = 0

        # Bulk files (warn only)
        def _size(p: str) -> int:
            try:
                return os.path.getsize(p) if os.path.exists(p) else 0
            except OSError:
                return 0

        a_sz = _size(ALL_CARDS_GZ)
        o_sz = _size(ORACLE_GZ)

        # Report
        print("DB Verify Summary")
        print(f"- path: {db_path}")
        print(f"- prints: {prints} ({'OK' if prints > 0 else 'FAIL'})")
        print(
            f"- schema_version: {schema_version} expected={SCHEMA_VERSION} ({'OK' if has_schema else 'FAIL'})"
        )
        print(
            f"- FTS5: {'present' if has_fts else 'missing'} ({'OK' if has_fts else 'WARN'})"
        )
        print(f"- unique_artworks: {ua_count}")
        print(f"- bulk files: all-cards.gz={a_sz}B oracle.gz={o_sz}B")

        if prints <= 0:
            ok = False
        if not has_schema:
            ok = False
        return 0 if ok else 3
    finally:
        conn.close()


def _row_to_art(entry: tuple) -> Dict[str, Any]:
    (
        uid,
        oracle_id,
        illustration_id,
        name,
        name_slug,
        set_code,
        collector,
        type_line,
        image_url,
        artist,
        frame,
        frame_effects,
        full_art,
    ) = entry
    try:
        effects = json.loads(frame_effects) if frame_effects else []
    except Exception:
        effects = []
    return {
        "id": uid,
        "oracle_id": oracle_id,
        "illustration_id": illustration_id,
        "name": name,
        "name_slug": name_slug,
        "set": set_code,
        "collector_number": collector,
        "type_line": type_line,
        "image_url": image_url,
        "artist": artist,
        "frame": frame,
        "frame_effects": effects,
        "full_art": bool(full_art),
    }


def query_unique_artworks(
    oracle_id: str | None = None,
    illustration_id: str | None = None,
    set_filter: str | None = None,
    limit: int | None = None,
    db_path: str = DB_PATH,
    *,
    name_filter: str | None = None,
    artist_filter: str | None = None,
    frame_filter: str | None = None,
    frame_effect_contains: str | None = None,
    full_art: bool | None = None,
) -> list[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["1=1"]
        params: list[Any] = []
        if oracle_id:
            clauses.append("oracle_id=?")
            params.append(oracle_id)
        if illustration_id:
            clauses.append("illustration_id=?")
            params.append(illustration_id)
        if set_filter:
            clauses.append("set_code=?")
            params.append((set_filter or "").lower())
        if name_filter:
            clauses.append("name_slug LIKE ?")
            params.append(f"%{_slugify(name_filter)}%")
        if artist_filter:
            clauses.append("lower(coalesce(artist,'')) LIKE ?")
            params.append(f"%{(artist_filter or '').strip().lower()}%")
        if frame_filter:
            clauses.append("frame=?")
            params.append(frame_filter)
        if frame_effect_contains:
            clauses.append("lower(coalesce(frame_effects,'')) LIKE ?")
            params.append(f"%{(frame_effect_contains or '').strip().lower()}%")
        if full_art is not None:
            clauses.append("full_art=?")
            params.append(1 if full_art else 0)
        sql = (
            "SELECT id,oracle_id,illustration_id,name,name_slug,set_code,collector_number,type_line,"
            "image_url,artist,frame,frame_effects,full_art FROM unique_artworks WHERE "
            + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        return [_row_to_art(r) for r in cur.fetchall()]
    finally:
        conn.close()


def count_unique_artworks(
    oracle_id: str | None = None,
    illustration_id: str | None = None,
    set_filter: str | None = None,
    db_path: str = DB_PATH,
    *,
    name_filter: str | None = None,
    artist_filter: str | None = None,
    frame_filter: str | None = None,
    frame_effect_contains: str | None = None,
    full_art: bool | None = None,
) -> int:
    if not os.path.exists(db_path):
        return 0
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["1=1"]
        params: list[Any] = []
        if oracle_id:
            clauses.append("oracle_id=?")
            params.append(oracle_id)
        if illustration_id:
            clauses.append("illustration_id=?")
            params.append(illustration_id)
        if set_filter:
            clauses.append("set_code=?")
            params.append((set_filter or "").lower())
        if name_filter:
            clauses.append("name_slug LIKE ?")
            params.append(f"%{_slugify(name_filter)}%")
        if artist_filter:
            clauses.append("lower(coalesce(artist,'')) LIKE ?")
            params.append(f"%{(artist_filter or '').strip().lower()}%")
        if frame_filter:
            clauses.append("frame=?")
            params.append(frame_filter)
        if frame_effect_contains:
            clauses.append("lower(coalesce(frame_effects,'')) LIKE ?")
            params.append(f"%{(frame_effect_contains or '').strip().lower()}%")
        if full_art is not None:
            clauses.append("full_art=?")
            params.append(1 if full_art else 0)
        sql = "SELECT COUNT(*) FROM unique_artworks WHERE " + " AND ".join(clauses)
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def query_oracle_fts(
    query: str,
    set_filter: str | None = None,
    include_tokens: bool = False,
    limit: int | None = None,
    db_path: str = DB_PATH,
) -> list[Dict[str, Any]]:
    """FTS5-backed search over prints if available; falls back to LIKE query.

    Matches against name, oracle_text, and type_line.
    """
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        # Verify FTS table exists
        try:
            cur.execute("SELECT 1 FROM prints_fts LIMIT 1;")
            has_fts = True
        except sqlite3.DatabaseError:
            has_fts = False
        if not has_fts:
            return query_oracle_text(query, set_filter, include_tokens, limit, db_path)

        where_clauses = ["prints.rowid = prints_fts.rowid"]
        params: list[Any] = []
        # Use simple FTS match. For complex syntax, we could preprocess later.
        q = (query or "").strip()
        where_clauses.append("prints_fts MATCH ?")
        params.append(q)
        if not include_tokens:
            where_clauses.append("prints.is_token=0")
        if set_filter:
            where_clauses.append("prints.set_code=?")
            params.append((set_filter or "").lower())
        sql = (
            "SELECT prints.id,prints.name,prints.name_slug,prints.set_code,prints.collector_number,"
            "prints.type_line,prints.is_basic_land,prints.is_token,prints.image_url,prints.oracle_id,prints.color_identity,prints.keywords,prints.oracle_text,prints.lang "
            "FROM prints JOIN prints_fts ON prints.rowid=prints_fts.rowid WHERE "
            + " AND ".join(where_clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _token_subtype_from_type_line(type_line: str) -> str:
    if "—" in (type_line or ""):
        return type_line.split("—", 1)[1].strip()
    if " - " in (type_line or ""):
        return type_line.split(" - ", 1)[1].strip()
    return (type_line or "Token").replace("Token", "").strip() or "Token"


def _row_to_entry(row: tuple) -> Dict[str, Any]:
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
        artist,
        rarity,
        cmc,
        mana_cost,
        colors,
        border_color,
        layout,
        released_at,
        set_name,
        prices,
        legalities,
        produced_mana,
        illustration_id,
        promo,
        textless,
        all_parts,
    ) = row
    try:
        ci = json.loads(color_identity) if color_identity else []
    except Exception:
        ci = []
    try:
        kw = json.loads(keywords) if keywords else []
    except Exception:
        kw = []
    # Parse JSON fields safely
    try:
        colors_list = json.loads(colors) if colors else []
    except Exception:
        colors_list = []
    try:
        prices_dict = json.loads(prices) if prices else {}
    except Exception:
        prices_dict = {}
    try:
        legalities_dict = json.loads(legalities) if legalities else {}
    except Exception:
        legalities_dict = {}
    try:
        produced_mana_list = json.loads(produced_mana) if produced_mana else []
    except Exception:
        produced_mana_list = []

    # Parse frame_effects JSON field
    try:
        frame_effects_list = json.loads(frame_effects) if frame_effects else []
    except Exception:
        frame_effects_list = []

    # Parse all_parts JSON field
    try:
        all_parts_list = json.loads(all_parts) if all_parts else []
    except Exception:
        all_parts_list = []

    entry: Dict[str, Any] = {
        "id": cid,
        "name": name,
        "name_slug": name_slug,
        "set": set_code,
        "set_code": set_code,
        "collector_number": collector,
        "type_line": type_line,
        "is_basic_land": bool(is_basic),
        "is_token": bool(is_token),
        "image_url": image_url,
        "oracle_id": oracle_id,
        "color_identity": ci,
        "keywords": kw,
        "oracle_keywords": kw,
        "oracle_text": oracle_text,
        "frame": frame,
        "frame_effects": frame_effects_list,
        "full_art": bool(full_art),
        "lang": lang,
        "artist": artist,
        "rarity": rarity,
        "cmc": cmc,
        "mana_cost": mana_cost,
        "colors": colors_list,
        "border_color": border_color,
        "layout": layout,
        "released_at": released_at,
        "set_name": set_name,
        "prices": prices_dict,
        "legalities": legalities_dict,
        "produced_mana": produced_mana_list,
        "illustration_id": illustration_id,
        "promo": bool(promo),
        "textless": bool(textless),
        "all_parts": all_parts_list,
    }
    if bool(is_token):
        subtype = _token_subtype_from_type_line(type_line or "Token")
        entry["token_subtype"] = subtype
        entry["token_subtype_slug"] = _slugify(subtype)
    return entry


@cached_query(expire=3600)  # Cache for 1 hour
def query_basic_lands(
    limit: int | None = None,
    db_path: str = DB_PATH,
    *,
    lang_filter: str | list[str] | None = None,
    set_filter: str | None = None,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    cmc_filter: float | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    fullart_only: bool = False,
) -> list[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["is_basic_land=1", "image_url IS NOT NULL"]
        params: list = []

        # Add filtering clauses
        if lang_filter:
            if isinstance(lang_filter, list):
                # Multiple languages: use IN clause
                placeholders = ",".join("?" * len(lang_filter))
                clauses.append(f"lang IN ({placeholders})")
                params.extend(lang_filter)
            else:
                # Single language
                clauses.append("lang=?")
                params.append(lang_filter)
        if set_filter:
            clauses.append("set_code=?")
            params.append(set_filter.lower())
        if artist_filter:
            clauses.append("artist LIKE ?")
            params.append(f"%{artist_filter}%")
        if rarity_filter:
            clauses.append("rarity=?")
            params.append(rarity_filter)
        if cmc_filter is not None:
            clauses.append("cmc=?")
            params.append(cmc_filter)
        if layout_filter:
            clauses.append("layout=?")
            params.append(layout_filter)
        if frame_filter:
            clauses.append("frame=?")
            params.append(frame_filter)
        if fullart_only:
            clauses.append("full_art=1")

        sql = (
            "SELECT id,name,name_slug,set_code,collector_number,type_line,is_basic_land,is_token,"
            "image_url,oracle_id,color_identity,keywords,oracle_text,frame,frame_effects,full_art,lang,"
            "artist,rarity,cmc,mana_cost,colors,border_color,layout,released_at,set_name,"
            "prices,legalities,produced_mana,illustration_id,promo,textless,all_parts "
            "FROM prints WHERE " + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, params)
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


@cached_query(expire=3600)  # Cache for 1 hour
def query_non_basic_lands(
    limit: int | None = None,
    db_path: str = DB_PATH,
    *,
    lang_filter: str | list[str] | None = None,
    set_filter: str | None = None,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    cmc_filter: float | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    fullart_only: bool = False,
) -> list[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["is_basic_land=0", "lower(type_line) LIKE '%land%'"]
        params: list = []

        # Add filtering clauses
        if lang_filter:
            if isinstance(lang_filter, list):
                # Multiple languages: use IN clause
                placeholders = ",".join("?" * len(lang_filter))
                clauses.append(f"lang IN ({placeholders})")
                params.extend(lang_filter)
            else:
                # Single language
                clauses.append("lang=?")
                params.append(lang_filter)
        if set_filter:
            clauses.append("set_code=?")
            params.append(set_filter.lower())
        if artist_filter:
            clauses.append("artist LIKE ?")
            params.append(f"%{artist_filter}%")
        if rarity_filter:
            clauses.append("rarity=?")
            params.append(rarity_filter)
        if cmc_filter is not None:
            clauses.append("cmc=?")
            params.append(cmc_filter)
        if layout_filter:
            clauses.append("layout=?")
            params.append(layout_filter)
        if frame_filter:
            clauses.append("frame=?")
            params.append(frame_filter)
        if fullart_only:
            clauses.append("full_art=1")

        sql = (
            "SELECT id,name,name_slug,set_code,collector_number,type_line,is_basic_land,is_token,"
            "image_url,oracle_id,color_identity,keywords,oracle_text,frame,frame_effects,full_art,lang,"
            "artist,rarity,cmc,mana_cost,colors,border_color,layout,released_at,set_name,"
            "prices,legalities,produced_mana,illustration_id,promo,textless,all_parts "
            "FROM prints WHERE " + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, params)
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_cards_optimized(
    limit: int | None = None,
    db_path: str = DB_PATH,
    *,
    card_type: str = "any",
    is_token: bool | None = None,
    is_basic_land: bool | None = None,
    name_filter: str | None = None,
    type_line_contains: str | None = None,
    subtype_filter: str | None = None,
    lang_filter: str | list[str] | None = None,
    set_filter: str | None = None,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    colors_filter: str | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    border_color_filter: str | None = None,
    fullart_only: bool = False,
    card_ids: list[str] | None = None,
) -> list[Dict[str, Any]]:
    """Optimized card query with SQL-level filtering.

    Pushes all filters to SQL WHERE clause to minimize memory usage.
    Returns only matching cards instead of loading all 508k cards.
    """
    if not os.path.exists(db_path):
        return []

    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = []
        params: list = []

        # Card type filtering
        if card_type == "basic_land":
            clauses.append("is_basic_land=1")
        elif card_type == "nonbasic_land":
            clauses.append("is_basic_land=0 AND lower(type_line) LIKE '%land%'")
        elif card_type == "token":
            clauses.append("is_token=1")
        elif card_type != "any":
            # Specific card type (creature, planeswalker, etc.)
            clauses.append("lower(type_line) LIKE ?")
            params.append(f"%{card_type.lower()}%")

        # Token/land filtering
        if is_token is not None:
            clauses.append("is_token=?")
            params.append(1 if is_token else 0)

        if is_basic_land is not None:
            clauses.append("is_basic_land=?")
            params.append(1 if is_basic_land else 0)

        # Language filtering
        if lang_filter:
            if isinstance(lang_filter, list):
                placeholders = ",".join(["?" for _ in lang_filter])
                clauses.append(f"lang IN ({placeholders})")
                params.extend(lang_filter)
            else:
                clauses.append("lang=?")
                params.append(lang_filter)

        # Set filtering
        if set_filter:
            clauses.append("lower(set_code)=?")
            params.append(set_filter.lower())

        # Name filtering
        if name_filter:
            clauses.append("lower(name) LIKE ?")
            params.append(f"%{name_filter.lower()}%")

        # Type line filtering
        if type_line_contains:
            clauses.append("lower(type_line) LIKE ?")
            params.append(f"%{type_line_contains.lower()}%")

        # Subtype filtering
        if subtype_filter:
            clauses.append("lower(type_line) LIKE ?")
            params.append(f"%{subtype_filter.lower()}%")

        # Artist filtering
        if artist_filter:
            clauses.append("lower(artist) LIKE ?")
            params.append(f"%{artist_filter.lower()}%")

        # Rarity filtering
        if rarity_filter:
            clauses.append("lower(rarity)=?")
            params.append(rarity_filter.lower())

        # Layout filtering
        if layout_filter:
            clauses.append("layout=?")
            params.append(layout_filter)

        # Frame filtering
        if frame_filter:
            clauses.append("frame=?")
            params.append(frame_filter)

        # Border color filtering
        if border_color_filter:
            clauses.append("border_color=?")
            params.append(border_color_filter)

        # Full art filtering
        if fullart_only:
            clauses.append("full_art=1")

        # Specific card IDs
        if card_ids:
            placeholders = ",".join(["?" for _ in card_ids])
            clauses.append(f"id IN ({placeholders})")
            params.extend(card_ids)

        # Build query
        where_clause = " AND ".join(clauses) if clauses else "1=1"
        query = f"SELECT * FROM prints WHERE {where_clause}"

        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query, params)
        rows = cur.fetchall()

        # Convert to dict format
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]

    finally:
        conn.close()


def query_cards(
    limit: int | None = None,
    db_path: str = DB_PATH,
    *,
    name_filter: str | None = None,
    type_filter: str | None = None,
    lang_filter: str | None = None,
    set_filter: str | None = None,
    artist_filter: str | None = None,
    rarity_filter: str | None = None,
    cmc_filter: float | None = None,
    layout_filter: str | None = None,
    frame_filter: str | None = None,
    fullart_only: bool = False,
    exclude_tokens: bool = False,
    exclude_lands: bool = False,
    colors_filter: list[str] | None = None,
    card_ids: list[str] | None = None,
) -> list[Dict[str, Any]]:
    """Query cards with comprehensive filtering options."""
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["1=1"]  # Base clause
        params: list = []

        # Add filtering clauses
        if name_filter:
            clauses.append("name LIKE ?")
            params.append(f"%{name_filter}%")
        if type_filter:
            clauses.append("lower(type_line) LIKE ?")
            params.append(f"%{type_filter.lower()}%")
        if lang_filter:
            clauses.append("lang=?")
            params.append(lang_filter)
        if set_filter:
            clauses.append("set_code=?")
            params.append(set_filter.lower())
        if artist_filter:
            clauses.append("artist LIKE ?")
            params.append(f"%{artist_filter}%")
        if rarity_filter:
            clauses.append("rarity=?")
            params.append(rarity_filter)
        if cmc_filter is not None:
            clauses.append("cmc=?")
            params.append(cmc_filter)
        if layout_filter:
            clauses.append("layout=?")
            params.append(layout_filter)
        if frame_filter:
            clauses.append("frame=?")
            params.append(frame_filter)
        if fullart_only:
            clauses.append("full_art=1")
        if card_ids:
            placeholders = ",".join("?" for _ in card_ids)
            clauses.append(f"id IN ({placeholders})")
            params.extend(card_ids)
        if exclude_tokens:
            clauses.append("is_token=0")
        if exclude_lands:
            clauses.append("is_basic_land=0 AND lower(type_line) NOT LIKE '%land%'")
        if colors_filter:
            # Colors stored as JSON array, check if any requested color is present
            for color in colors_filter:
                clauses.append("colors LIKE ?")
                params.append(f'%"{color}"%')

        sql = (
            "SELECT id,name,name_slug,set_code,collector_number,type_line,is_basic_land,is_token,"
            "image_url,oracle_id,color_identity,keywords,oracle_text,frame,frame_effects,full_art,lang,"
            "artist,rarity,cmc,mana_cost,colors,border_color,layout,released_at,set_name,"
            "prices,legalities,produced_mana,illustration_id,promo,textless,all_parts "
            "FROM prints WHERE " + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, params)
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


@cached_query(expire=3600)  # Cache for 1 hour
def query_tokens(
    name_filter: str | None = None,
    subtype_filter: str | None = None,
    set_filter: str | None = None,
    limit: int | None = None,
    db_path: str = DB_PATH,
) -> list[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["is_token=1"]
        params: list[Any] = []
        if name_filter:
            clauses.append("name_slug LIKE ?")
            params.append(f"%{_slugify(name_filter)}%")
        if subtype_filter:
            subtype_slug = _slugify(subtype_filter)
            clauses.append("(type_line LIKE ? OR type_line LIKE ?)")
            params.extend([f"%{subtype_slug}%", f"%{subtype_filter}%"])
        if set_filter:
            clauses.append("set_code=?")
            params.append((set_filter or "").lower())
        sql = (
            "SELECT id,name,name_slug,set_code,collector_number,type_line,is_basic_land,is_token,"
            "image_url,oracle_id,color_identity,keywords,oracle_text,frame,frame_effects,full_art,lang,"
            "artist,rarity,cmc,mana_cost,colors,border_color,layout,released_at,set_name,"
            "prices,legalities,produced_mana,illustration_id,promo,textless,all_parts FROM prints WHERE "
            + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_tokens_by_keyword(
    keyword: str,
    set_filter: str | None = None,
    limit: int | None = None,
    db_path: str = DB_PATH,
) -> list[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["is_token=1"]
        params: list[Any] = []
        kw_norm = (keyword or "").strip().lower()
        # keywords column is JSON array text; simplest robust path is to search oracle_text and keywords text blob
        clauses.append(
            "(lower(coalesce(oracle_text,'')) LIKE ? OR lower(coalesce(keywords,'')) LIKE ?)"
        )
        params.extend([f"%{kw_norm}%", f"%{kw_norm}%"])
        if set_filter:
            clauses.append("set_code=?")
            params.append((set_filter or "").lower())
        sql = (
            "SELECT id,name,name_slug,set_code,collector_number,type_line,is_basic_land,is_token,"
            "image_url,oracle_id,color_identity,keywords,oracle_text,frame,frame_effects,full_art,lang,"
            "artist,rarity,cmc,mana_cost,colors,border_color,layout,released_at,set_name,"
            "prices,legalities,produced_mana,illustration_id,promo,textless,all_parts FROM prints WHERE "
            + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_oracle_text(
    query: str,
    set_filter: str | None = None,
    include_tokens: bool = False,
    limit: int | None = None,
    db_path: str = DB_PATH,
) -> list[Dict[str, Any]]:
    if not os.path.exists(db_path):
        return []
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = []
        params: list[Any] = []
        q = (query or "").strip().lower()
        clauses.append(
            "(lower(coalesce(oracle_text,'')) LIKE ? OR lower(coalesce(type_line,'')) LIKE ? OR name_slug LIKE ?)"
        )
        params.extend([f"%{q}%", f"%{q}%", f"%{_slugify(query)}%"])
        if not include_tokens:
            clauses.append("is_token=0")
        if set_filter:
            clauses.append("set_code=?")
            params.append((set_filter or "").lower())
        sql = (
            "SELECT id,name,name_slug,set_code,collector_number,type_line,is_basic_land,is_token,"
            "image_url,oracle_id,color_identity,keywords,oracle_text,frame,frame_effects,full_art,lang,"
            "artist,rarity,cmc,mana_cost,colors,border_color,layout,released_at,set_name,"
            "prices,legalities,produced_mana,illustration_id,promo,textless,all_parts FROM prints WHERE "
            + " AND ".join(clauses)
        )
        if limit and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        cur.execute(sql, tuple(params))
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


def verify_schema_compatibility(db_path: str = DB_PATH) -> None:
    """Ensure code and DB schema versions match.

    Raises RuntimeError if versions don't match or schema_version is missing.
    """
    if not os.path.exists(db_path):
        return  # DB doesn't exist yet, will be created

    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM metadata WHERE key='schema_version'")
        row = cur.fetchone()

        if not row:
            raise RuntimeError(
                "Database missing schema_version metadata.\n"
                "Run 'make bulk-rebuild' to rebuild the database."
            )

        actual_version = int(row[0])
        if actual_version != EXPECTED_SCHEMA_VERSION:
            raise RuntimeError(
                f"Schema version mismatch:\n"
                f"  Code expects: v{EXPECTED_SCHEMA_VERSION}\n"
                f"  Database has: v{actual_version}\n"
                f"Run 'make bulk-rebuild' to update the database."
            )
    finally:
        conn.close()


def vacuum_db(db_path: str = DB_PATH) -> None:
    if not os.path.exists(db_path):
        print(f"No database found at {db_path}")
        return
    print("Starting database maintenance (VACUUM and ANALYZE)...")
    conn = _get_connection(db_path)
    try:
        print("  Running VACUUM (may take several minutes for large databases)...")
        conn.execute("VACUUM;")
        print("  Running ANALYZE (optimizing query performance)...")
        conn.execute("ANALYZE;")
        conn.commit()
    finally:
        conn.close()


def info(db_path: str = DB_PATH) -> None:
    if not os.path.exists(db_path):
        print("DB not found. Build it first.")
        return
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM prints;")
        count = cur.fetchone()[0]
        cur.execute("SELECT value FROM metadata WHERE key='schema_version';")
        row = cur.fetchone()
        schema_version = row[0] if row else "?"
        # unique_artworks count (if table exists) - not used in current system
        # FTS availability
        cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='prints_fts';"
        )
        has_fts = bool(cur.fetchone()[0])
        try:
            a_sz = os.path.getsize(ALL_CARDS_GZ) if os.path.exists(ALL_CARDS_GZ) else 0
        except OSError:
            a_sz = 0
        try:
            o_sz = os.path.getsize(ORACLE_GZ) if os.path.exists(ORACLE_GZ) else 0
        except OSError:
            o_sz = 0
        print(
            f"bulk.db entries: prints={count}; schema_version={schema_version}; FTS5={'yes' if has_fts else 'no'}; all-cards.gz={a_sz}B; oracle.gz={o_sz}B"
        )
    finally:
        conn.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Bulk database management")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("rebuild", help="Rebuild database from bulk JSON files")
    sub.add_parser("vacuum", help="Optimize database (VACUUM + ANALYZE)")
    sub.add_parser("info", help="Show database statistics")
    sub.add_parser("verify", help="Verify database health (exit non-zero on failure)")

    args = parser.parse_args()

    if args.cmd == "rebuild":
        build_db_from_bulk_json(DB_PATH)
    elif args.cmd == "vacuum":
        vacuum_db(DB_PATH)
    elif args.cmd == "info":
        print("Database Information:")
        info(DB_PATH)
    elif args.cmd == "verify":
        raise SystemExit(verify(DB_PATH))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
