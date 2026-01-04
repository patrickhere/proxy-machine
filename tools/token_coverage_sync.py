#!/usr/bin/env python3
"""Token coverage auto-sync.

Cron-friendly script to compare Scryfall catalog with local library
and stage missing downloads automatically.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set


SYNC_LOG = Path("logs/token_sync.log")
MISSING_TOKENS = Path("data/missing_tokens.json")


def log_message(message: str, level: str = "INFO"):
    """Log message to file and console."""
    timestamp = datetime.now().isoformat()
    log_line = f"[{timestamp}] [{level}] {message}"

    print(log_line)

    # Append to log file
    SYNC_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_LOG, "a") as f:
        f.write(log_line + "\n")


def get_scryfall_tokens() -> List[Dict]:
    """Fetch all tokens from Scryfall."""
    try:
        import requests

        log_message("Fetching tokens from Scryfall API...")

        response = requests.get("https://api.scryfall.com/cards/search?q=t:token")
        response.raise_for_status()

        data = response.json()
        tokens = data.get("data", [])

        # Handle pagination
        while data.get("has_more"):
            next_page = data.get("next_page")
            if not next_page:
                break

            response = requests.get(next_page)
            response.raise_for_status()
            data = response.json()
            tokens.extend(data.get("data", []))

        log_message(f"Found {len(tokens)} tokens in Scryfall catalog")
        return tokens

    except Exception as e:
        log_message(f"Failed to fetch Scryfall tokens: {e}", "ERROR")
        return []


def get_local_tokens() -> Set[str]:
    """Get set of token IDs present locally."""
    token_dir = Path("shared/tokens")

    if not token_dir.exists():
        log_message(f"Token directory not found: {token_dir}", "WARN")
        return set()

    local_tokens = set()

    # Scan for token files
    for file in token_dir.rglob("*"):
        if file.is_file() and file.suffix.lower() in {".jpg", ".png", ".jpeg"}:
            # Extract token identifier from filename
            # Assuming format: tokenname-arttype-lang-set.ext
            stem = file.stem
            local_tokens.add(stem)

    log_message(f"Found {len(local_tokens)} tokens locally")
    return local_tokens


def compare_coverage(scryfall_tokens: List[Dict], local_tokens: Set[str]) -> List[Dict]:
    """Compare Scryfall catalog with local library."""
    missing = []

    for token in scryfall_tokens:
        token_id = token.get("id")
        token_name = token.get("name", "").lower().replace(" ", "-")
        set_code = token.get("set", "")

        # Check if we have this token
        # This is a simplified check - actual implementation would be more sophisticated
        found = False
        for local_id in local_tokens:
            if token_name in local_id.lower() and set_code in local_id.lower():
                found = True
                break

        if not found:
            missing.append(
                {
                    "id": token_id,
                    "name": token.get("name"),
                    "set": set_code,
                    "set_name": token.get("set_name"),
                    "image_uri": token.get("image_uris", {}).get("normal"),
                    "scryfall_uri": token.get("scryfall_uri"),
                }
            )

    log_message(f"Found {len(missing)} missing tokens")
    return missing


def save_missing_tokens(missing: List[Dict]):
    """Save missing tokens to file for later processing."""
    MISSING_TOKENS.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "generated_at": datetime.now().isoformat(),
        "count": len(missing),
        "tokens": missing,
    }

    with open(MISSING_TOKENS, "w") as f:
        json.dump(data, f, indent=2)

    log_message(f"Saved missing tokens to: {MISSING_TOKENS}")


def generate_download_script(missing: List[Dict], output_file: Path):
    """Generate shell script to download missing tokens."""
    script_lines = [
        "#!/bin/bash",
        "# Auto-generated token download script",
        f"# Generated: {datetime.now().isoformat()}",
        f"# Missing tokens: {len(missing)}",
        "",
        "set -e",
        "",
    ]

    for token in missing[:100]:  # Limit to first 100 for safety
        if token.get("image_uri"):
            filename = f"{token['name'].lower().replace(' ', '-')}-{token['set']}.jpg"
            script_lines.append(f"# {token['name']} ({token['set']})")
            script_lines.append(
                f"curl -o 'shared/tokens/{filename}' '{token['image_uri']}'"
            )
            script_lines.append("sleep 0.1  # Rate limiting")
            script_lines.append("")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(script_lines))
    output_file.chmod(0o755)

    log_message(f"Generated download script: {output_file}")


def run_sync(dry_run: bool = True, generate_script: bool = False):
    """Run token coverage sync."""
    log_message("=" * 70)
    log_message("TOKEN COVERAGE AUTO-SYNC")
    log_message("=" * 70)

    if dry_run:
        log_message("Running in DRY RUN mode")

    # Get Scryfall tokens
    scryfall_tokens = get_scryfall_tokens()
    if not scryfall_tokens:
        log_message("No tokens fetched from Scryfall", "ERROR")
        return 1

    # Get local tokens
    local_tokens = get_local_tokens()

    # Compare coverage
    missing = compare_coverage(scryfall_tokens, local_tokens)

    # Calculate coverage percentage
    coverage = (
        ((len(scryfall_tokens) - len(missing)) / len(scryfall_tokens) * 100)
        if scryfall_tokens
        else 0
    )

    log_message(
        f"Coverage: {coverage:.1f}% ({len(scryfall_tokens) - len(missing)}/{len(scryfall_tokens)})"
    )

    if not missing:
        log_message("All tokens present - no action needed")
        return 0

    # Save missing tokens
    if not dry_run:
        save_missing_tokens(missing)
    else:
        log_message(f"[DRY RUN] Would save {len(missing)} missing tokens")

    # Generate download script if requested
    if generate_script:
        script_file = Path("scripts/download_missing_tokens.sh")
        if not dry_run:
            generate_download_script(missing, script_file)
        else:
            log_message(f"[DRY RUN] Would generate script: {script_file}")

    # Summary
    log_message("=" * 70)
    log_message(f"SUMMARY: {len(missing)} tokens missing")
    log_message("=" * 70)

    # Show top 10 missing
    log_message("\nTop 10 missing tokens:")
    for token in missing[:10]:
        log_message(f"  - {token['name']} ({token['set']})")

    if len(missing) > 10:
        log_message(f"  ... and {len(missing) - 10} more")

    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python token_coverage_sync.py <command> [options]")
        print("\nCommands:")
        print("  check                - Check coverage (dry run)")
        print("  check --apply        - Check and save missing tokens")
        print("  check --script       - Check and generate download script")
        print("  check --apply --script - Full sync with script generation")
        print("\nExamples:")
        print("  python token_coverage_sync.py check")
        print("  python token_coverage_sync.py check --apply")
        print("  python token_coverage_sync.py check --apply --script")
        print("\nCron example:")
        print(
            "  0 2 * * * cd /path/to/proxy-machine && python tools/token_coverage_sync.py check --apply"
        )
        return 1

    command = sys.argv[1]

    if command == "check":
        dry_run = "--apply" not in sys.argv
        generate_script = "--script" in sys.argv

        return run_sync(dry_run, generate_script)

    print(f"[ERROR] Unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
