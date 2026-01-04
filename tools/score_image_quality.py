#!/usr/bin/env python3
"""Image Quality Scoring Tool.

Computes quality scores for images using:
- Sharpness (Laplacian variance)
- Entropy (texture complexity)
- Brightness (mean luminance)
- Resolution check (>= 300 DPI equivalent)
"""

import sqlite3
import sys
from pathlib import Path
from typing import Tuple

try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError:
    print("Error: Required libraries not installed")
    print("Run: pip install opencv-python-headless pillow numpy")
    sys.exit(1)

# Color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def compute_sharpness(image_array: np.ndarray) -> float:
    """Compute sharpness using Laplacian variance."""
    gray = (
        cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        if len(image_array.shape) == 3
        else image_array
    )
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()
    return float(variance)


def compute_entropy(image_array: np.ndarray) -> float:
    """Compute entropy for texture complexity."""
    gray = (
        cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        if len(image_array.shape) == 3
        else image_array
    )
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.flatten() / hist.sum()
    hist = hist[hist > 0]  # Remove zero bins
    entropy = -np.sum(hist * np.log2(hist))
    return float(entropy)


def compute_brightness(image_array: np.ndarray) -> float:
    """Compute mean luminance."""
    gray = (
        cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        if len(image_array.shape) == 3
        else image_array
    )
    return float(gray.mean())


def compute_quality_score(image_path: Path) -> Tuple[float, dict]:
    """Compute overall quality score for an image."""
    try:
        # Load image
        img = Image.open(image_path)
        img_array = np.array(img)

        # Compute metrics
        sharpness = compute_sharpness(img_array)
        entropy = compute_entropy(img_array)
        brightness = compute_brightness(img_array)

        # Check resolution (MTG cards are typically 745x1040 at 300 DPI)
        width, height = img.size
        min_dimension = min(width, height)
        resolution_score = 1.0 if min_dimension >= 700 else (min_dimension / 700.0)

        # Normalize metrics to 0-1 range
        # Sharpness: typical range 0-1000, good > 100
        sharpness_norm = min(sharpness / 100.0, 1.0)

        # Entropy: typical range 0-8, good > 6
        entropy_norm = min(entropy / 8.0, 1.0)

        # Brightness: typical range 0-255, good around 100-150
        brightness_norm = 1.0 - abs(brightness - 127.5) / 127.5

        # Weighted combination
        quality_score = (
            sharpness_norm * 0.4
            + entropy_norm * 0.3
            + brightness_norm * 0.1
            + resolution_score * 0.2
        )

        metrics = {
            "sharpness": sharpness,
            "entropy": entropy,
            "brightness": brightness,
            "resolution": min_dimension,
            "sharpness_norm": sharpness_norm,
            "entropy_norm": entropy_norm,
            "brightness_norm": brightness_norm,
            "resolution_norm": resolution_score,
        }

        return quality_score, metrics

    except Exception as e:
        print(f"Warning: Failed to score {image_path}: {e}")
        return 0.0, {}


def score_images(shared_path: Path, db_path: Path, rescore: bool = False) -> int:
    """Score all images and update database."""
    if not shared_path.exists():
        print(f"Error: Shared path not found: {shared_path}")
        return 1

    print(f"\nScoring image quality in {shared_path}")
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
    low_quality = []

    for img_path in image_files:
        processed += 1

        if processed % 50 == 0:
            print(f"  Processed {processed:,}/{len(image_files):,} images...")

        rel_path = str(img_path.relative_to(shared_path.parent))

        # Check if already scored
        if not rescore:
            cursor.execute(
                "SELECT quality_score FROM assets WHERE path = ? AND quality_score IS NOT NULL",
                (rel_path,),
            )
            if cursor.fetchone():
                skipped += 1
                continue

        # Compute quality score
        quality_score, metrics = compute_quality_score(img_path)

        if quality_score == 0.0:
            continue

        # Track low quality images
        if quality_score < 0.5:
            low_quality.append((rel_path, quality_score))

        # Update database
        cursor.execute(
            "UPDATE assets SET quality_score = ? WHERE path = ?",
            (quality_score, rel_path),
        )

        if processed % 100 == 0:
            conn.commit()

    conn.commit()
    conn.close()

    print(f"\n{GREEN}Scoring complete!{RESET}")
    print(f"Processed: {processed:,}")
    print(f"Skipped (already scored): {skipped:,}")
    print(f"New scores: {processed - skipped:,}")

    if low_quality:
        print(f"\n{YELLOW}Low quality images found: {len(low_quality)}{RESET}")
        print("-" * 60)
        for path, score in sorted(low_quality, key=lambda x: x[1])[:20]:
            print(f"  {score:.2f}: {path}")
        if len(low_quality) > 20:
            print(f"  ... and {len(low_quality) - 20} more")

    print()
    return 0


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Score image quality")
    parser.add_argument(
        "--rescore", action="store_true", help="Re-score already scored images"
    )

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root.parent / "magic-the-gathering" / "bulk-data" / "bulk.db"
    shared_path = project_root.parent / "magic-the-gathering" / "shared"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        print("Run 'make bulk-index-build' first")
        return 1

    return score_images(shared_path, db_path, args.rescore)


if __name__ == "__main__":
    sys.exit(main())
