#!/usr/bin/env python3
"""Automated documentation verification tool.

Verifies that documentation matches actual code implementation:
- Make commands exist in Makefile
- File naming patterns match code
- Cross-references are valid
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check_make_commands(
    makefile_path: Path, mds_dir: Path, docs_dir: Path
) -> List[Tuple[str, str]]:
    """Verify all documented make commands exist in Makefile."""
    errors = []

    # Read Makefile to get actual targets
    with open(makefile_path) as f:
        makefile_content = f.read()

    # Extract make targets (lines starting with target:)
    actual_targets = set(
        re.findall(r"^([a-z][a-z0-9-]*):(?:\s|$)", makefile_content, re.MULTILINE)
    )

    # Check all markdown files in both mds/ and docs/ directories
    all_md_files = []

    # Get all MD files from mds/ (but skip planning/ and archive/ - they contain historical references)
    for md_file in mds_dir.glob("*.md"):
        all_md_files.append(md_file)

    # Include guides/ subdirectory
    guides_dir = mds_dir / "guides"
    if guides_dir.exists():
        all_md_files.extend(guides_dir.rglob("*.md"))

    # Get all MD files from docs/ if it exists
    if docs_dir.exists():
        all_md_files.extend(docs_dir.rglob("*.md"))

    for md_file in all_md_files:
        with open(md_file) as f:
            content = f.read()

        # Split into lines for context checking
        lines = content.split("\n")

        for i, line in enumerate(lines):
            # Find all `make <command>` references in this line
            commands_in_line = re.findall(r"`make ([a-z][a-z0-9-]*)", line)

            # Check context - skip if line mentions removal/deprecation
            context_keywords = [
                "removed",
                "deprecated",
                "no longer",
                "fixed:",
                "deleted",
                "→",
            ]
            is_historical = any(keyword in line.lower() for keyword in context_keywords)

            for cmd in commands_in_line:
                if cmd not in actual_targets and not is_historical:
                    errors.append((md_file.name, f"make {cmd}"))

    return errors


def check_file_naming_patterns(
    create_pdf_path: Path, reference_md: Path
) -> List[Tuple[str, str]]:
    """Verify file naming documentation matches code."""
    errors = []

    # Read the naming functions from create_pdf.py
    with open(create_pdf_path) as f:
        code = f.read()

    # Read REFERENCE.md if it exists
    if not os.path.exists(reference_md):
        # REFERENCE.md is optional, skip these checks
        return errors

    with open(reference_md) as f:
        ref_content = f.read()

    # Check that key naming components are documented
    # Look for the actual naming functions and verify docs mention the components
    if "_land_base_stem" in code:
        if (
            "landname" not in ref_content.lower()
            or "arttype" not in ref_content.lower()
        ):
            errors.append(("REFERENCE.md", "Missing land naming components"))

    if "_token_base_stem" in code:
        if (
            "tokenname" not in ref_content.lower()
            or "subtype" not in ref_content.lower()
        ):
            errors.append(("REFERENCE.md", "Missing token naming components"))

    if "_card_base_stem" in code:
        if "cardname" not in ref_content.lower():
            errors.append(("REFERENCE.md", "Missing card naming components"))

    # Verify examples exist
    if (
        "forest-fullart-en" not in ref_content
        and "island-standard-en" not in ref_content
    ):
        errors.append(("REFERENCE.md", "Missing land naming examples"))

    if (
        "insect-standard-en" not in ref_content
        and "spirit-fullart-en" not in ref_content
    ):
        errors.append(("REFERENCE.md", "Missing token naming examples"))

    return errors


def check_documentation_organization(project_root: Path) -> List[Tuple[str, str]]:
    """Verify documentation is properly organized per global rules."""
    errors = []

    # Expected structure
    mds_dir = project_root / "mds"
    docs_dir = project_root / "docs"

    # Check mds/ primary docs exist
    required_mds = ["CHANGELOG.md", "IDEAS.md", "PROJECT_OVERVIEW.md", "README.md"]
    for doc in required_mds:
        if not (mds_dir / doc).exists():
            errors.append(("mds/", f"Missing required file: {doc}"))

    # Check mds/ subdirectories exist
    required_subdirs = ["planning", "guides", "archive"]
    for subdir in required_subdirs:
        if not (mds_dir / subdir).exists():
            errors.append(("mds/", f"Missing required subdirectory: {subdir}"))

    # Check docs/ generated docs (optional but should exist if present)
    if docs_dir.exists():
        expected_docs = ["ROLLBACK.md", "cli.md", "schema.md"]
        for doc in expected_docs:
            doc_path = docs_dir / doc
            if doc_path.exists():
                # Verify it's actually a generated/technical doc
                with open(doc_path) as f:
                    content = f.read()
                    if doc == "cli.md" and "Auto-generated" not in content:
                        errors.append((f"docs/{doc}", "Should be auto-generated"))

    return errors


def check_cross_references(
    mds_dir: Path, docs_dir: Path, project_root: Path
) -> List[Tuple[str, str]]:
    """Verify all cross-references to other docs are valid."""
    errors = []

    # Get all markdown files in mds/ and subdirectories
    md_files = {}
    for md_file in mds_dir.rglob("*.md"):
        md_files[md_file.stem] = md_file

    # Also check docs/ directory
    if docs_dir.exists():
        for md_file in docs_dir.rglob("*.md"):
            md_files[md_file.stem] = md_file

    # Also check root directory for MD files (like AI_PROJECT_DESCRIPTION.md)
    for md_file in project_root.glob("*.md"):
        md_files[md_file.stem] = md_file

    # Historical references that are OK (renamed files mentioned in history)
    historical_refs = {"CHATLOG.md", "old-chat.md", "REFERENCE.md"}

    # Check references in both mds/ and docs/
    all_md_files = list(mds_dir.rglob("*.md"))
    if docs_dir.exists():
        all_md_files.extend(docs_dir.rglob("*.md"))

    for md_file in all_md_files:
        with open(md_file) as f:
            content = f.read()

        # Find references to other .md files
        references = re.findall(r"`([A-Z_]+\.md)`", content)
        references += re.findall(r"See `([A-Z_]+\.md)`", content)
        references += re.findall(r"\[.*?\]\(([A-Z_]+\.md)\)", content)

        for ref in set(references):
            # Skip historical references
            if ref in historical_refs:
                continue

            ref_stem = ref.replace(".md", "")
            if ref_stem not in md_files:
                errors.append((md_file.name, f"Invalid reference: {ref}"))

    return errors


def check_art_type_documentation(
    create_pdf_path: Path, workflow_md: Path
) -> List[Tuple[str, str]]:
    """Verify art type documentation matches _derive_art_type() function."""
    errors = []

    # Skip if WORKFLOW.md doesn't exist (optional)
    if not workflow_md.exists():
        return errors

    # Read the function from code
    with open(create_pdf_path) as f:
        code = f.read()

    # Extract art types from the function
    art_types_in_code = set()

    # Primary types
    if 'primary_type = "textless"' in code:
        art_types_in_code.add("textless")
    if 'primary_type = "borderless"' in code:
        art_types_in_code.add("borderless")
    if 'primary_type = "showcase"' in code:
        art_types_in_code.add("showcase")
    if 'primary_type = "extended"' in code:
        art_types_in_code.add("extended")
    if 'primary_type = "retro"' in code:
        art_types_in_code.add("retro")
    if 'primary_type = "fullart"' in code:
        art_types_in_code.add("fullart")
    if 'primary_type = "standard"' in code:
        art_types_in_code.add("standard")

    # Read WORKFLOW.md
    with open(workflow_md) as f:
        workflow_content = f.read()

    # Check if all art types are documented
    for art_type in art_types_in_code:
        if art_type not in workflow_content.lower():
            errors.append(("WORKFLOW.md", f"Art type not documented: {art_type}"))

    return errors


def main():
    """Run all documentation verification checks."""
    # Determine paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    mds_dir = project_root / "mds"
    docs_dir = project_root / "docs"
    makefile_path = project_root / "Makefile"
    create_pdf_path = project_root / "create_pdf.py"
    reference_md = mds_dir / "REFERENCE.md"
    workflow_md = mds_dir / "WORKFLOW.md"

    print(" Verifying documentation consistency...\n")

    all_errors = []

    # Check documentation organization first
    print("Checking documentation organization...")
    org_errors = check_documentation_organization(project_root)
    all_errors.extend(org_errors)
    if org_errors:
        print(f"{RED}✗ Found {len(org_errors)} organization issues{RESET}")
    else:
        print(f"{GREEN}✓ Documentation properly organized{RESET}")

    # Run checks
    print("\nChecking make commands...")
    make_errors = check_make_commands(makefile_path, mds_dir, docs_dir)
    all_errors.extend(make_errors)
    if make_errors:
        print(f"{RED}✗ Found {len(make_errors)} make command issues{RESET}")
    else:
        print(f"{GREEN}✓ All make commands valid{RESET}")

    print("\nChecking file naming patterns...")
    naming_errors = check_file_naming_patterns(create_pdf_path, reference_md)
    all_errors.extend(naming_errors)
    if naming_errors:
        print(f"{RED}✗ Found {len(naming_errors)} naming pattern issues{RESET}")
    else:
        print(f"{GREEN}✓ File naming patterns match code{RESET}")

    print("\nChecking cross-references...")
    ref_errors = check_cross_references(mds_dir, docs_dir, project_root)
    all_errors.extend(ref_errors)
    if ref_errors:
        print(f"{RED}✗ Found {len(ref_errors)} cross-reference issues{RESET}")
    else:
        print(f"{GREEN}✓ All cross-references valid{RESET}")

    print("\nChecking art type documentation...")
    art_errors = check_art_type_documentation(create_pdf_path, workflow_md)
    all_errors.extend(art_errors)
    if art_errors:
        print(f"{RED}✗ Found {len(art_errors)} art type documentation issues{RESET}")
    else:
        print(f"{GREEN}✓ Art type documentation matches code{RESET}")

    # Print detailed errors
    if all_errors:
        print(f"\n{YELLOW}Detailed Issues:{RESET}")
        for file, issue in all_errors:
            print(f"  {file}: {issue}")
        print(
            f"\n{RED}✗ Documentation verification failed with {len(all_errors)} issues{RESET}"
        )
        return 1
    else:
        print(f"\n{GREEN}✓ All documentation checks passed!{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
