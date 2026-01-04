#!/usr/bin/env python3
"""
Clean Token Fetch System - Built from scratch for simplicity and reliability.

This is a complete rewrite of the token fetching logic to avoid the complexity
that built up in the original system.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import re
from dataclasses import dataclass

import click
import requests

from services.fetch import FetchJob, fetch_service


@dataclass
class TokenCard:
    """Simple token card representation."""

    id: str
    name: str
    type_line: str
    set_code: str
    collector_number: str
    image_url: str
    lang: str
    subtype: str
    subtype_slug: str
    power: Optional[str]
    toughness: Optional[str]


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def extract_token_subtype(type_line: str) -> str:
    """Extract token subtype from type line."""
    if "—" in type_line:
        return type_line.split("—", 1)[1].strip()
    elif " - " in type_line:
        return type_line.split(" - ", 1)[1].strip()
    else:
        # Remove "Token" and clean up
        cleaned = type_line.replace("Token", "").strip()
        return cleaned if cleaned else "Misc"


def query_tokens_from_db(
    db_path: str,
    subtype_filter: Optional[str] = None,
    set_filter: Optional[str] = None,
    lang_filter: str = "en",
    limit: Optional[int] = None,
) -> List[TokenCard]:
    """
    Query tokens directly from database with simple, clear filters.
    No complex expansion logic - just get tokens.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Build base query - only get actual tokens
    query = """
        SELECT id, name, type_line, set_code, collector_number,
               image_url, lang, power, toughness
        FROM prints
        WHERE is_token = 1
        AND image_url IS NOT NULL
        AND image_url != ''
    """

    params: list[str] = []

    # Language filter: support comma-separated list like "en,ph"
    if lang_filter:
        langs = [part.strip() for part in lang_filter.split(",") if part.strip()]
        if langs:
            placeholders = ",".join(["?" for _ in langs])
            query += f" AND lang IN ({placeholders})"
            params.extend(langs)

    # Add additional filters
    if subtype_filter:
        query += " AND type_line LIKE ?"
        params.append(f"%{subtype_filter}%")

    if set_filter:
        query += " AND set_code = ?"
        params.append(set_filter.upper())

    # Add limit
    if limit:
        query += " LIMIT ?"
        params.append(str(limit))

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tokens = []
    for row in rows:
        (
            id_val,
            name,
            type_line,
            set_code,
            collector_number,
            image_url,
            lang,
            power,
            toughness,
        ) = row

        # image_url is already a direct string
        if not image_url:
            continue

        # Extract subtype
        subtype = extract_token_subtype(type_line)
        subtype_slug = slugify(subtype)

        tokens.append(
            TokenCard(
                id=str(id_val),
                name=name,
                type_line=type_line,
                set_code=set_code,
                collector_number=collector_number,
                image_url=image_url,
                lang=lang,
                subtype=subtype,
                subtype_slug=subtype_slug,
                power=power,
                toughness=toughness,
            )
        )

    return tokens


def build_token_presence_index(tokens_dir: Path) -> Dict[str, Set[str]]:
    """Build presence index for tokens.

    Returns: {relative_dir: {file_stems}}
    where relative_dir is relative to tokens_dir, e.g.:
      "creature/soldier/1-1" or "noncreature/treasure".
    """
    presence: Dict[str, Set[str]] = {}

    if not tokens_dir.exists():
        return presence

    for file_path in tokens_dir.rglob("*.png"):
        if not file_path.is_file():
            continue
        rel_dir = file_path.parent.relative_to(tokens_dir).as_posix()
        presence.setdefault(rel_dir, set()).add(file_path.stem)

    return presence


def generate_token_filename(token: TokenCard) -> str:
    """Generate filename for token inside its destination directory.
    We assume directory encodes kind/subtype/power-toughness. Filename focuses on
    uniqueness via set and collector number.
    """
    name_slug = slugify(token.name)
    parts = [name_slug, token.lang]
    if token.set_code:
        parts.append(token.set_code.lower())
    if token.collector_number:
        parts.append(str(token.collector_number))
    return "-".join(parts) + ".png"


def is_creature_token(token: TokenCard) -> bool:
    return "creature" in token.type_line.lower()


def power_toughness_slug(token: TokenCard) -> str:
    if token.power and token.toughness:
        return f"{token.power}-{token.toughness}"
    return "unknown"


def classify_noncreature_kind(token: TokenCard) -> str:
    tl = token.type_line.lower()
    name = token.name.lower()
    if "treasure" in tl or "treasure" in name:
        return "treasure"
    if "food" in tl or "food" in name:
        return "food"
    return "misc"


def token_destination_dir(base_dir: Path, token: TokenCard) -> Path:
    """Compute the destination directory for a token under base_dir."""
    if is_creature_token(token):
        pt_slug = power_toughness_slug(token)
        return base_dir / "creature" / token.subtype_slug / pt_slug
    kind = classify_noncreature_kind(token)
    return base_dir / "noncreature" / kind


