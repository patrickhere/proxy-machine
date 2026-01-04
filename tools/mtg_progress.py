#!/usr/bin/env python3
"""Magic-themed progress bars and status messages for The Proxy Machine."""

import random
import sys
import time
from typing import Optional

# Magic-themed progress messages
PROGRESS_MESSAGES = {
    "fetch": [
        "Summoning creatures from the aether",
        "Tapping mana for card knowledge",
        "Scrying through the multiverse",
        "Consulting the oracle",
        "Drawing from the library",
        "Searching the deck",
        "Shuffling through possibilities",
        "Casting divination spells",
        "Exploring the plane",
        "Gathering the cards",
    ],
    "download": [
        "Channeling card images",
        "Materializing proxies",
        "Conjuring artwork",
        "Manifesting cards",
        "Summoning illustrations",
        "Fetching from the vault",
        "Pulling from the archive",
        "Retrieving card faces",
    ],
    "build": [
        "Constructing the deck",
        "Assembling the collection",
        "Building the library",
        "Organizing the binder",
        "Sorting the cards",
        "Cataloging artifacts",
        "Indexing the collection",
    ],
    "search": [
        "Searching the library",
        "Consulting the grimoire",
        "Examining the codex",
        "Reviewing the spellbook",
        "Scanning the archives",
        "Investigating the vault",
    ],
    "process": [
        "Processing card data",
        "Analyzing the board state",
        "Calculating synergies",
        "Evaluating the meta",
        "Crunching the numbers",
        "Optimizing the deck",
    ],
}


class MagicProgressBar:
    """A fun Magic-themed progress bar for long-running operations."""

    def __init__(
        self,
        total: int,
        prefix: str = "Progress",
        category: str = "process",
        width: int = 40,
        show_percentage: bool = True,
        show_count: bool = True,
        magic_messages: bool = True,
    ):
        """
        Initialize a Magic-themed progress bar.

        Args:
            total: Total number of items to process
            prefix: Prefix label for the progress bar
            category: Message category (fetch, download, build, search, process)
            width: Width of the progress bar in characters
            show_percentage: Whether to show percentage complete
            show_count: Whether to show item count (current/total)
            magic_messages: Whether to show rotating Magic-themed messages
        """
        self.total = total
        self.prefix = prefix
        self.category = category
        self.width = width
        self.show_percentage = show_percentage
        self.show_count = show_count
        self.magic_messages = magic_messages
        self.current = 0
        self.last_message_idx = -1
        self.start_time = time.time()
        self.last_update = 0

    def _get_magic_message(self) -> str:
        """Get a random Magic-themed message for the current category."""
        messages = PROGRESS_MESSAGES.get(self.category, PROGRESS_MESSAGES["process"])
        # Avoid repeating the same message twice in a row
        available = [i for i in range(len(messages)) if i != self.last_message_idx]
        if not available:
            available = list(range(len(messages)))
        idx = random.choice(available)
        self.last_message_idx = idx
        return messages[idx]

    def update(self, current: Optional[int] = None, force: bool = False) -> None:
        """
        Update the progress bar.

        Args:
            current: Current progress (if None, increments by 1)
            force: Force update even if not enough time has passed
        """
        if current is not None:
            self.current = current
        else:
            self.current += 1

        # Throttle updates to avoid excessive terminal writes (update every 0.1s minimum)
        now = time.time()
        if not force and (now - self.last_update) < 0.1 and self.current < self.total:
            return
        self.last_update = now

        self._render()

    def _render(self) -> None:
        """Render the progress bar to the terminal."""
        if self.total == 0:
            percent = 100.0
            filled = self.width
        else:
            percent = min(100.0, (self.current / self.total) * 100)
            filled = int(self.width * self.current // self.total)

        # Build the bar with block characters
        bar = "█" * filled + "░" * (self.width - filled)

        # Build the status line
        parts = [f"\r{self.prefix}"]

        if self.magic_messages and self.current < self.total:
            # Show magic message during progress
            parts.append(f": {self._get_magic_message()}")

        parts.append(f" |{bar}|")

        if self.show_count:
            parts.append(f" {self.current}/{self.total}")

        if self.show_percentage:
            parts.append(f" ({percent:.1f}%)")

        # Add ETA if we're making progress
        if self.current > 0 and self.current < self.total:
            elapsed = time.time() - self.start_time
            rate = self.current / elapsed
            remaining = (self.total - self.current) / rate if rate > 0 else 0
            if remaining < 60:
                parts.append(f" - {remaining:.0f}s remaining")
            elif remaining < 3600:
                parts.append(f" - {remaining/60:.1f}m remaining")
            else:
                parts.append(f" - {remaining/3600:.1f}h remaining")

        message = "".join(parts)
        # Pad to clear previous longer messages
        message = message.ljust(120)
        sys.stdout.write(message)
        sys.stdout.flush()

    def finish(self, message: Optional[str] = None) -> None:
        """
        Complete the progress bar and print a final message.

        Args:
            message: Optional completion message (defaults to "Complete!")
        """
        self.current = self.total
        self._render()

        elapsed = time.time() - self.start_time
        if message is None:
            message = "✓ Complete!"

        # Add timing info
        if elapsed < 60:
            timing = f"{elapsed:.1f}s"
        elif elapsed < 3600:
            timing = f"{elapsed/60:.1f}m"
        else:
            timing = f"{elapsed/3600:.1f}h"

        print(f"\n{message} (took {timing})")


def simple_progress(
    current: int,
    total: int,
    prefix: str = "Progress",
    category: str = "process",
    width: int = 40,
) -> None:
    """
    Simple one-line progress bar update (for use in loops).

    Args:
        current: Current progress
        total: Total items
        prefix: Prefix label
        category: Message category for Magic-themed messages
        width: Progress bar width
    """
    if total == 0:
        percent = 100.0
        filled = width
    else:
        percent = min(100.0, (current / total) * 100)
        filled = int(width * current // total)

    bar = "█" * filled + "░" * (width - filled)

    # Get a magic message
    messages = PROGRESS_MESSAGES.get(category, PROGRESS_MESSAGES["process"])
    message = random.choice(messages)

    status = f"\r{prefix}: {message} |{bar}| {current}/{total} ({percent:.1f}%)"
    sys.stdout.write(status.ljust(120))
    sys.stdout.flush()

    if current >= total:
        print()  # New line when complete


if __name__ == "__main__":
    # Demo the progress bar
    print("Demo: Magic-themed progress bars\n")

    # Test different categories
    for category in ["fetch", "download", "build", "search"]:
        print(f"\nCategory: {category}")
        bar = MagicProgressBar(
            total=50,
            prefix=f"Testing {category}",
            category=category,
            width=30,
        )
        for i in range(51):
            bar.update(i)
            time.sleep(0.05)
        bar.finish(f"{category.title()} complete!")

    print("\n✓ Demo complete!")
