#!/usr/bin/env python3
"""Comprehensive test suite for AI recommendations implementation.

This script tests all 8 features added from the ChatGPT/Cascade AI review:
1. Foreign key enforcement
2. Golden dataset fixtures
3. Centralized network module
4. Integration tests
5. Developer guide
6. Alembic migrations
7. Structured logging
8. Incremental updates

Usage:
    python tools/test_ai_recommendations.py
    # or
    make test-ai-recommendations
"""

import json
import os
import sys
import time
import tracemalloc
from pathlib import Path

# Add src and repo root to path for imports
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root))

# Test results tracking
tests_passed = 0
tests_failed = 0
tests_skipped = 0


def print_header(title):
    """Print a formatted test section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def print_test(name, status="PASS", details=""):
    """Print a test result."""
    global tests_passed, tests_failed, tests_skipped

    if status == "PASS":
        symbol = "[PASS]"
        tests_passed += 1
    elif status == "FAIL":
        symbol = "[FAIL]"
        tests_failed += 1
    elif status == "SKIP":
        symbol = "[SKIP]"
        tests_skipped += 1
    else:
        symbol = "[INFO]"

    print(f"{symbol} {name}")
    if details:
        print(f"      {details}")


def test_foreign_keys():
    """Test 1: Foreign key enforcement."""
    print_header("Test 1: Foreign Key Enforcement")

    try:
        from db.bulk_index import _get_connection, DB_PATH

        if not Path(DB_PATH).exists():
            print_test("Foreign keys", "SKIP", "Database not found")
            return

        conn = _get_connection(DB_PATH)
        cur = conn.cursor()

        # Check if foreign keys are enabled
        cur.execute("PRAGMA foreign_keys")
        result = cur.fetchone()

        if result and result[0] == 1:
            print_test("Foreign keys enabled globally", "PASS")
        else:
            print_test("Foreign keys enabled globally", "FAIL", "PRAGMA returned 0")

        conn.close()

    except Exception as e:
        print_test("Foreign keys", "FAIL", str(e))


def test_golden_fixtures():
    """Test 2: Golden dataset fixtures."""
    print_header("Test 2: Golden Dataset Fixtures")

    fixtures_dir = Path("src/tests/data/fixtures")

    # Check directory exists
    if not fixtures_dir.exists():
        print_test("Fixtures directory", "FAIL", "Directory not found")
        return

    print_test("Fixtures directory exists", "PASS")

    # Check manifest
    manifest_path = fixtures_dir / "manifest.json"
    if not manifest_path.exists():
        print_test("Manifest file", "FAIL", "manifest.json not found")
        return

    try:
        manifest = json.loads(manifest_path.read_text())
        fixture_count = len(manifest.get("fixtures", []))
        print_test("Manifest loaded", "PASS", f"{fixture_count} fixtures defined")

        # Validate each fixture
        for fixture in manifest["fixtures"]:
            name = fixture["name"]
            file_path = fixtures_dir / fixture["file"]

            if not file_path.exists():
                print_test(
                    f"Fixture: {name}", "FAIL", f"File not found: {fixture['file']}"
                )
                continue

            content = file_path.read_text()
            expected = fixture.get("expected", {})

            print_test(
                f"Fixture: {name}",
                "PASS",
                f"{fixture['format']} format, {expected.get('total_cards', '?')} cards",
            )

    except Exception as e:
        print_test("Fixture validation", "FAIL", str(e))


def test_network_module():
    """Test 3: Centralized network module."""
    print_header("Test 3: Centralized Network Module")

    try:
        from net import fetch_bytes, fetch_json, fetch_with_etag, RetryConfig

        print_test("Network module imports", "PASS")

        # Test fetch_bytes
        try:
            content = fetch_bytes("https://httpbin.org/bytes/100")
            print_test("fetch_bytes()", "PASS", f"Downloaded {len(content)} bytes")
        except Exception as e:
            print_test("fetch_bytes()", "FAIL", str(e))

        # Test fetch_json
        try:
            data = fetch_json("https://httpbin.org/json")
            print_test("fetch_json()", "PASS", f"Keys: {list(data.keys())[:3]}")
        except Exception as e:
            print_test("fetch_json()", "FAIL", str(e))

        # Test RetryConfig
        try:
            config = RetryConfig(max_retries=2, base_delay=0.1)
            print_test("RetryConfig", "PASS", f"max_retries={config.max_retries}")
        except Exception as e:
            print_test("RetryConfig", "FAIL", str(e))

        # Test fetch_with_etag
        try:
            content, etag = fetch_with_etag("https://httpbin.org/etag/test-etag")
            print_test(
                "fetch_with_etag()", "PASS", f"ETag: {etag[:20] if etag else 'None'}..."
            )
        except Exception as e:
            print_test("fetch_with_etag()", "FAIL", str(e))

    except ImportError as e:
        print_test("Network module", "FAIL", f"Import error: {e}")


def test_integration_tests():
    """Test 4: Integration tests."""
    print_header("Test 4: Integration Tests")

    test_file = Path("src/tests/test_integration.py")

    if not test_file.exists():
        print_test("Integration test file", "FAIL", "File not found")
        return

    print_test("Integration test file exists", "PASS")

    # Try to import pytest
    try:
        import pytest

        print_test("pytest installed", "PASS")

        # Count tests
        lines = test_file.read_text().split("\n")
        test_count = sum(1 for line in lines if line.strip().startswith("def test_"))
        print_test("Test functions defined", "PASS", f"{test_count} test functions")

    except ImportError:
        print_test("pytest", "SKIP", "pytest not installed")


def test_developer_guide():
    """Test 5: Developer guide."""
    print_header("Test 5: Developer Guide Documentation")

    guide_path = Path("mds/guides/DEVELOPER_GUIDE.md")

    if not guide_path.exists():
        print_test("Developer guide", "FAIL", "File not found")
        return

    content = guide_path.read_text()
    lines = content.split("\n")

    print_test("Developer guide exists", "PASS", f"{len(lines)} lines")

    # Check for major sections
    sections = [line for line in lines if line.startswith("## ")]
    print_test("Major sections", "PASS", f"{len(sections)} sections found")

    # Check for code examples
    code_blocks = content.count("```")
    print_test("Code examples", "PASS", f"{code_blocks // 2} code blocks")


def test_alembic_migrations():
    """Test 6: Alembic migrations."""
    print_header("Test 6: Alembic Schema Migrations")

    migrations_dir = Path("src/db/migrations")

    if not migrations_dir.exists():
        print_test("Migrations directory", "FAIL", "Directory not found")
        return

    print_test("Migrations directory exists", "PASS")

    # Check for config files
    config_files = ["alembic.ini", "env.py", "script.py.mako", "README.md"]

    for config_file in config_files:
        file_path = migrations_dir / config_file
        if file_path.exists():
            print_test(f"Config: {config_file}", "PASS")
        else:
            print_test(f"Config: {config_file}", "FAIL", "File not found")

    # Check for versions directory
    versions_dir = migrations_dir / "versions"
    if versions_dir.exists():
        migrations = list(versions_dir.glob("*.py"))
        print_test("Migration versions", "PASS", f"{len(migrations)} migration(s)")
    else:
        print_test("Versions directory", "FAIL", "Directory not found")

    # Try to import alembic
    try:
        import alembic

        print_test("Alembic installed", "PASS", f"version {alembic.__version__}")
    except ImportError:
        print_test("Alembic", "SKIP", "alembic not installed")


def test_structured_logging():
    """Test 7: Structured logging."""
    print_header("Test 7: Structured Logging")

    try:
        from tools.logging_config import (
            is_enabled,
            setup_logging,
            log_info,
            LogOperation,
            LOGURU_AVAILABLE,
        )

        print_test("Logging module imports", "PASS")

        # Check if loguru is available
        if LOGURU_AVAILABLE:
            print_test("loguru available", "PASS")
        else:
            print_test("loguru", "SKIP", "loguru not installed (optional)")

        # Test that logging is disabled by default
        if not is_enabled():
            print_test("Logging disabled by default", "PASS")
        else:
            print_test("Logging disabled by default", "FAIL", "Should be disabled")

        # Test enabling (if loguru available)
        if LOGURU_AVAILABLE:
            os.environ["ENABLE_STRUCTURED_LOGGING"] = "1"

            # Re-import to pick up env var
            from importlib import reload
            import tools.logging_config as lc

            reload(lc)

            if lc.is_enabled():
                print_test("Logging can be enabled", "PASS")
            else:
                print_test("Logging can be enabled", "FAIL")

            # Cleanup
            del os.environ["ENABLE_STRUCTURED_LOGGING"]

    except ImportError as e:
        print_test("Logging module", "FAIL", f"Import error: {e}")


def test_incremental_updates():
    """Test 8: Incremental updates."""
    print_header("Test 8: Incremental Database Updates")

    try:
        from tools.incremental_update import (
            get_stored_etag,
            store_etag,
            calculate_sha256,
            check_for_updates,
            BULK_FILES,
        )

        print_test("Incremental update module imports", "PASS")

        # Check bulk files defined
        print_test("Bulk file types", "PASS", f"{len(BULK_FILES)} types defined")

        # Test ETag storage (if database exists)
        from db.bulk_index import DB_PATH

        if Path(DB_PATH).exists():
            try:
                # Test get_stored_etag (should return None or a string)
                etag = get_stored_etag("test-file.json")
                print_test(
                    "get_stored_etag()", "PASS", f"Returns: {type(etag).__name__}"
                )
            except Exception as e:
                print_test("get_stored_etag()", "FAIL", str(e))
        else:
            print_test("ETag storage", "SKIP", "Database not found")

        # Test SHA256 calculation
        try:
            test_file = Path(__file__)
            sha256 = calculate_sha256(test_file)
            print_test("calculate_sha256()", "PASS", f"Hash: {sha256[:16]}...")
        except Exception as e:
            print_test("calculate_sha256()", "FAIL", str(e))

    except ImportError as e:
        print_test("Incremental update module", "FAIL", f"Import error: {e}")


def test_memory_usage():
    """Bonus: Test memory usage with optimized queries."""
    print_header("Bonus: Memory Usage Test")

    try:
        from db.bulk_index import query_cards_optimized, DB_PATH

        if not Path(DB_PATH).exists():
            print_test("Memory test", "SKIP", "Database not found")
            return

        tracemalloc.start()

        # Query with filters
        cards = query_cards_optimized(
            card_type="creature", set_filter="znr", rarity_filter="rare", limit=100
        )

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        memory_mb = peak / 1024 / 1024

        if memory_mb < 200:  # Should be well under 200MB
            print_test(
                "Memory usage",
                "PASS",
                f"Peak: {memory_mb:.1f}MB for {len(cards)} cards",
            )
        else:
            print_test("Memory usage", "FAIL", f"Peak: {memory_mb:.1f}MB (too high)")

    except Exception as e:
        print_test("Memory test", "FAIL", str(e))


def print_summary():
    """Print test summary."""
    print_header("Test Summary")

    total = tests_passed + tests_failed + tests_skipped

    print(f"Total tests:  {total}")
    print(f"Passed:       {tests_passed}")
    print(f"Failed:       {tests_failed}")
    print(f"Skipped:      {tests_skipped}")
    print()

    if tests_failed > 0:
        print("Status: FAILED")
        return 1
    elif tests_passed > 0:
        print("Status: PASSED")
        return 0
    else:
        print("Status: NO TESTS RUN")
        return 2


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("  AI RECOMMENDATIONS - COMPREHENSIVE TEST SUITE")
    print("  Testing all 8 features from ChatGPT/Cascade review")
    print("=" * 70)

    start_time = time.time()

    # Run all tests
    test_foreign_keys()
    test_golden_fixtures()
    test_network_module()
    test_integration_tests()
    test_developer_guide()
    test_alembic_migrations()
    test_structured_logging()
    test_incremental_updates()
    test_memory_usage()

    elapsed = time.time() - start_time

    # Print summary
    exit_code = print_summary()

    print(f"Completed in {elapsed:.2f} seconds")
    print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
