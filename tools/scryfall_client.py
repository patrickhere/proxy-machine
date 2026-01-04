#!/usr/bin/env python3
"""Enhanced Scryfall API client with retry-after logic and polite rate limiting."""

import time
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlencode


class ScryfallClient:
    """
    A polite Scryfall API client with automatic retry-after handling.

    Features:
    - Respects Retry-After headers
    - Automatic rate limiting (100ms between requests)
    - Exponential backoff for errors
    - User-agent compliance
    """

    def __init__(
        self,
        user_agent: str = "ProxyMachine/1.0 (patrick)",
        base_delay: float = 0.11,  # Scryfall recommends 50-100ms
        max_retries: int = 3,
    ):
        """
        Initialize the Scryfall client.

        Args:
            user_agent: User-Agent string for API requests
            base_delay: Minimum delay between requests in seconds
            max_retries: Maximum number of retry attempts
        """
        self.user_agent = user_agent
        self.base_delay = base_delay
        self.max_retries = max_retries
        self.last_request_time = 0
        self.api_base = "https://api.scryfall.com"

        # Track statistics
        self.stats = {
            "requests": 0,
            "retries": 0,
            "rate_limited": 0,
            "errors": 0,
        }

    def _wait_for_rate_limit(self) -> None:
        """Ensure we respect the rate limit between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.base_delay:
            time.sleep(self.base_delay - elapsed)
        self.last_request_time = time.time()

    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Make a GET request to the Scryfall API with retry logic.

        Args:
            path: API path (e.g., "/cards/search")
            params: Query parameters
            retry_count: Current retry attempt (internal use)

        Returns:
            JSON response as a dictionary

        Raises:
            requests.HTTPError: If the request fails after all retries
        """
        self._wait_for_rate_limit()

        # Build URL
        if path.startswith("http"):
            url = path
        else:
            url = f"{self.api_base}{path}"
            if params:
                url = f"{url}?{urlencode(params)}"

        headers = {"User-Agent": self.user_agent}

        try:
            self.stats["requests"] += 1
            response = requests.get(url, headers=headers, timeout=30)

            # Check for rate limiting (429 Too Many Requests)
            if response.status_code == 429:
                self.stats["rate_limited"] += 1
                retry_after = int(response.headers.get("Retry-After", 1))

                if retry_count < self.max_retries:
                    print(
                        f"\n⏳ Scryfall is busy, waiting {retry_after}s before retry "
                        f"(attempt {retry_count + 1}/{self.max_retries})..."
                    )
                    time.sleep(retry_after)
                    self.stats["retries"] += 1
                    return self.get(path, params, retry_count + 1)
                else:
                    raise requests.HTTPError(
                        f"Rate limited after {self.max_retries} retries"
                    )

            # Check for other errors
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            self.stats["errors"] += 1

            # Retry with exponential backoff for transient errors
            if retry_count < self.max_retries:
                wait_time = self.base_delay * (2**retry_count)
                print(
                    f"\n⚠️  Request failed ({e}), retrying in {wait_time:.1f}s "
                    f"(attempt {retry_count + 1}/{self.max_retries})..."
                )
                time.sleep(wait_time)
                self.stats["retries"] += 1
                return self.get(path, params, retry_count + 1)
            else:
                raise

    def get_card(self, card_id: str) -> Dict[str, Any]:
        """
        Get a single card by ID.

        Args:
            card_id: Scryfall card ID

        Returns:
            Card data dictionary
        """
        return self.get(f"/cards/{card_id}")

    def search(
        self,
        query: str,
        unique: str = "cards",
        order: str = "name",
        include_extras: bool = False,
    ) -> Dict[str, Any]:
        """
        Search for cards using Scryfall syntax.

        Args:
            query: Scryfall search query
            unique: Uniqueness strategy (cards, art, prints)
            order: Sort order
            include_extras: Include extras like tokens

        Returns:
            Search results dictionary with 'data' list
        """
        params = {
            "q": query,
            "unique": unique,
            "order": order,
        }
        if include_extras:
            params["include_extras"] = "true"

        return self.get("/cards/search", params)

    def get_all_pages(
        self,
        initial_response: Dict[str, Any],
        max_pages: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        """
        Fetch all pages from a paginated Scryfall response.

        Args:
            initial_response: First page of results
            max_pages: Maximum number of pages to fetch (None = all)

        Returns:
            List of all cards from all pages
        """
        all_cards = list(initial_response.get("data", []))
        next_page = initial_response.get("next_page")
        page_count = 1

        while next_page and (max_pages is None or page_count < max_pages):
            response = self.get(next_page)
            all_cards.extend(response.get("data", []))
            next_page = response.get("next_page")
            page_count += 1

        return all_cards

    def print_stats(self) -> None:
        """Print client statistics."""
        print("\n📊 Scryfall API Statistics:")
        print(f"  Total requests: {self.stats['requests']}")
        print(f"  Retries: {self.stats['retries']}")
        print(f"  Rate limited: {self.stats['rate_limited']}")
        print(f"  Errors: {self.stats['errors']}")


# Singleton instance for convenience
_default_client: Optional[ScryfallClient] = None


def get_default_client() -> ScryfallClient:
    """Get the default Scryfall client instance."""
    global _default_client
    if _default_client is None:
        _default_client = ScryfallClient()
    return _default_client


if __name__ == "__main__":
    # Demo the Scryfall client
    print("Demo: Scryfall API client with retry logic\n")

    client = ScryfallClient()

    # Test a simple search
    print("Searching for Lightning Bolt...")
    results = client.search('!"Lightning Bolt"')

    if results.get("data"):
        card = results["data"][0]
        print(f"✓ Found: {card['name']} ({card['set'].upper()})")

    # Print stats
    client.print_stats()

    print("\n✓ Demo complete!")
