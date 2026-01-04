"""Centralized network utilities with retry logic and exponential backoff.

This module provides robust HTTP request handling with:
- Automatic retries with exponential backoff
- Jitter to prevent thundering herd
- Configurable retry behavior
- Support for rate limiting
- Proper error handling and logging
"""

import json
import random
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 0.5  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_429: bool = True  # Rate limit errors
    retry_on_5xx: bool = True  # Server errors
    timeout: int = 30  # seconds

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter."""
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)

        if self.jitter:
            # Add random jitter (0-50% of delay)
            delay += random.uniform(0, delay * 0.5)

        return delay


# Default configuration
DEFAULT_CONFIG = RetryConfig()


def fetch_bytes(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    config: Optional[RetryConfig] = None,
    user_agent: str = "ProxyMachine/1.0",
) -> bytes:
    """Fetch URL content as bytes with retry logic.

    Args:
        url: URL to fetch
        headers: Optional HTTP headers
        config: Retry configuration (uses default if None)
        user_agent: User-Agent header value

    Returns:
        Response body as bytes

    Raises:
        HTTPError: If all retries fail with HTTP error
        URLError: If all retries fail with network error
        TimeoutError: If request times out
    """
    if config is None:
        config = DEFAULT_CONFIG

    request_headers = {"User-Agent": user_agent}
    if headers:
        request_headers.update(headers)

    last_error: Optional[Exception] = None

    for attempt in range(config.max_retries):
        try:
            req = Request(url, headers=request_headers)
            with urlopen(req, timeout=config.timeout) as response:
                return response.read()

        except HTTPError as error:
            last_error = error

            # Retry on rate limit (429)
            if (
                error.code == 429
                and config.retry_on_429
                and attempt < config.max_retries - 1
            ):
                delay = config.get_delay(attempt)
                time.sleep(delay)
                continue

            # Retry on server errors (5xx)
            if (
                500 <= error.code < 600
                and config.retry_on_5xx
                and attempt < config.max_retries - 1
            ):
                delay = config.get_delay(attempt)
                time.sleep(delay)
                continue

            # Don't retry on client errors (4xx except 429)
            break

        except (URLError, ConnectionResetError, ssl.SSLError, TimeoutError) as error:
            last_error = error

            # Retry on network errors
            if attempt < config.max_retries - 1:
                delay = config.get_delay(attempt)
                time.sleep(delay)
                continue

            break

    # All retries exhausted
    if last_error:
        raise last_error

    raise RuntimeError(f"Failed to fetch {url} after {config.max_retries} attempts")


def fetch_json(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    config: Optional[RetryConfig] = None,
    user_agent: str = "ProxyMachine/1.0",
) -> dict[str, Any]:
    """Fetch URL content as JSON with retry logic.

    Args:
        url: URL to fetch
        headers: Optional HTTP headers
        config: Retry configuration (uses default if None)
        user_agent: User-Agent header value

    Returns:
        Parsed JSON response as dictionary

    Raises:
        HTTPError: If all retries fail with HTTP error
        URLError: If all retries fail with network error
        json.JSONDecodeError: If response is not valid JSON
    """
    content = fetch_bytes(url, headers=headers, config=config, user_agent=user_agent)
    return json.loads(content.decode("utf-8"))


def download_file(
    url: str,
    destination: Path,
    *,
    headers: Optional[dict[str, str]] = None,
    config: Optional[RetryConfig] = None,
    user_agent: str = "ProxyMachine/1.0",
    atomic: bool = True,
) -> None:
    """Download file from URL to destination with retry logic.

    Args:
        url: URL to download
        destination: Destination file path
        headers: Optional HTTP headers
        config: Retry configuration (uses default if None)
        user_agent: User-Agent header value
        atomic: If True, write to temp file and rename (atomic operation)

    Raises:
        HTTPError: If all retries fail with HTTP error
        URLError: If all retries fail with network error
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Fetch content with retry logic
    content = fetch_bytes(url, headers=headers, config=config, user_agent=user_agent)

    if atomic:
        # Write to temp file and atomically rename
        tmp_path = destination.with_suffix(destination.suffix + ".part")
        try:
            tmp_path.write_bytes(content)
            tmp_path.replace(destination)
        finally:
            # Clean up temp file if it exists
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
    else:
        # Direct write
        destination.write_bytes(content)


def fetch_with_etag(
    url: str,
    etag: Optional[str] = None,
    *,
    headers: Optional[dict[str, str]] = None,
    config: Optional[RetryConfig] = None,
    user_agent: str = "ProxyMachine/1.0",
) -> tuple[bytes, Optional[str]]:
    """Fetch URL with ETag support for conditional requests.

    Args:
        url: URL to fetch
        etag: Previous ETag value (for If-None-Match header)
        headers: Optional HTTP headers
        config: Retry configuration (uses default if None)
        user_agent: User-Agent header value

    Returns:
        Tuple of (content, new_etag)
        If server returns 304 Not Modified, content will be empty bytes

    Raises:
        HTTPError: If all retries fail with HTTP error (except 304)
        URLError: If all retries fail with network error
    """
    if config is None:
        config = DEFAULT_CONFIG

    request_headers = {"User-Agent": user_agent}
    if headers:
        request_headers.update(headers)
    if etag:
        request_headers["If-None-Match"] = etag

    last_error: Optional[Exception] = None

    for attempt in range(config.max_retries):
        try:
            req = Request(url, headers=request_headers)
            with urlopen(req, timeout=config.timeout) as response:
                content = response.read()
                new_etag = response.headers.get("ETag")
                return content, new_etag

        except HTTPError as error:
            # 304 Not Modified is success
            if error.code == 304:
                return b"", etag

            last_error = error

            # Retry logic (same as fetch_bytes)
            if (
                error.code == 429
                and config.retry_on_429
                and attempt < config.max_retries - 1
            ):
                delay = config.get_delay(attempt)
                time.sleep(delay)
                continue

            if (
                500 <= error.code < 600
                and config.retry_on_5xx
                and attempt < config.max_retries - 1
            ):
                delay = config.get_delay(attempt)
                time.sleep(delay)
                continue

            break

        except (URLError, ConnectionResetError, ssl.SSLError, TimeoutError) as error:
            last_error = error

            if attempt < config.max_retries - 1:
                delay = config.get_delay(attempt)
                time.sleep(delay)
                continue

            break

    if last_error:
        raise last_error

    raise RuntimeError(f"Failed to fetch {url} after {config.max_retries} attempts")
