#!/usr/bin/env python3
"""Set release automation.

Monitors Scryfall for new set releases and automates:
- Fetching new set data
- Downloading basics and tokens
- Tracking set changelog
- Notifications
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import subprocess


SET_TRACKER_FILE = Path("data/set_releases.json")
SCRYFALL_SETS_API = "https://api.scryfall.com/sets"


def load_tracked_sets() -> Dict:
    """Load tracked sets from file."""
    if not SET_TRACKER_FILE.exists():
        return {"sets": {}, "last_check": None}

    with open(SET_TRACKER_FILE) as f:
        return json.load(f)


def save_tracked_sets(data: Dict):
    """Save tracked sets to file."""
    SET_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SET_TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2)


def fetch_scryfall_sets() -> List[Dict]:
    """Fetch all sets from Scryfall API."""
    try:
        import requests

        response = requests.get(SCRYFALL_SETS_API)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch sets: {e}")
        return []


def check_for_new_sets() -> List[Dict]:
    """Check for new sets released since last check."""
    tracked = load_tracked_sets()
    current_sets = fetch_scryfall_sets()

    if not current_sets:
        return []

    new_sets = []
    for set_data in current_sets:
        set_code = set_data.get("code")
        if set_code and set_code not in tracked["sets"]:
            # Check if released (not future)
            released_at = set_data.get("released_at")
            if released_at:
                release_date = datetime.fromisoformat(released_at)
                if release_date <= datetime.now():
                    new_sets.append(set_data)

    return new_sets


def auto_fetch_set_basics(set_code: str, dry_run: bool = True) -> bool:
    """Automatically fetch basics for a new set."""
    print(f"\n[AUTO-FETCH] Basics for set {set_code.upper()}")

    if dry_run:
        print("  [DRY RUN] Would run: make fetch-basics SET={set_code}")
        return True

    try:
        result = subprocess.run(
            ["make", "fetch-basics", f"SET={set_code}"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print(f"  [OK] Fetched basics for {set_code}")
            return True
        else:
            print(f"  [ERROR] Failed to fetch basics: {result.stderr}")
            return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def auto_fetch_set_tokens(set_code: str, dry_run: bool = True) -> bool:
    """Automatically fetch tokens for a new set."""
    print(f"\n[AUTO-FETCH] Tokens for set {set_code.upper()}")

    if dry_run:
        print("  [DRY RUN] Would fetch tokens for set")
        return True

    # Implementation would call token fetch with set filter
    print(f"  [OK] Would fetch tokens for {set_code}")
    return True


def generate_set_changelog(new_sets: List[Dict]) -> str:
    """Generate changelog for new sets."""
    if not new_sets:
        return ""

    changelog = []
    changelog.append(
        f"# Set Release Changelog - {datetime.now().strftime('%Y-%m-%d')}\n"
    )

    for set_data in new_sets:
        changelog.append(
            f"## {set_data.get('name')} ({set_data.get('code', '').upper()})"
        )
        changelog.append(f"- Released: {set_data.get('released_at')}")
        changelog.append(f"- Type: {set_data.get('set_type')}")
        changelog.append(f"- Cards: {set_data.get('card_count', 0)}")
        if set_data.get("digital"):
            changelog.append("- Digital only")
        changelog.append("")

    return "\n".join(changelog)


def send_notification(title: str, message: str):
    """Send notification about new set."""
    print("\n[NOTIFICATION]")
    print(f"  Title: {title}")
    print(f"  Message: {message}")

    # Could integrate with notification system here
    # For now, just print


def process_new_sets(dry_run: bool = True, auto_fetch: bool = False):
    """Process new sets: track, notify, and optionally fetch."""
    print("\n" + "=" * 70)
    print("  SET RELEASE AUTOMATION")
    print("=" * 70)

    new_sets = check_for_new_sets()

    if not new_sets:
        print("\n[INFO] No new sets found")
        return

    print(f"\n[FOUND] {len(new_sets)} new set(s)")

    for set_data in new_sets:
        set_code = set_data.get("code")
        set_name = set_data.get("name")

        print(f"\n[NEW SET] {set_name} ({set_code.upper()})")
        print(f"  Released: {set_data.get('released_at')}")
        print(f"  Type: {set_data.get('set_type')}")
        print(f"  Cards: {set_data.get('card_count', 0)}")

        # Send notification
        send_notification(
            f"New MTG Set: {set_name}",
            f"{set_name} ({set_code.upper()}) is now available",
        )

        # Auto-fetch if enabled
        if auto_fetch:
            auto_fetch_set_basics(set_code, dry_run)
            auto_fetch_set_tokens(set_code, dry_run)

    # Generate changelog
    changelog = generate_set_changelog(new_sets)
    changelog_file = Path(f"data/set_changelog_{datetime.now().strftime('%Y%m%d')}.md")

    if not dry_run:
        changelog_file.parent.mkdir(parents=True, exist_ok=True)
        changelog_file.write_text(changelog)
        print(f"\n[OK] Changelog written to: {changelog_file}")
    else:
        print(f"\n[DRY RUN] Would write changelog to: {changelog_file}")

    # Update tracked sets
    if not dry_run:
        tracked = load_tracked_sets()
        for set_data in new_sets:
            tracked["sets"][set_data["code"]] = {
                "name": set_data["name"],
                "released_at": set_data["released_at"],
                "discovered_at": datetime.now().isoformat(),
            }
        tracked["last_check"] = datetime.now().isoformat()
        save_tracked_sets(tracked)
        print("[OK] Updated set tracker")

    print("\n" + "=" * 70)


def list_tracked_sets():
    """List all tracked sets."""
    tracked = load_tracked_sets()

    print("\n" + "=" * 70)
    print("  TRACKED SETS")
    print("=" * 70)

    if not tracked["sets"]:
        print("\n[INFO] No sets tracked yet")
        return

    print(f"\nLast check: {tracked.get('last_check', 'Never')}")
    print(f"Total sets: {len(tracked['sets'])}\n")

    for code, data in sorted(
        tracked["sets"].items(), key=lambda x: x[1].get("released_at", ""), reverse=True
    )[:20]:
        print(f"{code.upper():<8} {data['name']:<40} {data['released_at']}")

    if len(tracked["sets"]) > 20:
        print(f"\n... and {len(tracked['sets']) - 20} more")

    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python set_release_automation.py <command> [options]")
        print("\nCommands:")
        print("  check               - Check for new sets (dry run)")
        print("  check --apply       - Check and track new sets")
        print("  check --auto-fetch  - Check and auto-fetch basics/tokens")
        print("  list                - List tracked sets")
        print("\nExamples:")
        print("  python set_release_automation.py check")
        print("  python set_release_automation.py check --apply")
        print("  python set_release_automation.py check --apply --auto-fetch")
        print("  python set_release_automation.py list")
        return 1

    command = sys.argv[1]

    if command == "check":
        dry_run = "--apply" not in sys.argv
        auto_fetch = "--auto-fetch" in sys.argv

        process_new_sets(dry_run, auto_fetch)

        if dry_run:
            print("\n[INFO] This was a dry run. Use --apply to track sets.")

        return 0

    if command == "list":
        list_tracked_sets()
        return 0

    print(f"[ERROR] Unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
