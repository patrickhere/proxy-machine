#!/usr/bin/env python3
"""
Script to identify and re-fetch double-faced cards where the land face should be downloaded.
Works with existing database and files, no full rebuild needed.
"""

import os
import sys
from pathlib import Path

# Add proxy-machine to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from create_pdf import (
    _slugify,
    _fetch_all_basic_lands_from_scryfall,
    _fetch_all_non_basic_lands,
)


def _fetch_all_lands(
    *,
    land_type: str = "both",
    lang_preference: str = "en",
    land_set_filter: str | None = None,
    dry_run: bool = False,
    retry_only: bool = False,
) -> None:
    """Thin wrapper around the land fetch helpers in `create_pdf.py`.

    This mirrors the previous `_fetch_all_lands` import used by this script while
    delegating to the public functions that handle basic and non-basic land
    workflows. Parameters default to the original script behaviour (both land
    types, English) and are forwarded to the underlying helpers.
    """

    target_sets = [land_set_filter] if land_set_filter else [None]

    for set_code in target_sets:
        if land_type in {"basic", "both"}:
            _fetch_all_basic_lands_from_scryfall(
                retry_only=retry_only,
                lang_preference=lang_preference,
                dry_run=dry_run,
                land_set_filter=set_code,
            )

        if land_type in {"nonbasic", "both"}:
            _fetch_all_non_basic_lands(
                retry_only=retry_only,
                lang_preference=lang_preference,
                dry_run=dry_run,
                land_set_filter=set_code,
            )


def find_potential_dfc_lands():
    """Find cards in the database that might be DFCs with land faces."""
    try:
        import sqlite3

        import sys

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from bulk_paths import bulk_db_path

        db_path = str(bulk_db_path())

        if not os.path.exists(db_path):
            print("❌ Database not found. Please build it first.")
            return []

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Find cards with "transform" or "modal_dfc" layout that have "land" in type_line
        cur.execute(
            """
            SELECT DISTINCT set_code, name, type_line, layout, collector_number
            FROM prints
            WHERE layout IN ('transform', 'modal_dfc', 'reversible_card')
            AND (type_line LIKE '%Land%' OR type_line LIKE '%land%')
            ORDER BY set_code, collector_number
        """
        )

        results = cur.fetchall()
        conn.close()

        return results
    except Exception as e:
        print(f"❌ Error querying database: {e}")
        return []


def check_existing_files(set_code: str, card_name: str):
    """Check what files we currently have for this card."""
    basic_path = Path(
        f"../magic-the-gathering/shared/basic-lands/{_slugify(set_code).lower()}"
    )
    nonbasic_path = Path(
        f"../magic-the-gathering/shared/non-basic-lands/{_slugify(set_code).lower()}"
    )

    name_slug = _slugify(card_name)
    files_found = []

    for base_path in [basic_path, nonbasic_path]:
        if base_path.exists():
            for file_path in base_path.glob(f"{name_slug}*"):
                files_found.append(str(file_path))

    return files_found


def main():
    """Main function to find and optionally re-fetch DFC lands."""
    print("🔍 DOUBLE-FACED CARD LAND CHECKER")
    print("=" * 50)

    # Find potential DFC lands
    dfc_lands = find_potential_dfc_lands()

    if not dfc_lands:
        print("✅ No double-faced lands found or database unavailable.")
        return

    print(f"Found {len(dfc_lands)} potential double-faced lands:")

    # Group by set for easier processing
    by_set = {}
    for set_code, name, type_line, layout, collector in dfc_lands:
        if set_code not in by_set:
            by_set[set_code] = []
        by_set[set_code].append((name, type_line, layout, collector))

    # Show summary
    for set_code, cards in by_set.items():
        print(f"\n📦 {set_code.upper()} ({len(cards)} cards):")
        for name, type_line, layout, collector in cards[:3]:  # Show first 3
            existing = check_existing_files(set_code, name)
            status = f"({len(existing)} files)" if existing else "(no files)"
            print(f"   - {name} #{collector} {status}")
        if len(cards) > 3:
            print(f"   ... and {len(cards) - 3} more")

    # Ask what to do
    print(f"\n🤔 Found {len(dfc_lands)} potential DFC lands across {len(by_set)} sets.")
    print("Options:")
    print("  1. Re-fetch all affected sets (recommended)")
    print("  2. Re-fetch specific sets")
    print("  3. Just show analysis (no downloads)")

    choice = input("\nChoice [1/2/3]: ").strip()

    if choice == "1":
        # Re-fetch all affected sets
        print("\n🔄 Re-fetching all affected sets...")
        for set_code in by_set.keys():
            print(f"\n🔄 Fetching {set_code.upper()}...")
            try:
                _fetch_all_lands(
                    land_type="both",
                    lang_preference="en",
                    land_set_filter=set_code,
                    dry_run=False,
                )
                print(f"✅ Completed {set_code.upper()}")
            except Exception as e:
                print(f"❌ Error fetching {set_code}: {e}")

    elif choice == "2":
        # Re-fetch specific sets
        print("\nAvailable sets:")
        set_list = list(by_set.keys())
        for i, set_code in enumerate(set_list, 1):
            print(f"  {i}. {set_code.upper()} ({len(by_set[set_code])} cards)")

        selected = input("\nEnter set numbers (comma-separated): ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in selected.split(",") if x.strip()]
            for idx in indices:
                if 0 <= idx < len(set_list):
                    set_code = set_list[idx]
                    print(f"\n🔄 Fetching {set_code.upper()}...")
                    _fetch_all_lands(
                        land_type="both",
                        lang_preference="en",
                        land_set_filter=set_code,
                        dry_run=False,
                    )
                    print(f"✅ Completed {set_code.upper()}")
        except (ValueError, IndexError) as e:
            print(f"❌ Invalid selection: {e}")

    else:
        print("\n✅ Analysis complete. No downloads performed.")


if __name__ == "__main__":
    main()
