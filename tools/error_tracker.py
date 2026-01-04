#!/usr/bin/env python3
"""Error rate tracking and monitoring.

Tracks exceptions by type and provides summary statistics.
"""

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ErrorTracker:
    """Track errors and generate statistics."""

    def __init__(self, output_file: str = "logs/error_summary.json"):
        self.output_file = Path(output_file)
        self.errors: Dict[str, list] = defaultdict(list)
        self.start_time = time.time()

    def record_error(
        self, error_type: str, message: str, context: Optional[Dict[str, Any]] = None
    ):
        """Record an error occurrence.

        Args:
            error_type: Type of error (exception class name)
            message: Error message
            context: Optional context dict (operation_id, deck_id, etc.)
        """
        self.errors[error_type].append(
            {
                "timestamp": datetime.now().isoformat(),
                "message": message,
                "context": context or {},
            }
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get error summary statistics."""
        total_errors = sum(len(errors) for errors in self.errors.values())
        duration = time.time() - self.start_time

        error_counts = {
            error_type: len(errors) for error_type, errors in self.errors.items()
        }

        # Sort by count descending
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "duration_seconds": duration,
            "total_errors": total_errors,
            "unique_error_types": len(self.errors),
            "error_counts": dict(sorted_errors),
            "errors_per_minute": (total_errors / duration * 60) if duration > 0 else 0,
        }

    def save_summary(self):
        """Save error summary to file."""
        summary = self.get_summary()

        # Include recent errors (last 10 of each type)
        summary["recent_errors"] = {}
        for error_type, errors in self.errors.items():
            summary["recent_errors"][error_type] = errors[-10:]

        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, "w") as f:
            json.dump(summary, f, indent=2)

    def print_summary(self):
        """Print error summary to console."""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("  ERROR SUMMARY")
        print("=" * 60)
        print(f"Duration: {summary['duration_seconds']:.1f}s")
        print(f"Total errors: {summary['total_errors']}")
        print(f"Unique error types: {summary['unique_error_types']}")
        print(f"Error rate: {summary['errors_per_minute']:.2f} errors/min")

        if summary["error_counts"]:
            print("\nError counts by type:")
            for error_type, count in summary["error_counts"].items():
                print(f"  {error_type}: {count}")

        print("=" * 60 + "\n")


# Global tracker instance
_tracker: Optional[ErrorTracker] = None


def get_tracker() -> ErrorTracker:
    """Get or create global error tracker."""
    global _tracker
    if _tracker is None:
        _tracker = ErrorTracker()
    return _tracker


def record_error(
    error_type: str, message: str, context: Optional[Dict[str, Any]] = None
):
    """Record an error (convenience function)."""
    get_tracker().record_error(error_type, message, context)


def save_error_summary():
    """Save error summary (convenience function)."""
    if _tracker:
        _tracker.save_summary()


def print_error_summary():
    """Print error summary (convenience function)."""
    if _tracker:
        _tracker.print_summary()


# Example usage
if __name__ == "__main__":
    tracker = ErrorTracker()

    # Simulate some errors
    tracker.record_error("NetworkError", "Connection timeout", {"url": "example.com"})
    tracker.record_error("NetworkError", "Connection refused", {"url": "example.org"})
    tracker.record_error("ValidationError", "Invalid deck format", {"line": 42})
    tracker.record_error("DatabaseError", "Query failed", {"table": "prints"})
    tracker.record_error(
        "NetworkError", "DNS resolution failed", {"url": "example.net"}
    )

    # Print and save summary
    tracker.print_summary()
    tracker.save_summary()

    print(f"Summary saved to: {tracker.output_file}")
