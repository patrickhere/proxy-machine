#!/usr/bin/env python3
"""Duplicate Image Detection using Perceptual Hashing.

Uses imagehash library to compute pHash and dHash for images,
then finds near-duplicates using hamming distance.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple

try:
    import imagehash
    from PIL import Image
except ImportError:
    print("Error: Required libraries not installed")
    print("Run: pip install imagehash pillow")
    sys.exit(1)

# Color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def get_database_path() -> Path:
    """Get path to bulk database."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root.parent / "magic-the-gathering" / "bulk-data" / "bulk.db"
    return db_path


def get_shared_path() -> Path:
    """Get path to shared assets."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    shared_path = project_root.parent / "magic-the-gathering" / "shared"
    return shared_path


def compute_hashes(image_path: Path) -> Tuple[str, str, int, int]:
    """Compute perceptual hashes for an image."""
    try:
        img = Image.open(image_path)

        # Compute hashes
        phash = str(imagehash.phash(img))
        dhash = str(imagehash.dhash(img))

        # Get dimensions
        width, height = img.size

        return phash, dhash, width, height
    except Exception as e:
        print(f"Warning: Failed to process {image_path}: {e}")
        return "", "", 0, 0


def scan_and_hash_images(shared_path: Path, db_path: Path) -> int:
    """Scan all images and compute hashes."""
    if not shared_path.exists():
        print(f"Error: Shared path not found: {shared_path}")
        return 1

    print(f"\nScanning images in {shared_path}")
    print("=" * 60)

    # Find all PNG files
    image_files = list(shared_path.rglob("*.png"))
    print(f"Found {len(image_files):,} images")

    if not image_files:
        print("No images to process")
        return 0

    # Connect to database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Process images
    processed = 0
    skipped = 0
    batch = []
    batch_size = 100

    for img_path in image_files:
        processed += 1

        if processed % 100 == 0:
            print(f"  Processed {processed:,}/{len(image_files):,} images...")

        # Check if already processed
        rel_path = str(img_path.relative_to(shared_path.parent))
        cursor.execute("SELECT path FROM assets WHERE path = ?", (rel_path,))
        if cursor.fetchone():
            skipped += 1
            continue

        # Compute hashes
        phash, dhash, width, height = compute_hashes(img_path)

        if not phash:
            continue

        file_size = img_path.stat().st_size
        created_at = datetime.now().isoformat()

        batch.append(
            (rel_path, phash, dhash, width, height, None, file_size, created_at)
        )

        if len(batch) >= batch_size:
            cursor.executemany(
                "INSERT OR REPLACE INTO assets (path, phash, dhash, width, height, quality_score, file_size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
            conn.commit()
            batch.clear()

    # Flush remaining
    if batch:
        cursor.executemany(
            "INSERT OR REPLACE INTO assets (path, phash, dhash, width, height, quality_score, file_size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        conn.commit()

    conn.close()

    print(f"\n{GREEN}Hashing complete!{RESET}")
    print(f"Processed: {processed:,}")
    print(f"Skipped (already hashed): {skipped:,}")
    print(f"New hashes: {processed - skipped:,}")
    print()

    return 0


def find_duplicates(db_path: Path, threshold: int = 5) -> int:
    """Find duplicate images using hamming distance with optimized algorithm."""
    print(f"\nFinding duplicates (threshold: {threshold} bits)")
    print("=" * 60)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get all hashed images
    cursor.execute("SELECT path, phash, dhash FROM assets WHERE phash IS NOT NULL")
    assets = cursor.fetchall()
    conn.close()

    print(f"Comparing {len(assets):,} images...")
    print("Using optimized algorithm (grouping by hash prefix)...")

    # Convert hashes to imagehash objects and group by prefix for faster comparison
    hash_data = []
    for path, phash, dhash in assets:
        try:
            hash_obj = imagehash.hex_to_hash(phash)
            # Use first 4 bits as bucket key for pre-filtering
            bucket = int(phash[:4], 16)
            hash_data.append((path, hash_obj, bucket))
        except Exception:
            continue

    # Group by bucket to reduce comparisons
    from collections import defaultdict

    buckets = defaultdict(list)
    for path, hash_obj, bucket in hash_data:
        buckets[bucket].append((path, hash_obj))

    print(f"Grouped into {len(buckets)} buckets for faster comparison")

    duplicates = []
    checked = set()
    total_comparisons = 0

    # Compare within buckets and adjacent buckets only
    bucket_keys = sorted(buckets.keys())
    for idx, bucket_key in enumerate(bucket_keys):
        if idx % 50 == 0 and idx > 0:
            print(
                f"  Processed {idx}/{len(bucket_keys)} buckets ({total_comparisons:,} comparisons)..."
            )

        # Get items from current bucket and adjacent buckets (for threshold tolerance)
        items_to_compare = buckets[bucket_key].copy()
        for adjacent in range(
            max(0, bucket_key - threshold), min(0xFFFF, bucket_key + threshold + 1)
        ):
            if adjacent != bucket_key and adjacent in buckets:
                items_to_compare.extend(buckets[adjacent])

        # Compare within this group
        for i, (path1, hash1) in enumerate(buckets[bucket_key]):
            for j, (path2, hash2) in enumerate(items_to_compare):
                if path1 >= path2:  # Avoid duplicate comparisons
                    continue

                pair = tuple(sorted([path1, path2]))
                if pair in checked:
                    continue
                checked.add(pair)

                total_comparisons += 1
                distance = hash1 - hash2

                if distance <= threshold:
                    duplicates.append((path1, path2, distance))

    print(
        f"\nTotal comparisons: {total_comparisons:,} (vs {len(assets) * (len(assets) - 1) // 2:,} naive)"
    )
    print(
        f"Speedup: {(len(assets) * (len(assets) - 1) // 2) / max(total_comparisons, 1):.1f}x"
    )

    if not duplicates:
        print(f"\n{GREEN}No duplicates found!{RESET}")
        return 0

    print(f"\n{YELLOW}Found {len(duplicates):,} potential duplicates:{RESET}")
    print("-" * 60)

    for path1, path2, distance in sorted(duplicates, key=lambda x: x[2]):
        print(f"  Distance {distance}: ")
        print(f"    {path1}")
        print(f"    {path2}")

    print()
    return 0


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect duplicate images using perceptual hashing"
    )
    parser.add_argument("--scan", action="store_true", help="Scan and hash all images")
    parser.add_argument("--find", action="store_true", help="Find duplicates")
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Hamming distance threshold (default: 5)",
    )

    args = parser.parse_args()

    db_path = get_database_path()
    shared_path = get_shared_path()

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        print("Run 'make bulk-index-build' first")
        return 1

    if args.scan:
        return scan_and_hash_images(shared_path, db_path)
    elif args.find:
        return find_duplicates(db_path, args.threshold)
    else:
        print("Usage: python detect_duplicates.py --scan | --find [--threshold N]")
        print("\nExamples:")
        print("  python detect_duplicates.py --scan          # Hash all images")
        print("  python detect_duplicates.py --find          # Find duplicates")
        print("  python detect_duplicates.py --find --threshold 3  # Stricter matching")
        return 1


if __name__ == "__main__":
    sys.exit(main())
