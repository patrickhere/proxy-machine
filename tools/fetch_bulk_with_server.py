#!/usr/bin/env python3
"""
Enhanced bulk data fetcher with custom server support.

Tries to fetch from custom server first (if PM_BULK_DATA_URL is set),
then falls back to Scryfall if that fails.

Usage:
  # Use custom server (from environment)
  export PM_BULK_DATA_URL=http://100.64.1.5:8080
  python tools/fetch_bulk_with_server.py --id all-cards

  # Force Scryfall
  python tools/fetch_bulk_with_server.py --id all-cards --force-scryfall

  # Specify custom server directly
  python tools/fetch_bulk_with_server.py --id all-cards --server http://100.64.1.5:8080
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

# Add parent directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))

from bulk_paths import ensure_bulk_data_directory

# Configuration
BULK_DIR = str(ensure_bulk_data_directory(prefer_primary=True))
SCRYFALL_API = "https://api.scryfall.com"

# File mappings
BULK_FILES = {
    "all-cards": "all-cards.json.gz",
    "oracle-cards": "oracle-cards.json.gz",
    "unique-artwork": "unique-artwork.json.gz",
}


def get_custom_server_url() -> str | None:
    """Get custom server URL from environment."""
    return os.environ.get("PM_BULK_DATA_URL")


def http_get(
    url: str, *, retries: int = 3, backoff: float = 0.5, timeout: int = 30
) -> bytes:
    """Simple HTTP GET with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ProxyMachine/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(backoff * (2**attempt))
    return b""


def download_with_progress(
    url: str,
    out_path: str,
    *,
    label: str = "download",
    chunk_size: int = 1024 * 256,
    timeout: int = 60,
) -> bool:
    """Download file with progress indicator. Returns True on success."""
    tmp_path = out_path + ".part"

    # Clean up any existing files
    for path in (out_path, tmp_path):
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ProxyMachine/1.0",
                "Accept-Encoding": "identity",
            },
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0

            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        mb_down = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        print(
                            f"\r{label}: {mb_down:.1f}/{mb_total:.1f} MB ({pct:.1f}%)",
                            end="",
                            flush=True,
                        )
                    else:
                        mb_down = downloaded / (1024 * 1024)
                        print(f"\r{label}: {mb_down:.1f} MB", end="", flush=True)

        print()  # New line after progress

        # Atomic rename
        os.rename(tmp_path, out_path)
        return True

    except Exception as e:
        print(f"\nDownload failed: {e}")
        # Clean up partial file
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def try_custom_server(bulk_id: str, server_url: str) -> bool:
    """Try to download from custom server. Returns True on success."""
    filename = BULK_FILES.get(bulk_id)
    if not filename:
        print(f"Unknown bulk id: {bulk_id}")
        return False

    url = f"{server_url.rstrip('/')}/bulk-data/{filename}"
    out_path = os.path.join(BULK_DIR, filename)

    print(f"Trying custom server: {url}")

    # Test if server is reachable
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "ProxyMachine/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                print(f"Server returned status {resp.status}")
                return False
    except Exception as e:
        print(f"Server not reachable: {e}")
        return False

    # Download the file
    success = download_with_progress(
        url,
        out_path,
        label=f"Downloading {filename} from custom server",
    )

    if success:
        print("Successfully downloaded from custom server")
        print(f"Saved to: {out_path}")
        return True

    return False


def fetch_from_scryfall(bulk_id: str) -> bool:
    """Fetch from Scryfall API. Returns True on success."""
    filename = BULK_FILES.get(bulk_id)
    if not filename:
        print(f"Unknown bulk id: {bulk_id}")
        return False

    print("Fetching from Scryfall API...")

    # Get bulk data info
    try:
        bulk_info_url = f"{SCRYFALL_API}/bulk-data"
        data = http_get(bulk_info_url)
        bulk_data = json.loads(data)
    except Exception as e:
        print(f"Failed to fetch bulk data info: {e}")
        return False

    # Find the matching bulk data entry
    download_url = None
    for item in bulk_data.get("data", []):
        if item.get("type") == bulk_id:
            download_url = item.get("download_uri")
            break

    if not download_url:
        print(f"Could not find bulk data for id: {bulk_id}")
        return False

    out_path = os.path.join(BULK_DIR, filename)

    print(f"Downloading from: {download_url}")
    success = download_with_progress(
        download_url,
        out_path,
        label=f"Downloading {filename} from Scryfall",
    )

    if success:
        print("Successfully downloaded from Scryfall")
        print(f"Saved to: {out_path}")
        return True

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Scryfall bulk data with custom server support"
    )
    parser.add_argument(
        "--id",
        required=True,
        choices=list(BULK_FILES.keys()),
        help="Bulk data id to fetch",
    )
    parser.add_argument(
        "--server",
        help="Custom server URL (overrides PM_BULK_DATA_URL env var)",
    )
    parser.add_argument(
        "--force-scryfall",
        action="store_true",
        help="Skip custom server and fetch directly from Scryfall",
    )

    args = parser.parse_args()

    # Ensure bulk directory exists
    os.makedirs(BULK_DIR, exist_ok=True)

    # Try custom server first (unless forced to use Scryfall)
    if not args.force_scryfall:
        server_url = args.server or get_custom_server_url()

        if server_url:
            print(f"Custom server configured: {server_url}")
            if try_custom_server(args.id, server_url):
                return 0
            print("Custom server failed, falling back to Scryfall...")
        else:
            print("No custom server configured (set PM_BULK_DATA_URL)")
            print("Falling back to Scryfall...")

    # Fallback to Scryfall
    if fetch_from_scryfall(args.id):
        return 0

    print("Failed to download bulk data")
    return 1


if __name__ == "__main__":
    sys.exit(main())
