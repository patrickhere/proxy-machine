#!/usr/bin/env python3
"""Generate database schema documentation.

Introspects SQLite database and generates markdown documentation.
"""

import sqlite3
import sys
from pathlib import Path


def get_table_info(cursor, table_name: str) -> list:
    """Get column information for a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def get_foreign_keys(cursor, table_name: str) -> list:
    """Get foreign key information for a table."""
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    return cursor.fetchall()


def get_indexes(cursor, table_name: str) -> list:
    """Get index information for a table."""
    cursor.execute(f"PRAGMA index_list({table_name})")
    return cursor.fetchall()


def generate_schema_docs(db_path: str) -> str:
    """Generate schema documentation markdown."""
    docs = []
    docs.append("# Database Schema\n")
    docs.append("Auto-generated documentation for The Proxy Machine database schema.\n")
    docs.append("---\n")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cursor.fetchall()

        docs.append(f"## Tables ({len(tables)})\n")

        for (table_name,) in tables:
            if table_name.startswith("sqlite_"):
                continue

            docs.append(f"### {table_name}\n")

            # Get columns
            columns = get_table_info(cursor, table_name)
            if columns:
                docs.append("**Columns:**\n")
                docs.append("| Column | Type | Nullable | Default | Primary Key |")
                docs.append("|--------|------|----------|---------|-------------|")
                for col in columns:
                    cid, name, type_, notnull, default, pk = col
                    nullable = "No" if notnull else "Yes"
                    default_val = default if default else "-"
                    pk_val = "Yes" if pk else "No"
                    docs.append(
                        f"| {name} | {type_} | {nullable} | {default_val} | {pk_val} |"
                    )
                docs.append("")

            # Get foreign keys
            fks = get_foreign_keys(cursor, table_name)
            if fks:
                docs.append("**Foreign Keys:**\n")
                for fk in fks:
                    id_, seq, table, from_, to_, on_update, on_delete, match = fk
                    docs.append(f"- `{from_}` → `{table}.{to_}`")
                docs.append("")

            # Get indexes
            indexes = get_indexes(cursor, table_name)
            if indexes:
                docs.append("**Indexes:**\n")
                for idx in indexes:
                    seq, name, unique, origin, partial = idx
                    unique_str = " (UNIQUE)" if unique else ""
                    docs.append(f"- `{name}`{unique_str}")
                docs.append("")

            docs.append("---\n")

        conn.close()

    except sqlite3.Error as e:
        docs.append(f"\nError: {e}\n")

    return "\n".join(docs)


def main():
    """Generate schema documentation."""
    # Try multiple possible database locations
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bulk_paths import bulk_db_path, legacy_bulk_locations

    possible_paths = [
        str(bulk_db_path()),
        "db/scryfall.db",
    ]
    # Add legacy locations
    for legacy_dir in legacy_bulk_locations():
        possible_paths.append(str(legacy_dir / "bulk.db"))

    db_path = None
    for path in possible_paths:
        if Path(path).exists():
            db_path = path
            break

    if not db_path:
        print("Database not found in any of these locations:")
        for path in possible_paths:
            print(f"  - {path}")
        print("Run bulk data build first: make bulk-index-build")
        return 1

    docs = generate_schema_docs(db_path)

    # Write to file
    output_file = Path("docs/schema.md")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(docs)

    print(f"Schema documentation written to: {output_file}")
    print(f"Lines: {len(docs.split(chr(10)))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
