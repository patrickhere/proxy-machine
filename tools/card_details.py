#!/usr/bin/env python3
"""
Card Details CLI

Look up a card by name (exact or partial), list its printings, and optionally fetch
rulings from Scryfall. Prefers the local bulk index for speed/offline usage.

Examples:
  uv run python tools/card_details.py --name "Lightning Bolt" --json
  uv run python tools/card_details.py --name "Ponder" --set lrw --rulings --out /tmp/ponder.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cli import apply_pm_log_overrides, write_json_outputs

# Ensure parent directory (proxy-machine/) is on sys.path so we can import create_pdf
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

import create_pdf  # noqa: E402

SCRYFALL_API_BASE = "https://api.scryfall.com"
USER_AGENT = "ProxyMachine/1.0 (+https://example.local)"


def _http_get_json(url: str) -> dict:
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req) as resp:  # nosec - trusted domain
                payload = resp.read().decode("utf-8")
                data = json.loads(payload)
                if not isinstance(data, dict):
                    raise ValueError("Unexpected JSON response")
                return data
        except (HTTPError, URLError, ValueError) as exc:  # pragma: no cover (network)
            last_exc = exc
    raise RuntimeError(f"HTTP GET failed for {url}: {last_exc}")


def _normalize(s: Any) -> str:
    return str(s or "").strip()


def _match_score(candidate: str, query: str) -> int:
    """Simple heuristic to find best name match: exact > startswith > contains."""
    c = candidate.lower()
    q = query.lower()
    if c == q:
        return 3
    if c.startswith(q):
        return 2
    if q in c:
        return 1
    return 0


def _find_best_match(
    entries: Dict[str, dict], name_query: str
) -> Tuple[str | None, List[str]]:
    """Return the best-matching canonical name and list of entry ids for that name.

    Uses exact/startswith/contains heuristics across the bulk index entries by name.
    """
    best_id_list: List[str] = []
    best_name: str | None = None
    best_score = 0
    for card_id, entry in entries.items():
        name = _normalize(entry.get("name"))
        if not name:
            continue
        score = _match_score(name, name_query)
        if score > 0 and score >= best_score:
            if score > best_score:
                best_id_list = []
            best_score = score
            best_name = name
            best_id_list.append(card_id)
    return best_name, best_id_list


def _gather_prints(index: dict, name_query: str, set_filter: str | None) -> List[dict]:
    entries = index.get("entries", {})
    # Attempt to use direct name mapping if present
    cards_by_name = index.get("cards_by_name", {})
    name_slug = create_pdf._slugify(name_query)
    id_candidates: List[str] = list(cards_by_name.get(name_slug, []))

    # Fallback: scan all entries to find best match
    if not id_candidates:
        best_name, best_list = _find_best_match(entries, name_query)
        if best_name and best_list:
            id_candidates = best_list

    prints: List[dict] = []
    for card_id in id_candidates:
        entry = entries.get(card_id)
        if not entry:
            continue
        if set_filter and (_normalize(entry.get("set")).lower() != set_filter.lower()):
            continue
        prints.append(entry)
    # Sort by release/set then collector
    prints.sort(
        key=lambda e: (
            str(e.get("released_at") or "9999-99-99"),
            str(e.get("set") or ""),
            str(e.get("collector_number") or ""),
        )
    )
    return prints


def _gather_prints_db(name_query: str, set_filter: str | None) -> List[dict]:
    if not create_pdf._db_index_available():
        return []

    set_norm = set_filter.lower() if set_filter else None
    try:
        cards = create_pdf.db_query_cards(
            name_filter=name_query,
            set_filter=set_norm,
            limit=None,
        )
    except Exception:
        return []

    entries = {str(card.get("id")): card for card in cards if card.get("id")}
    if not entries:
        return []

    _, id_candidates = _find_best_match(entries, name_query)
    if not id_candidates:
        id_candidates = list(entries.keys())

    prints: List[dict] = []
    for card_id in id_candidates:
        entry = entries.get(card_id)
        if not entry:
            continue
        if set_norm and (entry.get("set") or "").lower() != set_norm:
            continue
        prints.append(entry)

    if not prints:
        for entry in entries.values():
            if set_norm and (entry.get("set") or "").lower() != set_norm:
                continue
            prints.append(entry)

    prints.sort(
        key=lambda e: (
            str(e.get("released_at") or "9999-99-99"),
            str(e.get("set") or ""),
            str(e.get("collector_number") or ""),
        )
    )
    return prints


def _fetch_rulings(oracle_id: str) -> List[dict]:
    try:
        url = f"{SCRYFALL_API_BASE}/cards/search?q=oracleid:{oracle_id}"
        found = _http_get_json(url)
        # Find any printing id for the oracle, then fetch rulings via /cards/{id}/rulings
        data = found.get("data") or []
        if not data:
            return []
        first_id = data[0].get("id")
        if not first_id:
            return []
        rulings_json = _http_get_json(f"{SCRYFALL_API_BASE}/cards/{first_id}/rulings")
        rulings = rulings_json.get("data") or []
        out: List[dict] = []
        for r in rulings:
            out.append(
                {
                    "published_at": r.get("published_at"),
                    "source": r.get("source"),
                    "comment": r.get("comment"),
                }
            )
        return out
    except Exception:  # pragma: no cover - network optional
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Card details lookup CLI")
    parser.add_argument("--name", required=True, help="Card name (exact or partial)")
    parser.add_argument(
        "--set", dest="set_code", help="Restrict to set code (e.g., mh3)"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Max prints to include (0 = all)"
    )
    parser.add_argument(
        "--rulings", action="store_true", help="Fetch rulings from Scryfall"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text output"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Reduce non-essential output"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Increase logging detail"
    )
    parser.add_argument(
        "--out", help="Write full JSON payload to this path (implies --json)"
    )
    parser.add_argument(
        "--summary-path", help="Write a concise JSON summary to this path"
    )
    args = parser.parse_args()

    quiet, verbose, json_mode = apply_pm_log_overrides(
        quiet=args.quiet, verbose=args.verbose, json_mode=args.json
    )
    args.quiet = bool(quiet)
    args.verbose = bool(verbose)
    json_mode = bool(json_mode)
    if args.out:
        json_mode = True
    args.json = bool(args.json or json_mode)

    prints = _gather_prints_db(args.name, args.set_code or None)

    if not prints:
        try:
            index = create_pdf._load_bulk_index()
        except Exception as exc:
            payload = {"status": "error", "reason": f"bulk index unavailable: {exc}"}
            write_json_outputs(
                payload=payload,
                summary_payload={"status": "error"},
                out_path=args.out,
                summary_path=args.summary_path,
                emit_stdout=args.json,
            )
            raise SystemExit(2)

        prints = _gather_prints(index, args.name, args.set_code or None)

    if not prints:
        payload = {
            "status": "not_found",
            "name": args.name,
            "set": args.set_code or None,
        }
        write_json_outputs(
            payload=payload,
            summary_payload={"status": payload["status"], "name": args.name},
            out_path=args.out,
            summary_path=args.summary_path,
            emit_stdout=args.json,
        )
        if not args.quiet:
            print(f"No prints found for '{args.name}' (set={args.set_code or 'any'}).")
        raise SystemExit(2)

    # Pick a canonical entry (best match) for the details panel (oracle/type/keywords etc.)
    primary = prints[0]
    oracle_id = primary.get("oracle_id")
    rulings: List[dict] = []
    if args.rulings and oracle_id:
        rulings = _fetch_rulings(str(oracle_id))

    limit = None if args.limit == 0 else max(0, args.limit)
    chosen_prints = prints if (limit is None) else prints[:limit]

    items: List[dict] = []
    for e in chosen_prints:
        items.append(
            {
                "name": e.get("name"),
                "set": (e.get("set") or "").upper(),
                "collector_number": e.get("collector_number"),
                "lang": e.get("lang") or "en",
                "rarity": e.get("rarity"),
                "released_at": e.get("released_at"),
                "type_line": e.get("type_line"),
                "oracle_text": e.get("oracle_text"),
                "image_url": e.get("image_uris", {}).get("png")
                or e.get("image_url")
                or None,
            }
        )

    payload = {
        "status": "ok",
        "query": {
            "name": args.name,
            "set": args.set_code or None,
            "limit": limit,
            "rulings": bool(args.rulings),
        },
        "details": {
            "oracle_id": oracle_id,
            "type_line": primary.get("type_line"),
            "oracle_text": primary.get("oracle_text"),
            "keywords": primary.get("oracle_keywords") or primary.get("keywords") or [],
        },
        "prints_count": len(prints),
        "prints": items,
        "rulings": rulings[:100],
    }

    write_json_outputs(
        payload=payload,
        summary_payload={
            "status": payload["status"],
            "name": args.name,
            "prints_count": payload["prints_count"],
        },
        out_path=args.out,
        summary_path=args.summary_path,
        emit_stdout=args.json,
    )

    if args.json and not args.out:
        print(json.dumps(payload, indent=2))
        return

    if not args.quiet:
        print(f"Card: {primary.get('name')} ({(primary.get('set') or '').upper()})")
        print(f"Type: {primary.get('type_line') or '—'}")
        if primary.get("oracle_text"):
            print("Oracle:")
            print(primary.get("oracle_text"))
        if rulings:
            print(f"Rulings: {len(rulings)} available (showing up to 100)")
        print(f"Prints: {len(prints)} (showing {len(items)})")
        for i, pr in enumerate(items, start=1):
            print(
                f"{i:>2}. {(pr['name'] or '—')} [{pr['set']}] #{pr['collector_number']} "
                f"{pr['rarity'] or ''} {pr['released_at'] or ''}"
            )


if __name__ == "__main__":
    main()
