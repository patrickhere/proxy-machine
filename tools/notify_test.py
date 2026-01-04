#!/usr/bin/env python3
"""
Notifications test CLI

Sends a sample notification through the existing notification channels
(macos/webhook) using create_pdf helpers. Honors current configuration.
"""

from __future__ import annotations

import os
import sys

# Ensure parent directory (proxy-machine/) is on sys.path so 'create_pdf' can be imported
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

try:
    import create_pdf
except Exception as e:
    print(f"Failed to import create_pdf: {e}")
    raise SystemExit(1)


def main() -> None:
    create_pdf._notify(
        "Proxy Machine Test",
        "This is a sample notification from notifications-test.",
        event="notifications_test",
    )
    print("Notification dispatched (check Notification Center and/or webhook)")


if __name__ == "__main__":
    main()
