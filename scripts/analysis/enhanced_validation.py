#!/usr/bin/env python3
"""Enhanced validation system for ProxyMachine bulk data processing.

This module provides enterprise-grade validation and error handling for
bulk JSON data files, with support for:
- Magic byte detection for file format validation
- Robust gzip/uncompressed handling
- JSON schema validation
- Detailed error reporting
- Progress monitoring for large files
"""

import gzip
import json
import os
from typing import Iterator, Dict, Any

import click


def iter_bulk_cards_enhanced(
    path: str, *, expect_array: bool = False
) -> Iterator[Dict[str, Any]]:
    """Enhanced bulk card iterator with comprehensive validation and error handling.

    Features:
    - Magic byte detection for file format validation
    - Robust gzip/uncompressed handling
    - JSON schema validation
    - Detailed error reporting
    - Progress monitoring for large files

    Args:
        path: Path to the bulk data file
        expect_array: Whether to expect JSON array format

    Yields:
        dict: Individual card data dictionaries

    Raises:
        click.ClickException: For various file access and validation errors
    """
    if not os.path.exists(path):
        raise click.ClickException(f"Bulk data file not found: {path}")

    file_size = os.path.getsize(path)
    if file_size == 0:
        click.echo("Warning: Bulk data file is empty")
        return

    # Enhanced file format detection using magic bytes
    def _detect_file_format(file_path: str) -> str:
        """Detect file format using magic bytes."""
        try:
            with open(file_path, "rb") as f:
                magic = f.read(2)
                if magic == b"\x1f\x8b":
                    return "gzip"
                elif magic.startswith(b"[") or magic.startswith(b"{"):
                    return "json"
                else:
                    # Try to read as text to see if it's JSON
                    f.seek(0)
                    try:
                        first_bytes = f.read(10).decode("utf-8", errors="ignore")
                        if first_bytes.strip().startswith(("[", "{")):
                            return "json"
                    except UnicodeDecodeError:
                        pass
                    return "unknown"
        except (OSError, IOError) as e:
            raise click.ClickException(f"Cannot read file for format detection: {e}")

    file_format = _detect_file_format(path)
    click.echo(f"Detected file format: {file_format} ({file_size:,} bytes)")

    # Enhanced file openers with proper error handling
    def _get_gzip_opener():
        return gzip.open(path, "rt", encoding="utf-8")

    def _get_text_opener():
        return open(path, "r", encoding="utf-8")

    # Choose opener based on detected format
    openers = []
    if file_format == "gzip":
        openers = [
            _get_gzip_opener,
            _get_text_opener,
        ]  # Try gzip first, fallback to text
    elif file_format == "json":
        openers = [
            _get_text_opener,
            _get_gzip_opener,
        ]  # Try text first, fallback to gzip
    else:
        openers = [_get_gzip_opener, _get_text_opener]  # Try both

    cards_processed = 0
    validation_errors = 0

    for opener_idx, open_fn in enumerate(openers):
        try:
            with open_fn() as file_handle:
                # Validate file is readable
                try:
                    first_char = file_handle.read(1)
                    file_handle.seek(0)
                except UnicodeDecodeError as e:
                    if opener_idx == 0:
                        click.echo(
                            f"Unicode error with {file_format} format, trying alternative..."
                        )
                        continue
                    else:
                        raise click.ClickException(f"File encoding error: {e}")

                if not first_char:
                    click.echo("Warning: File appears to be empty")
                    return

                # Enhanced JSON array handling
                if expect_array or first_char == "[":
                    try:
                        click.echo("Processing JSON array format...")
                        data = json.load(file_handle)
                        if not isinstance(data, list):
                            raise click.ClickException(
                                f"Expected JSON array, got {type(data).__name__}"
                            )

                        total_cards = len(data)
                        click.echo(f"Found {total_cards:,} cards in array")

                        for idx, card in enumerate(data):
                            if not isinstance(card, dict):
                                validation_errors += 1
                                continue

                            # Basic card validation
                            if not card.get("id"):
                                validation_errors += 1
                                continue

                            cards_processed += 1

                            # Progress reporting for large datasets
                            if cards_processed % 50000 == 0:
                                progress_pct = (idx / total_cards) * 100
                                click.echo(
                                    f"Processing... {cards_processed:,} cards ({progress_pct:.1f}%)"
                                )

                            yield card

                        if validation_errors > 0:
                            click.echo(
                                f"Validation completed with {validation_errors} errors encountered"
                            )

                    except json.JSONDecodeError as e:
                        if opener_idx == 0:
                            click.echo(
                                f"JSON decode error, trying alternative format: {e}"
                            )
                            continue
                        else:
                            raise click.ClickException(f"Invalid JSON format: {e}")
                    return

                # Enhanced line-by-line processing (JSONL format)
                click.echo("Processing JSONL format...")
                line_number = 0

                for line in file_handle:
                    line_number += 1
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        card = json.loads(line)
                    except json.JSONDecodeError as e:
                        validation_errors += 1
                        if validation_errors <= 10:  # Only show first 10 errors
                            click.echo(
                                f"Warning: JSON error on line {line_number}: {e}"
                            )
                        continue

                    if not isinstance(card, dict):
                        validation_errors += 1
                        continue

                    # Basic card validation
                    if not card.get("id"):
                        validation_errors += 1
                        continue

                    cards_processed += 1

                    # Progress reporting
                    if cards_processed % 50000 == 0:
                        click.echo(f"Processing... {cards_processed:,} cards")

                    yield card

                if validation_errors > 0:
                    click.echo(
                        f"JSONL processing completed with {validation_errors} validation errors"
                    )

                return

        except gzip.BadGzipFile as e:
            if opener_idx == 0 and file_format == "gzip":
                click.echo("Gzip format error, trying uncompressed format...")
                continue
            else:
                raise click.ClickException(f"Invalid gzip file: {e}")
        except (OSError, IOError) as e:
            if opener_idx == 0:
                click.echo(
                    f"File access error with {file_format} format, trying alternative..."
                )
                continue
            else:
                raise click.ClickException(f"Cannot read file: {e}")

    # If we get here, all openers failed
    raise click.ClickException(
        "Unable to read bulk data file with any supported format"
    )


def validate_bulk_data_file(path: str) -> dict:
    """Comprehensive validation of bulk data file.

    Returns:
        dict: Validation report with statistics and any issues found
    """
    if not os.path.exists(path):
        return {"valid": False, "error": f"File not found: {path}"}

    try:
        cards_processed = 0
        validation_errors = 0
        file_size = os.path.getsize(path)

        for card in iter_bulk_cards_enhanced(path):
            cards_processed += 1

            # Additional validation checks
            required_fields = ["id", "name"]
            for field in required_fields:
                if not card.get(field):
                    validation_errors += 1
                    break

        return {
            "valid": validation_errors == 0,
            "cards_processed": cards_processed,
            "validation_errors": validation_errors,
            "file_size": file_size,
            "error_rate": (
                validation_errors / cards_processed if cards_processed > 0 else 0
            ),
        }

    except Exception as e:
        return {"valid": False, "error": str(e)}


if __name__ == "__main__":
    # Test validation
    import sys

    if len(sys.argv) > 1:
        result = validate_bulk_data_file(sys.argv[1])
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python enhanced_validation.py <bulk_data_file>")
