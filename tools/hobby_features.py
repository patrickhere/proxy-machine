#!/usr/bin/env python3
"""Hobby utilities that use the project-wide DB-first helpers."""

from __future__ import annotations

import os
import random
import sys
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, cast

# Make sure `create_pdf` is importable when the script is run directly.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import create_pdf  # noqa: E402

try:  # pragma: no cover - optional CLI dependency
    import click as _click  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - graceful CLI handling
    _click = None

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    import click  # type: ignore[import-not-found]

click = cast(Any, _click)
CLI_AVAILABLE: bool = _click is not None


def _card_search_db_first(
    *,
    artist_filter: str | None = None,
    card_type_filter: str | None = None,
    rarity_filter: str | None = None,
    set_filter: str | None = None,
    exclude_tokens: bool = True,
    limit: int | None = None,
) -> List[dict]:
    """Return cards using DB-first lookup with JSON fallback."""

    artist_norm = artist_filter.strip() if artist_filter else None
    type_norm = card_type_filter.strip() if card_type_filter else None
    rarity_norm = rarity_filter.strip().lower() if rarity_filter else None
    set_norm = set_filter.strip().lower() if set_filter else None

    def _db_call() -> List[dict]:
        return create_pdf.db_query_cards(
            limit=limit,
            artist_filter=artist_norm,
            type_filter=type_norm,
            rarity_filter=rarity_norm,
            set_filter=set_norm,
            exclude_tokens=exclude_tokens,
        )

    def _json_fallback() -> List[dict]:
        index = create_pdf._load_bulk_index()
        entries = index.get("entries", {})
        results: List[dict] = []
        for entry in entries.values():
            if exclude_tokens and entry.get("is_token"):
                continue
            if (
                artist_norm
                and artist_norm.lower() not in (entry.get("artist") or "").lower()
            ):
                continue
            if (
                type_norm
                and type_norm.lower() not in (entry.get("type_line") or "").lower()
            ):
                continue
            if rarity_norm and (entry.get("rarity") or "").lower() != rarity_norm:
                continue
            if set_norm and (entry.get("set") or "").lower() != set_norm:
                continue
            results.append(entry)
        results.sort(key=lambda e: (str(e.get("name") or ""), str(e.get("set") or "")))
        if limit and limit > 0:
            return results[:limit]
        return results

    return create_pdf._db_first_fetch(
        "hobby features card search",
        _db_call,
        _json_fallback,
        allow_empty=True,
    )


def analyze_deck_theme(deck_cards: List[str]) -> Dict[str, Any]:
    """Summarise colors, types, themes, and artists for a collection of cards."""

    colors = Counter()
    types = Counter()
    themes = Counter()
    artists = Counter()
    sets = Counter()

    for card_name in deck_cards:
        entry = create_pdf._find_card_entry(card_name, None)
        if not entry:
            continue

        card_colors = (
            entry.get("oracle_color_identity") or entry.get("color_identity") or []
        )
        for color in card_colors:
            colors[color] += 1

        type_line = entry.get("type_line") or ""
        if "Creature" in type_line:
            types["Creature"] += 1
            parts = type_line.split("—")
            if len(parts) > 1:
                subtypes = parts[1].strip().split()
                for subtype in subtypes:
                    if subtype not in {"Creature", "Legendary"}:
                        themes[subtype] += 1

        if "Artifact" in type_line:
            types["Artifact"] += 1
        if "Enchantment" in type_line:
            types["Enchantment"] += 1
        if "Instant" in type_line or "Sorcery" in type_line:
            types["Spell"] += 1

        artist = entry.get("artist")
        if artist:
            artists[artist] += 1

        set_code = entry.get("set")
        if set_code:
            sets[set_code] += 1

    total_color_symbols = sum(colors.values())
    color_percentages = {
        color: (count / total_color_symbols * 100) if total_color_symbols else 0
        for color, count in colors.items()
    }

    land_suggestions: List[Dict[str, str]] = []
    if themes:
        tribe, amount = themes.most_common(1)[0]
        if amount >= 5:
            land_suggestions.append(
                {
                    "reason": f"Tribal deck ({tribe})",
                    "suggestion": f"Look for {tribe}-themed lands or lands from sets featuring {tribe}s",
                }
            )
    if sets:
        dominant_set, amount = sets.most_common(1)[0]
        if amount >= 10:
            land_suggestions.append(
                {
                    "reason": f"Heavy {dominant_set.upper()} presence",
                    "suggestion": f"Consider basic lands from {dominant_set.upper()} for thematic consistency",
                }
            )
    if artists:
        dominant_artist, amount = artists.most_common(1)[0]
        if amount >= 8:
            land_suggestions.append(
                {
                    "reason": f"Artwork by {dominant_artist}",
                    "suggestion": f"Search for basic lands illustrated by {dominant_artist}",
                }
            )
    if types.get("Artifact", 0) >= 15:
        land_suggestions.append(
            {
                "reason": "Artifact-heavy deck",
                "suggestion": "Consider artifact-themed lands or lands from Kaladesh/Mirrodin",
            }
        )
    if types.get("Enchantment", 0) >= 12:
        land_suggestions.append(
            {
                "reason": "Enchantment-heavy deck",
                "suggestion": "Consider enchantment-themed lands or the Theros block",
            }
        )

    return {
        "colors": dict(colors),
        "color_percentages": color_percentages,
        "types": dict(types),
        "top_themes": themes.most_common(3),
        "top_artists": artists.most_common(3),
        "top_sets": sets.most_common(3),
        "land_suggestions": land_suggestions,
    }


