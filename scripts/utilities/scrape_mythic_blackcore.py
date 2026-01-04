#!/usr/bin/env python3
"""Scrape card art from Mythic Black Core gallery.

Usage:
    python scrape_mythic_blackcore.py [start_page] [max_pages]

Example:
    python scrape_mythic_blackcore.py 1 20
"""

import re
import time
from pathlib import Path
import json
import ssl
import urllib.request
import urllib.parse


def download_image(url: str, destination: Path, ssl_context) -> bool:
    """Download an image from URL to destination."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
        )

        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            content = response.read()

        with open(destination, "wb") as f:
            f.write(content)

        print(f"[OK] Downloaded: {destination.name}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return False


def fetch_gallery_api(page_num: int, ssl_context) -> dict:
    """Fetch gallery data from the AJAX API."""
    try:
        # The site uses a custom AJAX endpoint
        api_url = "https://www.mythicblackcore.com/ajax/gallery.php"

        # Build multipart form data (site uses FormData, not urlencoded)
        boundary = "----WebKitFormBoundary" + "".join(
            [str(ord(c)) for c in "RandomString"]
        )

        form_fields = {
            "cpage": str(page_num),
            "type": "",  # Empty = all cards
            "val": "",
            "search": "",
            "order": "recent",  # or 'popular', 'oldest'
            "nsfw": "0",
            "other": "0",
            "ajax_action": "searchGalleryCards",
        }

        # Build multipart/form-data body
        body_parts = []
        for key, value in form_fields.items():
            body_parts.append(f"--{boundary}".encode())
            body_parts.append(f'Content-Disposition: form-data; name="{key}"'.encode())
            body_parts.append(b"")
            body_parts.append(str(value).encode())
        body_parts.append(f"--{boundary}--".encode())
        body_parts.append(b"")

        post_data = b"\r\n".join(body_parts)

        req = urllib.request.Request(
            api_url,
            data=post_data,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode("utf-8"))

        return data

    except Exception as e:
        print(f"Error fetching API page {page_num}: {e}")
        return {}


def scrape_mythic_blackcore(
    start_page: int = 1,
    max_pages: int = 10,
    output_dir: str = None,
) -> None:
    """Scrape Mythic Black Core gallery using AJAX API."""
    if output_dir is None:
        # Default to magic-the-gathering/proxied-decks/misc-alt-arts relative to repo root
        repo_root = Path(__file__).parent.parent
        output_dir = str(
            repo_root / "magic-the-gathering" / "proxied-decks" / "misc-alt-arts"
        )

    # Create SSL context that doesn't verify certificates (for sites with cert issues)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("Scraping Mythic Black Core Gallery")
    print(f"Output directory: {output_path}")
    print(f"Starting from page: {start_page}")
    print(f"Max pages to check: {max_pages}\n")

    all_cards = []
    downloaded = 0
    skipped = 0
    failed = 0

    for page_num in range(start_page, start_page + max_pages):
        print(f"\n[Analyzing] Fetching page {page_num}...")

        api_data = fetch_gallery_api(page_num, ssl_context)

        if not api_data or "data" not in api_data:
            print(f"   No data returned for page {page_num}")
            break

        cards = api_data.get("data", [])
        total_cards = api_data.get("total", 0)

        if not cards:
            print(f"   No cards found on page {page_num}")
            break

        print(f"   Found {len(cards)} cards (total in gallery: {total_cards})")

        for card in cards:
            card_name = card.get("card_edition", "unknown")
            card_id = card.get("id", "")
            user_id = card.get("user_id", "unknown")
            design_date = card.get("design_date", "")

            # Construct image URL from card ID and design date
            # Format: https://s3.us-west-1.wasabisys.com/mythicblackcore-wasabifs/storage/card/proof/YYYY/MM/DD/{id}.png
            image_url = ""
            if card_id and design_date:
                try:
                    # Parse date: '2025-10-15 21:28:47' -> '2025/10/15'
                    date_parts = design_date.split(" ")[0].split("-")
                    if len(date_parts) == 3:
                        year, month, day = date_parts
                        image_url = f"https://s3.us-west-1.wasabisys.com/mythicblackcore-wasabifs/storage/card/proof/{year}/{month}/{day}/{card_id}.png"
                except Exception:
                    pass

            if not image_url:
                print(f"   [SKIP] No image URL for: {card_name}")
                skipped += 1
                continue

            # Generate clean filename: cardname-userid-cardid.png
            clean_name = (
                re.sub(r"[^\w\s-]", "", card_name).strip().replace(" ", "-").lower()
            )
            filename = f"{clean_name}-user{user_id}-{card_id}.png"
            destination = output_path / filename

            # Skip if already exists
            if destination.exists():
                print(f"   [SKIP] Already exists: {filename}")
                skipped += 1
                continue

            # Download with rate limiting
            if download_image(image_url, destination, ssl_context):
                downloaded += 1
                all_cards.append(
                    {
                        "name": card_name,
                        "id": card_id,
                        "user_id": user_id,
                        "design_date": design_date,
                        "image_url": image_url,
                        "local_path": str(destination),
                    }
                )
                time.sleep(0.5)  # Be polite to the server
            else:
                failed += 1

            time.sleep(0.2)  # Small delay between requests

    print(f"\n{'='*60}")
    print("[COMPLETE] Scraping finished!")
    print(f"   Downloaded: {downloaded} images")
    print(f"   Skipped: {skipped} (already existed)")
    print(f"   Failed: {failed}")
    print(f"   Total new: {len(all_cards)} cards")
    print(f"   Location: {output_path}")
    print(f"{'='*60}\n")

    # Save manifest with card metadata
    manifest_path = output_path / "_scrape_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(
            {
                "source": "mythicblackcore.com",
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "cards": all_cards,
                "count": len(all_cards),
                "stats": {
                    "downloaded": downloaded,
                    "skipped": skipped,
                    "failed": failed,
                },
            },
            f,
            indent=2,
        )

    print(f"[Report] Manifest saved to: {manifest_path}")


if __name__ == "__main__":
    import sys

    # Allow command-line arguments
    start_page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    scrape_mythic_blackcore(start_page=start_page, max_pages=max_pages)
