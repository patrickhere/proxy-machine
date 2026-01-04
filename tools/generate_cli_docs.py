#!/usr/bin/env python3
"""Generate CLI documentation from Click commands.

Extracts help text from create_pdf.py and generates markdown documentation.
"""

import subprocess
import sys
from pathlib import Path


def generate_cli_docs() -> str:
    """Generate CLI documentation markdown."""
    docs = []
    docs.append("# CLI Reference\n")
    docs.append("Auto-generated documentation for The Proxy Machine CLI.\n")
    docs.append("---\n")

    # Get main help
    result = subprocess.run(
        [sys.executable, "create_pdf.py", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    if result.returncode == 0:
        docs.append("## Main Menu\n")
        docs.append("```")
        docs.append(result.stdout)
        docs.append("```\n")

    # Try to get subcommand help (if any)
    # For now, just document the interactive menu
    docs.append("## Interactive Menu\n")
    docs.append(
        "Run `make menu` or `python create_pdf.py` to launch the interactive menu.\n"
    )
    docs.append("\n### Menu Options\n")
    docs.append("1. **Deck Tools** - Manage deck reports and PDF generation\n")
    docs.append("2. **Token Utilities** - Search, build packs, explorers\n")
    docs.append("3. **Card Search & Fetch** - Universal card search with filtering\n")
    docs.append("4. **Profiles & Shared** - Manage profiles and shared assets\n")
    docs.append("5. **Maintenance & Tools** - Health checks, coverage, notifications\n")
    docs.append(
        "6. **Hobby Features** - Discovery tools, artist search, set exploration\n"
    )
    docs.append("7. **Plugins** - Manage plugins (enable/disable)\n")
    docs.append("0. **Exit**\n")

    return "\n".join(docs)


def main():
    """Generate CLI documentation."""
    docs = generate_cli_docs()

    # Write to file
    output_file = Path("docs/cli.md")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(docs)

    print(f"CLI documentation written to: {output_file}")
    print(f"Lines: {len(docs.split(chr(10)))}")


if __name__ == "__main__":
    main()
