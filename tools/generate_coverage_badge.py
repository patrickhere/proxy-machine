#!/usr/bin/env python3
"""Generate coverage badge for README.

Reads coverage data and generates a badge SVG or markdown.
"""

import json
from pathlib import Path


def get_coverage_percentage() -> float:
    """Extract coverage percentage from coverage.json if it exists."""
    coverage_file = Path(".coverage.json")

    if not coverage_file.exists():
        return 0.0

    try:
        with open(coverage_file) as f:
            data = json.load(f)

        # Extract coverage percentage
        totals = data.get("totals", {})
        percent = totals.get("percent_covered", 0.0)
        return percent
    except Exception:
        return 0.0


def get_badge_color(percentage: float) -> str:
    """Get badge color based on coverage percentage."""
    if percentage >= 90:
        return "brightgreen"
    elif percentage >= 80:
        return "green"
    elif percentage >= 70:
        return "yellowgreen"
    elif percentage >= 60:
        return "yellow"
    elif percentage >= 50:
        return "orange"
    else:
        return "red"


def generate_badge_markdown(percentage: float) -> str:
    """Generate shields.io badge markdown."""
    color = get_badge_color(percentage)
    badge_url = f"https://img.shields.io/badge/coverage-{percentage:.0f}%25-{color}"
    return f"![Coverage]({badge_url})"


def main():
    """Generate coverage badge."""
    percentage = get_coverage_percentage()
    badge = generate_badge_markdown(percentage)

    print(f"Coverage: {percentage:.1f}%")
    print(f"Badge: {badge}")

    # Optionally write to file
    badge_file = Path("docs/coverage-badge.md")
    badge_file.parent.mkdir(parents=True, exist_ok=True)
    badge_file.write_text(badge + "\n")
    print(f"Badge written to: {badge_file}")


if __name__ == "__main__":
    main()
