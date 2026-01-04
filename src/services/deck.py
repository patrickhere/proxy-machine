"""Deck Processing Service

Business logic for deck parsing, validation, and processing.
Separated from CLI interface for better testability and reusability.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DeckFormat(Enum):
    """Supported deck formats."""

    MOXFIELD = "moxfield"
    ARCHIDEKT = "archidekt"
    MTGA = "mtga"
    MTGO = "mtgo"
    DECKSTATS = "deckstats"
    SCRYFALL = "scryfall"
    SIMPLE = "simple"
    AUTO = "auto"


@dataclass
class Card:
    """Represents a card in a deck."""

    name: str
    quantity: int
    set_code: Optional[str] = None
    collector_number: Optional[str] = None
    is_commander: bool = False
    is_sideboard: bool = False

    def __post_init__(self):
        """Normalize card data after initialization."""
        self.name = self.name.strip()
        if self.set_code:
            self.set_code = self.set_code.lower().strip()


@dataclass
class Deck:
    """Represents a complete deck with metadata."""

    name: str
    cards: List[Card]
    format: Optional[str] = None
    commander: Optional[Card] = None
    sideboard: Optional[List[Card]] = None

    def __post_init__(self):
        """Initialize sideboard if not provided."""
        if self.sideboard is None:
            self.sideboard = []

    @property
    def mainboard_count(self) -> int:
        """Total cards in mainboard."""
        return sum(card.quantity for card in self.cards if not card.is_sideboard)

    @property
    def sideboard_count(self) -> int:
        """Total cards in sideboard."""
        return sum(card.quantity for card in (self.sideboard or []))

    @property
    def total_count(self) -> int:
        """Total cards in deck."""
        return self.mainboard_count + self.sideboard_count


class DeckService:
    """Service for deck processing operations."""

    def __init__(self):
        self.supported_formats = list(DeckFormat)

    def parse_deck_file(
        self, file_path: Path, format_hint: Optional[DeckFormat] = None
    ) -> Deck:
        """Parse a deck file into a Deck object."""
        if not file_path.exists():
            raise FileNotFoundError(f"Deck file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return self.parse_deck_text(content, format_hint, deck_name=file_path.stem)

    def parse_deck_text(
        self,
        content: str,
        format_hint: Optional[DeckFormat] = None,
        deck_name: str = "Untitled",
    ) -> Deck:
        """Parse deck text content into a Deck object."""
        if format_hint is None:
            format_hint = self.detect_format(content)

        logger.info(f"Parsing deck '{deck_name}' as {format_hint.value}")

        # Import parser from registry
        try:
            from plugins.registry import get_parser

            parser = get_parser(format_hint.value)

            if parser is None:
                raise ValueError(f"No parser available for format: {format_hint.value}")

            # Parse using plugin system
            cards = []

            def handle_card(
                name: str, set_code: str, collector_number: str, quantity: int
            ):
                """Card handler for parser callback."""
                card = Card(
                    name=name,
                    quantity=quantity,
                    set_code=set_code if set_code else None,
                    collector_number=collector_number if collector_number else None,
                )
                cards.append(card)

            # Call the parser
            parser(content, handle_card)

            return Deck(name=deck_name, cards=cards, format=format_hint.value)

        except ImportError:
            logger.warning("Plugin registry not available, using fallback parsing")
            return self._fallback_parse(content, deck_name)

    def detect_format(self, content: str) -> DeckFormat:
        """Auto-detect deck format from content."""
        content_lower = content.lower()

        # Check for format-specific patterns
        if "moxfield.com" in content_lower or "(mox)" in content_lower:
            return DeckFormat.MOXFIELD
        elif "archidekt.com" in content_lower or "archidekt" in content_lower:
            return DeckFormat.ARCHIDEKT
        elif "deck" in content_lower and "main" in content_lower:
            return DeckFormat.MTGA
        elif any(
            line.strip().startswith(str(i))
            for i in range(1, 5)
            for line in content.split("\n")
        ):
            return DeckFormat.MTGO
        elif "[" in content and "]" in content:
            return DeckFormat.DECKSTATS
        elif content.strip().startswith("{"):
            return DeckFormat.SCRYFALL
        else:
            return DeckFormat.SIMPLE

    def validate_deck(self, deck: Deck) -> List[str]:
        """Validate deck and return list of issues."""
        issues = []

        if not deck.cards:
            issues.append("Deck contains no cards")

        if deck.mainboard_count == 0:
            issues.append("Mainboard is empty")

        # Check for reasonable deck size
        if deck.mainboard_count < 40:
            issues.append(f"Deck size ({deck.mainboard_count}) is unusually small")
        elif deck.mainboard_count > 250:
            issues.append(f"Deck size ({deck.mainboard_count}) is unusually large")

        # Check for duplicate cards (by name)
        card_names = {}
        for card in deck.cards:
            if card.name in card_names:
                card_names[card.name] += card.quantity
            else:
                card_names[card.name] = card.quantity

        # Check for excessive quantities
        for name, total_quantity in card_names.items():
            if total_quantity > 4 and not self._is_basic_land(name):
                issues.append(f"'{name}' has {total_quantity} copies (more than 4)")

        return issues

    def get_missing_cards(self, deck: Deck, collection_paths: List[Path]) -> List[Card]:
        """Find cards in deck that are missing from collection."""
        missing = []

        # Build collection index
        collection_cards = set()
        for path in collection_paths:
            if path.exists():
                for file in path.rglob("*.png"):
                    # Extract card name from filename
                    card_name = self._extract_card_name_from_filename(file.name)
                    if card_name:
                        collection_cards.add(card_name.lower())

        # Check each deck card
        for card in deck.cards:
            if card.name.lower() not in collection_cards:
                missing.append(card)

        return missing

    def generate_deck_report(
        self, deck: Deck, output_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive deck analysis report."""
        report = {
            "name": deck.name,
            "format": deck.format,
            "statistics": {
                "mainboard_count": deck.mainboard_count,
                "sideboard_count": deck.sideboard_count,
                "total_count": deck.total_count,
                "unique_cards": len(deck.cards),
            },
            "validation": {
                "issues": self.validate_deck(deck),
                "is_valid": len(self.validate_deck(deck)) == 0,
            },
            "breakdown": self._analyze_deck_composition(deck),
        }

        if output_path:
            import json

            with open(output_path, "w") as f:
                json.dump(report, f, indent=2)
            logger.info(f"Deck report saved to {output_path}")

        return report

    def _fallback_parse(self, content: str, deck_name: str) -> Deck:
        """Fallback parser for simple deck lists."""
        cards = []

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            # Try to parse "quantity name" format
            parts = line.split(None, 1)
            if len(parts) >= 2 and parts[0].isdigit():
                quantity = int(parts[0])
                name = parts[1]
                cards.append(Card(name=name, quantity=quantity))

        return Deck(name=deck_name, cards=cards, format="simple")

    def _is_basic_land(self, card_name: str) -> bool:
        """Check if card is a basic land (no 4-card limit)."""
        basic_lands = {"plains", "island", "swamp", "mountain", "forest", "wastes"}
        return card_name.lower() in basic_lands

    def _extract_card_name_from_filename(self, filename: str) -> Optional[str]:
        """Extract card name from image filename."""
        # Remove extension
        name = filename.rsplit(".", 1)[0]

        # Remove common suffixes (art type, language, set)
        suffixes = [
            "-standard",
            "-showcase",
            "-borderless",
            "-extended",
            "-full",
            "-retro",
        ]
        for suffix in suffixes:
            if suffix in name:
                name = name.split(suffix)[0]

        # Remove language codes
        lang_codes = ["-en", "-ja", "-de", "-fr", "-it", "-es", "-pt", "-ru", "-ko"]
        for lang in lang_codes:
            if name.endswith(lang):
                name = name[: -len(lang)]

        return name.strip() if name.strip() else None

    def _analyze_deck_composition(self, deck: Deck) -> Dict[str, Any]:
        """Analyze deck composition by card types, colors, etc."""
        # This would integrate with card database for detailed analysis
        # For now, return basic structure
        return {
            "card_types": {},
            "mana_curve": {},
            "colors": {},
            "rarity_distribution": {},
        }


# Global service instance
deck_service = DeckService()