def find_cards_by_artist(
    artist_name: str,
    card_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return a list of cards illustrated by the requested artist."""

    entries = _card_search_db_first(
        artist_filter=artist_name,
        card_type_filter=card_type,
        limit=None,
        exclude_tokens=False,
    )

    results: List[Dict[str, Any]] = []
    seen: set[tuple] = set()
    for entry in entries:
        key = (
            entry.get("name"),
            entry.get("set"),
            entry.get("collector_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "name": entry.get("name"),
                "type": entry.get("type_line"),
                "set": entry.get("set"),
                "artist": entry.get("artist"),
                "rarity": entry.get("rarity"),
                "image_url": entry.get("image_url")
                or (entry.get("image_uris") or {}).get("png"),
            }
        )
        if limit and len(results) >= limit:
            break
    return results


def discover_random_cards(
    card_type: Optional[str] = None,
    rarity: Optional[str] = None,
    set_code: Optional[str] = None,
    count: int = 5,
) -> List[Dict[str, Any]]:
    """Return a random selection of cards matching the provided filters."""

    if count <= 0:
        return []

    entries = _card_search_db_first(
        card_type_filter=card_type,
        rarity_filter=rarity,
        set_filter=set_code,
        exclude_tokens=True,
        limit=None,
    )

    if not entries:
        return []

    sample_count = min(count, len(entries))
    selection = random.sample(entries, sample_count)

    return [
        {
            "name": entry.get("name"),
            "type": entry.get("type_line"),
            "set": entry.get("set"),
            "artist": entry.get("artist"),
            "rarity": entry.get("rarity"),
            "oracle_text": entry.get("oracle_text"),
            "image_url": entry.get("image_url"),
        }
        for entry in selection
    ]


def explore_set(
    set_code: str,
    card_type: Optional[str] = None,
    rarity: Optional[str] = None,
    sort_by: str = "name",
    limit: int = 50,
) -> Dict[str, Any]:
    """Browse a set's cards using DB-first behaviour with JSON fallback."""

    entries = _card_search_db_first(
        set_filter=set_code,
        card_type_filter=card_type,
        rarity_filter=rarity,
        exclude_tokens=True,
        limit=None,
    )

    if not entries:
        return {"error": f"Set '{set_code}' not found"}

    def _collector_sort_key(value: str | None) -> tuple[int, str]:
        if not value:
            return (0, "")
        raw = value.split("/")[0]
        digits = "".join(ch for ch in raw if ch.isdigit()) or "0"
        suffix = "".join(ch for ch in raw if not ch.isdigit())
        return (int(digits), suffix)

    sort_key_map: Dict[str, Callable[[dict], tuple]] = {
        "name": lambda e: (str(e.get("name") or ""),),
        "rarity": lambda e: (str(e.get("rarity") or ""), str(e.get("name") or "")),
        "cmc": lambda e: (
            float(e.get("mana_value") or e.get("cmc") or 0),
            str(e.get("name") or ""),
        ),
        "collector_number": lambda e: _collector_sort_key(e.get("collector_number")),
    }

    sort_key = sort_key_map.get(sort_by, sort_key_map["name"])
    entries.sort(key=sort_key)

    limited_entries = entries[:limit] if limit and limit > 0 else entries
    cards: List[Dict[str, Any]] = [
        {
            "name": entry.get("name"),
            "type": entry.get("type_line"),
            "collector_number": entry.get("collector_number"),
            "rarity": entry.get("rarity"),
            "artist": entry.get("artist"),
            "cmc": entry.get("mana_value") or entry.get("cmc"),
            "image_url": entry.get("image_url"),
        }
        for entry in limited_entries
    ]

    stats = Counter()
    for entry in entries:
        stats["total_cards"] += 1
        rarity_value = (entry.get("rarity") or "").lower()
        if rarity_value in {"common", "uncommon", "rare", "mythic"}:
            stats[rarity_value + "s"] += 1

    first = entries[0]
    return {
        "set_name": first.get("set_name") or first.get("set"),
        "set_code": (first.get("set") or set_code).upper(),
        "released_at": first.get("released_at"),
        "cards": cards,
        "stats": {
            "total_cards": stats.get("total_cards", 0),
            "commons": stats.get("commons", 0),
            "uncommons": stats.get("uncommons", 0),
            "rares": stats.get("rares", 0),
            "mythics": stats.get("mythics", 0),
        },
        "showing": len(cards),
        "total_available": len(entries),
    }


if __name__ == "__main__":
    if not CLI_AVAILABLE:
        raise SystemExit("The 'click' dependency is required to use this CLI.")

    assert click is not None

    rarity_symbols = {
        "common": "○",
        "uncommon": "◇",
        "rare": "◆",
        "mythic": "★",
    }

    @click.group()
    def cli() -> None:
        """Cool hobby features for The Proxy Machine."""

    @cli.command("artist")
    @click.argument("artist")
    @click.option("--type", "card_type", help="Card type filter")
    @click.option("--limit", default=20, help="Maximum results")
    def cli_artist(artist: str, card_type: Optional[str], limit: int) -> None:
        results = find_cards_by_artist(artist, card_type, limit)
        if not results:
            click.echo(f"No cards found by artist '{artist}'")
            return
        click.echo(f"\n🎨 Cards by {artist}:\n")
        for card in results:
            card_name = str(card.get("name") or "")
            set_code = str(card.get("set") or "").upper()
            card_type_str = str(card.get("type") or "")
            click.echo(f"  • {card_name} ({set_code}) - {card_type_str}")
        click.echo(f"\n✓ Found {len(results)} cards")

    @cli.command("random")
    @click.option("--type", "card_type", help="Card type filter")
    @click.option("--rarity", help="Rarity filter")
    @click.option("--set", "set_code", help="Set code filter")
    @click.option("--count", default=5, help="Number of cards")
    def cli_random(
        card_type: Optional[str],
        rarity: Optional[str],
        set_code: Optional[str],
        count: int,
    ) -> None:
        results = discover_random_cards(card_type, rarity, set_code, count)
        if not results:
            click.echo("No cards found matching criteria")
            return
        click.echo("\n🎲 Random Card Discovery:\n")
        for idx, card in enumerate(results, 1):
            card_name = str(card.get("name") or "")
            set_display = str(card.get("set") or "").upper()
            card_type_str = str(card.get("type") or "")
            click.echo(f"{idx}. {card_name} ({set_display})")
            click.echo(f"   Type: {card_type_str}")
            click.echo(f"   Artist: {card.get('artist') or 'Unknown'}")
            text = card.get("oracle_text")
            if text:
                text_str = str(text)
                snippet = text_str[:100] + ("..." if len(text_str) > 100 else "")
                click.echo(f"   Text: {snippet}")
            click.echo()

    @cli.command("explore")
    @click.argument("set_code")
    @click.option("--type", "card_type", help="Card type filter")
    @click.option("--rarity", help="Rarity filter")
    @click.option(
        "--sort", default="name", help="Sort by (name, rarity, cmc, collector_number)"
    )
    @click.option("--limit", default=50, help="Maximum cards to show")
    def cli_explore(
        set_code: str,
        card_type: Optional[str],
        rarity: Optional[str],
        sort: str,
        limit: int,
    ) -> None:
        result = explore_set(set_code, card_type, rarity, sort, limit)
        if "error" in result:
            click.echo(f"⚠️  {result['error']}")
            return
        set_name = str(result.get("set_name") or "Unknown Set")
        click.echo(f"\n📚 {set_name} ({str(result.get('set_code') or '').upper()})")
        released = result.get("released_at")
        if released:
            click.echo(f"Released: {released}\n")
        stats = cast(Dict[str, Any], result.get("stats", {}))
        click.echo("Set Statistics:")
        click.echo(f"  Total cards: {stats.get('total_cards', 0)}")
        click.echo(f"  Commons: {stats.get('commons', 0)}")
        click.echo(f"  Uncommons: {stats.get('uncommons', 0)}")
        click.echo(f"  Rares: {stats.get('rares', 0)}")
        click.echo(f"  Mythics: {stats.get('mythics', 0)}\n")
        click.echo(
            f"Showing {result.get('showing', 0)} of {result.get('total_available', 0)} cards:\n"
        )
        cards = cast(List[Dict[str, Any]], result.get("cards", []))
        for card in cards:
            name = str(card.get("name") or "")
            collector = str(card.get("collector_number") or "?")
            artist = card.get("artist") or "—"
            rarity_key = str(card.get("rarity") or "").lower()
            symbol = rarity_symbols.get(rarity_key, "•")
            click.echo(f"  {symbol} {name} (#{collector}) - {artist}")

    cli()
