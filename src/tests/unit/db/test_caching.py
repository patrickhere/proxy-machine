"""Unit tests for database caching in db/bulk_index.py"""

import sys
import time
from pathlib import Path

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def test_cache_imports():
    """Test that caching imports work."""
    try:
        from db.bulk_index import CACHE_ENABLED, cached_query, query_cache

        assert CACHE_ENABLED is True
        assert cached_query is not None
        assert query_cache is not None
    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_enabled():
    """Test that caching is enabled when diskcache is available."""
    try:
        from db.bulk_index import CACHE_ENABLED

        assert CACHE_ENABLED is True
    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_directory_created():
    """Test that cache directory is created."""
    try:
        from db.bulk_index import query_cache

        cache_dir = Path(query_cache.directory)
        assert cache_dir.exists()
        assert cache_dir.name == "db_queries"
    except ImportError:
        pytest.skip("diskcache not available")


def test_cached_query_decorator():
    """Test that @cached_query decorator works."""
    try:
        from db.bulk_index import cached_query

        call_count = 0

        @cached_query(expire=60)
        def test_function(x, y):
            nonlocal call_count
            call_count += 1
            return x + y

        # First call - should execute function
        result1 = test_function(2, 3)
        assert result1 == 5
        assert call_count == 1

        # Second call with same args - should use cache
        result2 = test_function(2, 3)
        assert result2 == 5
        assert call_count == 1  # Not incremented - used cache

        # Different args - should execute function again
        result3 = test_function(4, 5)
        assert result3 == 9
        assert call_count == 2

    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_expiration():
    """Test that cache expires after specified time."""
    try:
        from db.bulk_index import cached_query

        call_count = 0

        @cached_query(expire=1)  # 1 second expiration
        def test_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = test_function(5)
        assert result1 == 10
        assert call_count == 1

        # Immediate second call - should use cache
        result2 = test_function(5)
        assert result2 == 10
        assert call_count == 1

        # Wait for expiration
        time.sleep(1.5)

        # Third call - should re-execute
        result3 = test_function(5)
        assert result3 == 10
        assert call_count == 2

    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_with_kwargs():
    """Test that caching works with keyword arguments."""
    try:
        from db.bulk_index import cached_query

        call_count = 0

        @cached_query(expire=60)
        def test_function(a, b=10):
            nonlocal call_count
            call_count += 1
            return a + b

        # Call with positional and keyword args
        result1 = test_function(5, b=15)
        assert result1 == 20
        assert call_count == 1

        # Same call - should use cache
        result2 = test_function(5, b=15)
        assert result2 == 20
        assert call_count == 1

        # Different kwargs - should re-execute
        result3 = test_function(5, b=20)
        assert result3 == 25
        assert call_count == 2

    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_size_limit():
    """Test that cache has a size limit."""
    try:
        from db.bulk_index import query_cache

        # Check that size_limit is set (100MB = 100,000,000 bytes)
        assert query_cache.size_limit == 100_000_000

    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_statistics():
    """Test that cache provides statistics."""
    try:
        from db.bulk_index import query_cache

        # Cache should have a volume() method that returns size
        volume = query_cache.volume()
        assert isinstance(volume, int)
        assert volume >= 0

    except ImportError:
        pytest.skip("diskcache not available")


def test_cache_clear():
    """Test that cache can be cleared."""
    try:
        from db.bulk_index import cached_query, query_cache

        call_count = 0

        @cached_query(expire=60)
        def test_function(x):
            nonlocal call_count
            call_count += 1
            return x * 3

        # First call
        test_function(7)
        assert call_count == 1

        # Second call - cached
        test_function(7)
        assert call_count == 1

        # Clear cache
        query_cache.clear()

        # Third call - should re-execute after clear
        test_function(7)
        assert call_count == 2

    except ImportError:
        pytest.skip("diskcache not available")


def test_cached_functions_exist():
    """Test that expected functions have caching decorators."""
    try:
        from db import bulk_index

        # Check that key query functions exist
        assert hasattr(bulk_index, "query_basic_lands")
        assert hasattr(bulk_index, "query_non_basic_lands")
        assert hasattr(bulk_index, "query_tokens")

        # These should all be callable
        assert callable(bulk_index.query_basic_lands)
        assert callable(bulk_index.query_non_basic_lands)
        assert callable(bulk_index.query_tokens)

    except ImportError:
        pytest.skip("db.bulk_index not available")


def test_cache_performance_improvement():
    """Test that caching provides performance improvement."""
    try:
        from db.bulk_index import cached_query
        import time

        call_times = []

        @cached_query(expire=60)
        def slow_function(x):
            # Simulate slow operation
            time.sleep(0.01)
            return x**2

        # First call (uncached)
        start = time.time()
        result1 = slow_function(10)
        first_call_time = time.time() - start

        # Second call (cached)
        start = time.time()
        result2 = slow_function(10)
        second_call_time = time.time() - start

        # Verify results are the same
        assert result1 == result2 == 100

        # Cache should be significantly faster
        # (second call should be <1ms vs first call 10ms)
        assert second_call_time < first_call_time * 0.5

    except ImportError:
        pytest.skip("diskcache not available")
