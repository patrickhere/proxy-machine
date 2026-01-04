#!/usr/bin/env python3
"""Database optimization utilities - add composite indexes for faster searches."""

import os
import sys
import sqlite3
import time

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


def add_composite_indexes(db_path: str = DB_PATH) -> None:
    """
    Add composite indexes for common query patterns to speed up searches.

    These indexes help with:
    - Set + language queries (fetch-basics, fetch-nonbasics)
    - Type + rarity queries (random card discovery)
    - Artist + set queries (art style matching)
    - Color identity + type queries (deck building)
    """
    if not os.path.exists(db_path):
        print(f"⚠️  Database not found at {db_path}")
        print("   Run 'make bulk-index-build' to create it.")
        return

    print("🔧 Optimizing database with composite indexes...")
    start_time = time.time()

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Composite indexes for common query patterns
        indexes = [
            # Set + language (for land fetching)
            ("idx_prints_set_lang", "prints(set_code, lang)"),
            # Type + rarity (for filtered searches)
            ("idx_prints_type_rarity", "prints(type_line, rarity)"),
            # Artist + set (for art style matching)
            ("idx_prints_artist_set", "prints(artist, set_code)"),
            # Set + rarity + lang (for set exploration)
            ("idx_prints_set_rarity_lang", "prints(set_code, rarity, lang)"),
            # Type + set (for set-specific type searches)
            ("idx_prints_type_set", "prints(type_line, set_code)"),
            # Basic land + lang + set (optimized for land queries)
            ("idx_prints_basic_lang_set", "prints(is_basic_land, lang, set_code)"),
            # Token + lang (for token searches)
            ("idx_prints_token_lang", "prints(is_token, lang)"),
            # Oracle ID + lang (for finding all printings)
            ("idx_prints_oracle_lang", "prints(oracle_id, lang)"),
            # Illustration ID (for finding duplicate art)
            ("idx_prints_illustration", "prints(illustration_id)"),
            # CMC + colors (for mana curve analysis)
            ("idx_prints_cmc_colors", "prints(cmc, colors)"),
        ]

        created = 0
        skipped = 0

        for idx_name, idx_def in indexes:
            try:
                print(f"  Creating {idx_name}...", end=" ", flush=True)
                cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def};")

                # Check if it was actually created or already existed
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                    (idx_name,),
                )
                if cur.fetchone():
                    print("✓")
                    created += 1
                else:
                    print("(already exists)")
                    skipped += 1

            except sqlite3.Error as e:
                print(f"✗ ({e})")

        # Analyze the database to update query planner statistics
        print("\n  Running ANALYZE to update statistics...", end=" ", flush=True)
        cur.execute("ANALYZE;")
        print("✓")

        conn.commit()

        # Get database size
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)

        elapsed = time.time() - start_time

        print("\n✓ Database optimization complete!")
        print(f"  Created: {created} new indexes")
        print(f"  Skipped: {skipped} existing indexes")
        print(f"  Database size: {db_size_mb:.1f} MB")
        print(f"  Time: {elapsed:.1f}s")

    finally:
        conn.close()


def show_index_info(db_path: str = DB_PATH) -> None:
    """Show information about database indexes."""
    if not os.path.exists(db_path):
        print(f"⚠️  Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Get all indexes
        cur.execute(
            """
            SELECT name, tbl_name, sql
            FROM sqlite_master
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            ORDER BY tbl_name, name
            """
        )

        indexes = cur.fetchall()

        print(f"\n📊 Database Indexes ({len(indexes)} total):\n")

        current_table = None
        for name, table, sql in indexes:
            if table != current_table:
                print(f"\n{table}:")
                current_table = table
            print(f"  • {name}")

        # Get table sizes
        print("\n📈 Table Statistics:\n")

        for table in ["prints", "unique_artworks", "prints_fts"]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  {table}: {count:,} rows")
            except sqlite3.Error:
                pass

    finally:
        conn.close()


def vacuum_db(db_path: str = DB_PATH) -> None:
    """Vacuum and optimize the database."""
    if not os.path.exists(db_path):
        print(f"⚠️  Database not found at {db_path}")
        return

    print("🧹 Vacuuming database...")
    start_time = time.time()

    size_before = os.path.getsize(db_path) / (1024 * 1024)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("VACUUM;")
        cur.execute("ANALYZE;")
        conn.commit()
    finally:
        conn.close()

    size_after = os.path.getsize(db_path) / (1024 * 1024)
    elapsed = time.time() - start_time

    print("✓ Vacuum complete!")
    print(f"  Before: {size_before:.1f} MB")
    print(f"  After: {size_after:.1f} MB")
    print(f"  Saved: {size_before - size_after:.1f} MB")
    print(f"  Time: {elapsed:.1f}s")


if __name__ == "__main__":
    import click

    @click.group()
    def cli():
        """Database optimization utilities."""
        pass

    @cli.command()
    def optimize():
        """Add composite indexes for faster searches."""
        add_composite_indexes()

    @cli.command()
    def info():
        """Show database index information."""
        show_index_info()

    @cli.command()
    def vacuum():
        """Vacuum and optimize the database."""
        vacuum_db()

    @cli.command()
    def all():
        """Run all optimizations (indexes + vacuum)."""
        add_composite_indexes()
        print()
        vacuum_db()

    cli()
