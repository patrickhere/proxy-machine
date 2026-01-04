"""Card fetching module - refactored from monolithic functions.

Provides clean, testable interfaces for fetching cards from various sources.
"""

from fetch.card_fetcher import (
    CardFetcher,
    FetchConfig,
    FetchResult,
    fetch_cards,
)

__all__ = [
    "CardFetcher",
    "FetchConfig",
    "FetchResult",
    "fetch_cards",
]
