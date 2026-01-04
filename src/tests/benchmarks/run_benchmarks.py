#!/usr/bin/env python3
"""Benchmark suite for performance regression testing.

Measures critical operations to establish baseline and detect regressions.

Usage:
    python tests/benchmarks/run_benchmarks.py
    # or
    make benchmark

Output:
    benchmarks/current.json - Latest benchmark results
"""

import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 0.001:
        return f"{seconds * 1000000:.2f}μs"
    elif seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    else:
        return f"{seconds:.2f}s"


def format_memory(bytes_val: int) -> str:
    """Format memory in human-readable format."""
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.2f}KB"
    else:
        return f"{bytes_val / 1024 / 1024:.2f}MB"


class Benchmark:
    """Base class for benchmarks."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.duration = 0.0
        self.memory_peak = 0
        self.success = False
        self.error = None

    def run(self) -> Dict[str, Any]:
        """Run benchmark and return results."""
        print(f"\nRunning: {self.name}")
        print(f"  {self.description}")

        tracemalloc.start()
        start_time = time.time()

        try:
            self.execute()
            self.success = True
        except Exception as e:
            self.success = False
            self.error = str(e)
            print(f"  [FAIL] {e}")

        self.duration = time.time() - start_time
        current, peak = tracemalloc.get_traced_memory()
        self.memory_peak = peak
        tracemalloc.stop()

        if self.success:
            print(
                f"  [PASS] {format_duration(self.duration)} | Peak memory: {format_memory(self.memory_peak)}"
            )

        return {
            "name": self.name,
            "description": self.description,
            "duration_seconds": self.duration,
            "memory_peak_bytes": self.memory_peak,
            "success": self.success,
            "error": self.error,
        }

    def execute(self):
        """Override in subclass."""
        raise NotImplementedError


class DeckImportBenchmark(Benchmark):
    """Benchmark deck parsing."""

    def __init__(self):
        super().__init__("deck_import", "Parse 60-card MTGA format deck")

    def execute(self):
        from pathlib import Path

        # Use fixture file
        deck_file = Path("tests/data/fixtures/red_burn.txt")
        if not deck_file.exists():
            raise FileNotFoundError(f"Fixture not found: {deck_file}")

        content = deck_file.read_text()
        lines = content.strip().split("\n")

        # Simple parsing (mimics deck parser logic)
        total_cards = 0
        for line in lines:
            line = line.strip()
            if (
                not line
                or line.startswith("//")
                or line.lower() in ["deck", "sideboard"]
            ):
                continue

            # Extract quantity (first number in line)
            parts = line.split()
            if parts and parts[0].isdigit():
                total_cards += int(parts[0])

        if total_cards < 50:
            raise ValueError(f"Expected ~60 cards, got {total_cards}")


class TokenExpansionBenchmark(Benchmark):
    """Benchmark token relationship expansion."""

    def __init__(self):
        super().__init__("token_expansion", "Resolve token relationships for 20 cards")

    def execute(self):
        from db.bulk_index import query_cards_optimized, DB_PATH
        from pathlib import Path

        if not Path(DB_PATH).exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")

        # Query cards that produce tokens
        cards = query_cards_optimized(card_type="creature", set_filter="znr", limit=20)

        if len(cards) < 10:
            raise ValueError(f"Expected 20 cards, got {len(cards)}")

        # Simulate token lookup (basic query)
        import sqlite3

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        for card in cards[:20]:
            cur.execute(
                """
                SELECT related_card_id, relationship_type
                FROM card_relationships
                WHERE source_card_id = ? AND relationship_type = 'token'
            """,
                (card["id"],),
            )
            tokens = cur.fetchall()

        conn.close()


class PDFGenerationBenchmark(Benchmark):
    """Benchmark PDF layout calculation."""

    def __init__(self):
        super().__init__("pdf_generation", "Calculate layout for 9-card PDF")

    def execute(self):
        # Simulate PDF layout calculation
        # (actual PDF generation requires ReportLab, this tests the logic)

        cards = 9
        cards_per_page = 9
        card_width = 2.5  # inches
        card_height = 3.5  # inches
        margin = 0.5  # inches

        # Calculate grid
        cols = 3
        rows = 3

        positions = []
        for i in range(cards):
            row = i // cols
            col = i % cols
            x = margin + (col * card_width)
            y = margin + (row * card_height)
            positions.append((x, y))

        if len(positions) != cards:
            raise ValueError(f"Expected {cards} positions, got {len(positions)}")


class ImageFetchBenchmark(Benchmark):
    """Benchmark image download simulation."""

    def __init__(self):
        super().__init__("image_fetch", "Simulate fetching 10 card images")

    def execute(self):
        from db.bulk_index import query_cards_optimized, DB_PATH
        from pathlib import Path

        if not Path(DB_PATH).exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")

        # Query 10 cards
        cards = query_cards_optimized(card_type="creature", set_filter="znr", limit=10)

        if len(cards) < 10:
            raise ValueError(f"Expected 10 cards, got {len(cards)}")

        # Simulate image URL construction (no actual download)
        image_urls = []
        for card in cards[:10]:
            if "image_uris" in card and card["image_uris"]:
                try:
                    uris = (
                        json.loads(card["image_uris"])
                        if isinstance(card["image_uris"], str)
                        else card["image_uris"]
                    )
                    if "normal" in uris:
                        image_urls.append(uris["normal"])
                except:
                    pass

        # Simulate network delay (very small)
        time.sleep(0.01 * len(image_urls))


class MemoryUsageBenchmark(Benchmark):
    """Benchmark memory usage for large query."""

    def __init__(self):
        super().__init__("memory_usage", "Query 100 cards and measure memory")

    def execute(self):
        from db.bulk_index import query_cards_optimized, DB_PATH
        from pathlib import Path

        if not Path(DB_PATH).exists():
            raise FileNotFoundError(f"Database not found: {DB_PATH}")

        # Query 100 cards
        cards = query_cards_optimized(card_type="creature", set_filter="znr", limit=100)

        if len(cards) < 50:
            raise ValueError(f"Expected 100 cards, got {len(cards)}")

        # Hold in memory briefly
        card_data = [dict(c) for c in cards]

        if len(card_data) < 50:
            raise ValueError("Failed to load card data")


def run_all_benchmarks() -> Dict[str, Any]:
    """Run all benchmarks and return results."""
    benchmarks = [
        DeckImportBenchmark(),
        TokenExpansionBenchmark(),
        PDFGenerationBenchmark(),
        ImageFetchBenchmark(),
        MemoryUsageBenchmark(),
    ]

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "system": {
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
        },
        "benchmarks": [],
    }

    print("=" * 70)
    print("  BENCHMARK SUITE")
    print("=" * 70)

    for benchmark in benchmarks:
        result = benchmark.run()
        results["benchmarks"].append(result)

    # Calculate summary
    total_duration = sum(b["duration_seconds"] for b in results["benchmarks"])
    total_memory = max(b["memory_peak_bytes"] for b in results["benchmarks"])
    success_count = sum(1 for b in results["benchmarks"] if b["success"])

    results["summary"] = {
        "total_duration_seconds": total_duration,
        "peak_memory_bytes": total_memory,
        "benchmarks_run": len(benchmarks),
        "benchmarks_passed": success_count,
        "benchmarks_failed": len(benchmarks) - success_count,
    }

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"Total duration: {format_duration(total_duration)}")
    print(f"Peak memory: {format_memory(total_memory)}")
    print(f"Passed: {success_count}/{len(benchmarks)}")

    return results


def save_results(results: Dict[str, Any], filename: str = "benchmarks/current.json"):
    """Save benchmark results to file."""
    output_path = Path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")


def main():
    """Run benchmarks and save results."""
    results = run_all_benchmarks()
    save_results(results)

    # Exit with error if any benchmarks failed
    if results["summary"]["benchmarks_failed"] > 0:
        print("\n[FAIL] Some benchmarks failed")
        return 1

    print("\n[PASS] All benchmarks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
