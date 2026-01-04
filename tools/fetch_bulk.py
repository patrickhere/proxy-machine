#!/usr/bin/env python3
"""
Fetch a Scryfall bulk data file by bulk id and save it into bulk-data/.

Usage:
  python tools/fetch_bulk.py --id all-cards
  python tools/fetch_bulk.py --id unique-artwork
  python tools/fetch_bulk.py --id oracle-cards

This script uses only the Python standard library.
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

# Resolve bulk directory via centralized helpers
BULK_DIR = str(ensure_bulk_data_directory(prefer_primary=True))

API_ROOT = "https://api.scryfall.com"


def http_get(url: str, *, retries: int = 3, backoff: float = 0.5) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url) as resp:
                return resp.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2**attempt))
    return b""


def download_with_progress(
    url: str,
    out_path: str,
    *,
    label: str = "download",
    retries: int = 3,
    backoff: float = 0.5,
    chunk_size: int = 1024 * 256,
) -> None:
    """Download a URL to a file, streaming with a single-line progress indicator.

    Standard library only. Writes to out_path + ".part" and atomically replaces on success.
    """
    tmp_path = out_path + ".part"

    # Ensure previous partial download or incorrect file is removed
    def _cleanup_existing() -> None:
        for path in (out_path, tmp_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    _cleanup_existing()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "ProxyMachine/1.0 (bulk-fetch)",
                    "Accept-Encoding": "identity",
                },
            )
            with urllib.request.urlopen(req) as resp:
                total_header = resp.info().get("Content-Length")
                total_bytes = int(total_header) if total_header else None
                # Print header line once with approximate size
                if total_bytes:
                    approx_mb = total_bytes / (1024 * 1024)
                    print(f"Downloading {label} to {out_path} (~{approx_mb:.1f} MB)...")
                else:
                    print(f"Downloading {label} to {out_path} (size unknown)...")

                written = 0
                last_update = 0.0
                with open(tmp_path, "wb") as fh:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        fh.write(chunk)
                        written += len(chunk)
                        # Throttle UI updates to ~20 Hz
                        now = time.time()
                        if now - last_update >= 0.05:
                            last_update = now
                            if total_bytes:
                                pct = min(written * 100.0 / total_bytes, 100.0)
                                print(
                                    f"\r{label}: {written // (1024*1024)}MB/{total_bytes // (1024*1024)}MB ({pct:.1f}%)",
                                    end="",
                                    flush=True,
                                )
                            else:
                                print(
                                    f"\r{label}: {written // (1024*1024)}MB",
                                    end="",
                                    flush=True,
                                )
                if total_bytes and written < total_bytes:
                    print(
                        f"\n{label}: download incomplete ({written // (1024*1024)}MB/{total_bytes // (1024*1024)}MB). Retrying...",
                        flush=True,
                    )
                    raise IOError("download truncated")
                if total_bytes:
                    total_mb = total_bytes // (1024 * 1024)
                    print(
                        f"\r{label}: {written // (1024*1024)}MB/{total_mb}MB (100.0%)"
                    )
                else:
                    print(f"\r{label}: {written // (1024*1024)}MB (done)")
                os.replace(tmp_path, out_path)
                print("Done.")
                return
        except Exception:
            # Cleanup partial file on failure
            _cleanup_existing()
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2**attempt))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Scryfall bulk data by id")
    parser.add_argument(
        "--id",
        required=True,
        help="Bulk id: all-cards | oracle-cards | unique-artwork",
    )
    args = parser.parse_args()

    bulk_id = args.id.strip()
    # Offline mode: skip network fetches entirely
    offline = os.environ.get("PM_OFFLINE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if offline:
        print(f"Offline mode: skipping fetch for '{bulk_id}'")
        sys.exit(0)

    # Optional confirmation prompt to avoid accidental large downloads
    ask_refresh = os.environ.get("PM_ASK_REFRESH", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if ask_refresh and sys.stdin.isatty():
        try:
            resp = input(f"Fetch bulk '{bulk_id}' now? [y/N]: ").strip().lower()
        except EOFError:
            resp = "n"
        if resp not in {"y", "yes"}:
            print("Cancelled by user. Skipping fetch.")
            sys.exit(0)
    api_type = bulk_id.replace("-", "_")  # normalize to Scryfall's type values
    index_url = f"{API_ROOT}/bulk-data"

    try:
        raw = http_get(index_url)
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"Failed to load bulk-data index: {e}")
        sys.exit(1)

    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        print("Unexpected response from bulk-data API")
        sys.exit(1)

    target = None
    for entry in data["data"]:
        if not isinstance(entry, dict):
            continue
        # Match by normalized type (preferred). `id` is a UUID and not stable/human.
        if entry.get("type") == api_type:
            target = entry
            break

    if not target:
        print(f"Bulk id '{bulk_id}' not found in API index.")
        sys.exit(1)

    download_uri = target.get("download_uri")
    if not download_uri:
        print("No download_uri in target bulk entry.")
        sys.exit(1)

    os.makedirs(BULK_DIR, exist_ok=True)
    # Derive filename from download URI (preserves actual extension)
    uri_filename = download_uri.rsplit("/", 1)[-1] if "/" in download_uri else f"{bulk_id}.json"
    # Normalize to consistent naming: bulk_id.json or bulk_id.json.gz
    if uri_filename.endswith(".json.gz"):
        filename = f"{bulk_id}.json.gz"
    else:
        filename = f"{bulk_id}.json"
    out_path = os.path.join(BULK_DIR, filename)

    try:
        download_with_progress(download_uri, out_path, label=bulk_id)
    except Exception as e:
        print(f"Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
