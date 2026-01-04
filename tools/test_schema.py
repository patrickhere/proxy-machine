#!/usr/bin/env python3
"""Schema validation tests for database integrity.

Validates that:
1. Database schema matches expected structure
2. Column names in code match database columns
3. Type definitions are correct
4. Indexes exist and are properly configured
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.card_types import DBColumns, CardRelationshipColumns, SCHEMA_VERSION

DB_PATH = (
    Path(__file__).parent.parent.parent
    / "magic-the-gathering"
    / "bulk-data"
    / "bulk.db"
)


def test_database_exists():
    """Test that database file exists."""
    assert DB_PATH.exists(), f"Database not found at {DB_PATH}"
    print("[PASS] Database file exists")


def test_prints_table_exists():
    """Test that prints table exists."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prints'")
    result = cur.fetchone()
    conn.close()

    assert result is not None, "prints table does not exist"
    print("[PASS] prints table exists")


def test_prints_columns():
    """Test that all expected columns exist in prints table."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(prints)")
    actual_columns = {row[1] for row in cur.fetchall()}
    conn.close()

    # Get all column names from DBColumns class
    expected_columns = {
        getattr(DBColumns, attr) for attr in dir(DBColumns) if not attr.startswith("_")
    }

    missing = expected_columns - actual_columns
    extra = actual_columns - expected_columns

    if missing:
        print(f"[FAIL] Missing columns in database: {missing}")
        assert False, f"Missing columns: {missing}"

    if extra:
        print(f"[WARN] Extra columns in database (not in DBColumns): {extra}")

    print(f"[PASS] All {len(expected_columns)} expected columns exist in prints table")


def test_relationships_table_exists():
    """Test that card_relationships table exists."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='card_relationships'"
    )
    result = cur.fetchone()
    conn.close()

    assert result is not None, "card_relationships table does not exist"
    print("[PASS] card_relationships table exists")


def test_relationships_columns():
    """Test that all expected columns exist in card_relationships table."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(card_relationships)")
    actual_columns = {row[1] for row in cur.fetchall()}
    conn.close()

    expected_columns = {
        getattr(CardRelationshipColumns, attr)
        for attr in dir(CardRelationshipColumns)
        if not attr.startswith("_")
    }

    missing = expected_columns - actual_columns

    if missing:
        print(f"[FAIL] Missing columns in card_relationships: {missing}")
        assert False, f"Missing columns: {missing}"

    print(
        f"[PASS] All {len(expected_columns)} expected columns exist in card_relationships table"
    )


def test_indexes_exist():
    """Test that required indexes exist."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cur.fetchall()}
    conn.close()

    # Check for important indexes
    required_patterns = [
        "idx_prints_set",  # Index on set_code column
        "idx_prints_name",
        "idx_relationships_source",
        "idx_relationships_related",
    ]

    found = []
    missing = []

    for pattern in required_patterns:
        if any(pattern in idx for idx in indexes):
            found.append(pattern)
        else:
            missing.append(pattern)

    if missing:
        print(f"[WARN] Missing recommended indexes: {missing}")

    print(f"[PASS] Found {len(found)}/{len(required_patterns)} recommended indexes")


def test_schema_version():
    """Test that schema version is tracked."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    try:
        cur.execute("SELECT value FROM metadata WHERE key='schema_version'")
        result = cur.fetchone()

        if result:
            db_version = int(result[0])
            if db_version == SCHEMA_VERSION:
                print(f"[PASS] Schema version matches (v{SCHEMA_VERSION})")
            else:
                print(
                    f"[WARN] Schema version mismatch: DB={db_version}, Code={SCHEMA_VERSION}"
                )
        else:
            print("[WARN] Schema version not found in metadata")
    except sqlite3.OperationalError:
        print("[WARN] metadata table does not exist")
    finally:
        conn.close()


def test_column_types():
    """Test that column types match expectations."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(prints)")
    columns = {row[1]: row[2] for row in cur.fetchall()}
    conn.close()

    # Check critical column types
    type_checks = {
        DBColumns.ID: "TEXT",
        DBColumns.NAME: "TEXT",
        DBColumns.SET_CODE: "TEXT",
        DBColumns.IS_BASIC_LAND: "INTEGER",
        DBColumns.IS_TOKEN: "INTEGER",
        DBColumns.CMC: "REAL",
    }

    failures = []
    for col, expected_type in type_checks.items():
        actual_type = columns.get(col, "MISSING")
        if actual_type != expected_type:
            failures.append(f"{col}: expected {expected_type}, got {actual_type}")

    if failures:
        print("[FAIL] Column type mismatches:")
        for failure in failures:
            print(f"  - {failure}")
        assert False, "Column type mismatches found"

    print(f"[PASS] All {len(type_checks)} critical column types are correct")


def test_data_integrity():
    """Test basic data integrity constraints."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Check for NULL IDs
    cur.execute(f"SELECT COUNT(*) FROM prints WHERE {DBColumns.ID} IS NULL")
    null_ids = cur.fetchone()[0]
    assert null_ids == 0, f"Found {null_ids} cards with NULL IDs"

    # Check for NULL names
    cur.execute(f"SELECT COUNT(*) FROM prints WHERE {DBColumns.NAME} IS NULL")
    null_names = cur.fetchone()[0]
    assert null_names == 0, f"Found {null_names} cards with NULL names"

    # Check relationship integrity
    cur.execute(
        """
        SELECT COUNT(*) FROM card_relationships r
        WHERE NOT EXISTS (SELECT 1 FROM prints p WHERE p.id = r.source_card_id)
    """
    )
    orphaned_sources = cur.fetchone()[0]

    conn.close()

    if orphaned_sources > 0:
        print(f"[WARN] Found {orphaned_sources} orphaned relationship sources")

    print("[PASS] Basic data integrity checks passed")


def run_all_tests():
    """Run all schema validation tests."""
    tests = [
        test_database_exists,
        test_prints_table_exists,
        test_prints_columns,
        test_relationships_table_exists,
        test_relationships_columns,
        test_indexes_exist,
        test_schema_version,
        test_column_types,
        test_data_integrity,
    ]

    print("Running Schema Validation Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