def download_token(token: TokenCard, output_dir: Path) -> Tuple[bool, str]:
    """Download a single token image."""
    try:
        token_dir = token_destination_dir(output_dir, token)
        token_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = generate_token_filename(token)
        filepath = token_dir / filename

        # Download image
        response = requests.get(token.image_url, timeout=30)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(response.content)
            return True, f"Downloaded: {token.name}"
        else:
            return False, f"HTTP {response.status_code}: {token.name}"

    except Exception as e:
        return False, f"Error downloading {token.name}: {e}"


def download_tokens_batch(
    tokens: List[TokenCard], output_dir: Path
) -> Tuple[int, int, List[str]]:
    """Download tokens using the shared FetchService for concurrency.

    This function is retained for compatibility with the previous interface,
    but it now delegates to FetchService instead of doing sequential
    requests.get calls.
    """

    # Build FetchJob list
    jobs: List[FetchJob] = []
    for token in tokens:
        dest_dir = token_destination_dir(output_dir, token)
        filename = generate_token_filename(token)
        destination_path = dest_dir / filename

        jobs.append(
            FetchJob(
                card_id=token.id,
                card_name=token.name,
                image_url=token.image_url,
                destination_path=destination_path,
                set_code=token.set_code,
                collector_number=token.collector_number,
            )
        )

    summary = fetch_service.fetch_cards(jobs, dry_run=False, skip_existing=True)

    downloaded = summary.successful
    skipped = summary.skipped
    errors: List[str] = [job.card_name for job in summary.failed_jobs]

    return downloaded, skipped, errors


def fetch_tokens_clean(
    db_path: str,
    output_dir: Path,
    subtype_filter: Optional[str] = None,
    set_filter: Optional[str] = None,
    lang: str = "en",
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Tuple[int, int, List[str]]:
    """
    Clean token fetch function - simple and focused.

    Returns: (downloaded, skipped, errors)
    """
    click.echo("Fetching tokens with filters:")
    click.echo(f"  Subtype: {subtype_filter or 'Any'}")
    click.echo(f"  Set: {set_filter or 'Any'}")
    click.echo(f"  Language: {lang}")
    click.echo(f"  Limit: {limit or 'None'}")
    click.echo(f"  Dry run: {dry_run}")

    # 1. Query tokens from database
    click.echo("Querying tokens from database...")
    tokens = query_tokens_from_db(
        db_path=db_path,
        subtype_filter=subtype_filter,
        set_filter=set_filter,
        lang_filter=lang,
        limit=limit,
    )

    click.echo(f"Found {len(tokens)} tokens")

    if not tokens:
        return 0, 0, ["No tokens found matching criteria"]

    # 2. Build fetch jobs and delegate to FetchService
    click.echo("Building fetch jobs and delegating to FetchService...")

    jobs: List[FetchJob] = []
    for token in tokens:
        dest_dir = token_destination_dir(output_dir, token)
        filename = generate_token_filename(token)
        destination_path = dest_dir / filename

        jobs.append(
            FetchJob(
                card_id=token.id,
                card_name=token.name,
                image_url=token.image_url,
                destination_path=destination_path,
                set_code=token.set_code,
                collector_number=token.collector_number,
            )
        )

    click.echo(f"Prepared {len(jobs)} fetch jobs")

    if dry_run:
        # In dry run, just report how many would be fetched and skipped based on
        # existing files, without doing any network I/O.
        existing = sum(1 for job in jobs if job.destination_path.exists())
        to_download = len(jobs) - existing
        click.echo(
            f"Dry run: would download {to_download} tokens, skip {existing} existing files"
        )
        return 0, existing, []

    click.echo("Starting concurrent token fetch via FetchService...")
    summary = fetch_service.fetch_cards(jobs, dry_run=False, skip_existing=True)

    downloaded = summary.successful
    skipped = summary.skipped
    errors: List[str] = [job.card_name for job in summary.failed_jobs]

    click.echo(
        f"Token fetch complete: downloaded={downloaded}, skipped={skipped}, "
        f"failed={len(errors)}"
    )

    return downloaded, skipped, errors


if __name__ == "__main__":
    # Test the clean token fetch
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bulk_paths import bulk_db_path

    db_path = str(bulk_db_path())

    # Default to magic-the-gathering/shared/tokens relative to repo root
    repo_root = Path(__file__).parent.parent
    output_dir = repo_root / "magic-the-gathering" / "shared" / "tokens"

    downloaded, skipped, errors = fetch_tokens_clean(
        db_path=db_path,
        output_dir=output_dir,
        subtype_filter="Spirit",
        limit=5,
        dry_run=True,
    )

    print(f"Result: Downloaded {downloaded}, Skipped {skipped}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
