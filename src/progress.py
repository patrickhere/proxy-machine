"""Progress tracking context manager for long-running operations.

Provides consistent progress feedback and cancellation support across all
long-running tasks in the Proxy Machine.
"""

import time
from contextlib import contextmanager
from typing import Optional, Callable


class ProgressTracker:
    """Context manager for tracking progress of long-running operations."""

    def __init__(
        self,
        description: str,
        total: Optional[int] = None,
        show_progress: bool = True,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        """Initialize progress tracker.

        Args:
            description: Description of the operation
            total: Total number of items (None for indeterminate progress)
            show_progress: Whether to show progress output
            on_cancel: Optional callback to run on cancellation
        """
        self.description = description
        self.total = total
        self.show_progress = show_progress
        self.on_cancel = on_cancel
        self.current = 0
        self.start_time = None
        self.cancelled = False

    def __enter__(self):
        """Start progress tracking."""
        if self.show_progress:
            print(f"\n{self.description}...", flush=True)
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Complete progress tracking."""
        if self.cancelled and self.on_cancel:
            self.on_cancel()

        if self.show_progress:
            elapsed = time.time() - self.start_time
            if self.cancelled:
                print(
                    f"\n[CANCELLED] {self.description} (after {elapsed:.1f}s)",
                    flush=True,
                )
            elif exc_type is None:
                print(
                    f"\n[OK] {self.description} completed in {elapsed:.1f}s", flush=True
                )
            else:
                print(
                    f"\n[ERROR] {self.description} failed after {elapsed:.1f}s",
                    flush=True,
                )

        return False  # Don't suppress exceptions

    def update(self, amount: int = 1, message: Optional[str] = None):
        """Update progress.

        Args:
            amount: Amount to increment progress by
            message: Optional status message
        """
        self.current += amount

        if not self.show_progress:
            return

        if self.total:
            percentage = (self.current / self.total) * 100
            bar_length = 40
            filled = int(bar_length * self.current / self.total)
            bar = "=" * filled + "-" * (bar_length - filled)

            status = f"\r[{bar}] {self.current}/{self.total} ({percentage:.1f}%)"
            if message:
                status += f" - {message}"

            print(status, end="", flush=True)
        else:
            # Indeterminate progress
            spinner = ["|", "/", "-", "\\"][self.current % 4]
            status = f"\r{spinner} {self.current} processed"
            if message:
                status += f" - {message}"

            print(status, end="", flush=True)

    def cancel(self):
        """Mark operation as cancelled."""
        self.cancelled = True


@contextmanager
def progress(
    description: str,
    total: Optional[int] = None,
    show_progress: bool = True,
    on_cancel: Optional[Callable[[], None]] = None,
):
    """Context manager for progress tracking.

    Usage:
        with progress("Fetching cards", total=100) as p:
            for i in range(100):
                # Do work
                p.update(1, f"Processing card {i}")

    Args:
        description: Description of the operation
        total: Total number of items (None for indeterminate progress)
        show_progress: Whether to show progress output
        on_cancel: Optional callback to run on cancellation

    Yields:
        ProgressTracker instance
    """
    tracker = ProgressTracker(description, total, show_progress, on_cancel)
    try:
        with tracker:
            yield tracker
    except KeyboardInterrupt:
        tracker.cancel()
        raise
