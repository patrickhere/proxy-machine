#!/usr/bin/env python3
"""Query result caching for database performance.

Implements LRU cache for frequently accessed queries.
"""

import hashlib
import json
import time
from typing import Any, Optional, Callable
from collections import OrderedDict


class QueryCache:
    """LRU cache for database query results."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """Initialize cache.

        Args:
            max_size: Maximum number of cached queries
            ttl_seconds: Time-to-live for cache entries (default 5 minutes)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = OrderedDict()
        self.hits = 0
        self.misses = 0

    def _make_key(self, query: str, params: tuple) -> str:
        """Generate cache key from query and parameters."""
        key_data = json.dumps({"query": query, "params": params}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, query: str, params: tuple = ()) -> Optional[Any]:
        """Get cached result if available and not expired."""
        key = self._make_key(query, params)

        if key in self.cache:
            entry = self.cache[key]

            # Check if expired
            if time.time() - entry["timestamp"] > self.ttl_seconds:
                del self.cache[key]
                self.misses += 1
                return None

            # Move to end (most recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return entry["result"]

        self.misses += 1
        return None

    def set(self, query: str, params: tuple, result: Any):
        """Cache query result."""
        key = self._make_key(query, params)

        # Remove oldest if at capacity
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)

        self.cache[key] = {"result": result, "timestamp": time.time()}

    def clear(self):
        """Clear all cached entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "ttl_seconds": self.ttl_seconds,
        }

    def print_stats(self):
        """Print cache statistics."""
        stats = self.get_stats()
        print("\n[QUERY CACHE STATS]")
        print(f"  Size: {stats['size']}/{stats['max_size']}")
        print(f"  Hits: {stats['hits']}")
        print(f"  Misses: {stats['misses']}")
        print(f"  Hit rate: {stats['hit_rate']}")
        print(f"  TTL: {stats['ttl_seconds']}s")


# Global cache instance
_global_cache = QueryCache()


def get_cache() -> QueryCache:
    """Get global cache instance."""
    return _global_cache


def cached_query(func: Callable) -> Callable:
    """Decorator for caching query results."""

    def wrapper(*args, **kwargs):
        cache = get_cache()

        # Create cache key from function name and arguments
        key_data = f"{func.__name__}:{args}:{kwargs}"
        cache_key = hashlib.md5(key_data.encode()).hexdigest()

        # Try to get from cache
        cached = cache.get(cache_key, ())
        if cached is not None:
            return cached

        # Execute query
        result = func(*args, **kwargs)

        # Cache result
        cache.set(cache_key, (), result)

        return result

    return wrapper


# Example usage functions
@cached_query
def query_cards_by_set(set_code: str, limit: int = 100):
    """Example cached query function."""
    # This would normally query the database
    return f"Results for set {set_code} (limit {limit})"


@cached_query
def query_tokens_by_type(token_type: str):
    """Example cached query function."""
    return f"Results for token type {token_type}"


if __name__ == "__main__":
    # Test the cache
    cache = get_cache()

    print("Testing query cache...")

    # First query - cache miss
    result1 = query_cards_by_set("znr", 50)
    print(f"\n1st query: {result1}")
    cache.print_stats()

    # Second query - cache hit
    result2 = query_cards_by_set("znr", 50)
    print(f"\n2nd query: {result2}")
    cache.print_stats()

    # Different query - cache miss
    result3 = query_cards_by_set("mh2", 100)
    print(f"\n3rd query: {result3}")
    cache.print_stats()

    # Token query - cache miss
    result4 = query_tokens_by_type("goblin")
    print(f"\n4th query: {result4}")
    cache.print_stats()

    # Repeat token query - cache hit
    result5 = query_tokens_by_type("goblin")
    print(f"\n5th query: {result5}")
    cache.print_stats()

    print("\n[OK] Cache test complete")
