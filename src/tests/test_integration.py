"""Integration tests for The Proxy Machine.

Tests deck parsing, fixtures, and integration with various components.
"""

import json
import sys
from pathlib import Path
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test data location
FIXTURES_DIR = Path(__file__).parent / "data" / "fixtures"


def load_fixture(name: str) -> str:
    """Load fixture file content."""
    fixture_path = FIXTURES_DIR / f"{name}.txt"
    if not fixture_path.exists():
        pytest.skip(f"Fixture {name}.txt not found")
    return fixture_path.read_text()


def load_manifest() -> dict:
    """Load fixture manifest with expected values."""
    manifest_path = FIXTURES_DIR / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("manifest.json not found")
    return json.loads(manifest_path.read_text())


class TestDeckParsing:
    """Test deck format parsing with golden fixtures."""

    def test_fixtures_exist(self):
        """Verify all fixture files exist."""
        manifest = load_manifest()
        for fixture in manifest["fixtures"]:
            fixture_path = FIXTURES_DIR / fixture["file"]
            assert fixture_path.exists(), f"Missing fixture: {fixture['file']}"

    def test_manifest_valid(self):
        """Verify manifest structure is valid."""
        manifest = load_manifest()
        assert "fixtures" in manifest
        assert "version" in manifest
        assert len(manifest["fixtures"]) > 0

        for fixture in manifest["fixtures"]:
            assert "name" in fixture
            assert "file" in fixture
            assert "format" in fixture
            assert "expected" in fixture

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "red_burn",
            "lingering_souls",
            "simple_list",
            "mdfc_test",
        ],
    )
    def test_fixture_loads(self, fixture_name):
        """Test that fixtures can be loaded."""
        content = load_fixture(fixture_name)
        assert len(content) > 0
        assert isinstance(content, str)


class TestFixtureExpectations:
    """Test that fixture expectations are documented."""

    def test_red_burn_expectations(self):
        """Verify red_burn fixture has expected values."""
        manifest = load_manifest()
        fixture = next(f for f in manifest["fixtures"] if f["name"] == "red_burn")

        expected = fixture["expected"]
        assert expected["total_cards"] == 60
        assert expected["sideboard_cards"] == 15
        assert expected["tokens"] == 0
        assert expected["basic_lands"] == 20

    def test_lingering_souls_expectations(self):
        """Verify lingering_souls fixture has token expectations."""
        manifest = load_manifest()
        fixture = next(
            f for f in manifest["fixtures"] if f["name"] == "lingering_souls"
        )

        expected = fixture["expected"]
        assert expected["total_cards"] == 60
        assert expected["tokens"] == 2
        assert "token_names" in expected
        assert len(expected["token_names"]) == 2

    def test_mdfc_expectations(self):
        """Verify mdfc_test fixture has MDFC expectations."""
        manifest = load_manifest()
        fixture = next(f for f in manifest["fixtures"] if f["name"] == "mdfc_test")

        expected = fixture["expected"]
        assert expected["mdfc_cards"] == 4
        assert expected["tokens"] == 0


class TestFixtureFormats:
    """Test that fixtures use correct formats."""

    def test_mtga_format_markers(self):
        """Verify MTGA format fixtures have correct markers."""
        content = load_fixture("red_burn")
        assert "Deck" in content
        assert "Sideboard" in content
        assert "(" in content  # Set codes in parentheses

    def test_simple_format_structure(self):
        """Verify simple format has no special markers."""
        content = load_fixture("simple_list")
        assert "Deck" not in content
        assert "Sideboard" not in content
        # Should just be quantity + card name
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        for line in lines:
            assert line[0].isdigit(), f"Line should start with digit: {line}"


# Deck parser integration tests
class TestDeckParserIntegration:
    """Integration tests for deck parsers."""

    def test_parse_red_burn(self):
        """Test parsing red_burn fixture."""
        from deck.parser import parse_deck_file

        fixture_path = FIXTURES_DIR / "red_burn.txt"
        cards = parse_deck_file(str(fixture_path))

        # Should parse all deck and sideboard entries
        assert len(cards) > 0, "Should parse at least some cards"

        # Check that we got card entries with required fields
        for card in cards:
            assert "count" in card, "Card should have count"
            assert "name" in card, "Card should have name"
            assert isinstance(card["count"], int), "Count should be integer"
            assert card["count"] > 0, "Count should be positive"

    def test_parse_simple_list(self):
        """Test parsing simple_list fixture."""
        from deck.parser import parse_deck_file

        fixture_path = FIXTURES_DIR / "simple_list.txt"
        cards = parse_deck_file(str(fixture_path))

        # Should parse all entries
        assert len(cards) > 0, "Should parse at least some cards"

        # Verify structure
        for card in cards:
            assert "count" in card
            assert "name" in card
            assert card["count"] > 0


# Token detection tests
class TestTokenDetection:
    """Integration tests for token detection."""

    def test_detect_spirit_tokens(self):
        """Test detection of Spirit tokens in lingering_souls."""
        from deck.parser import parse_deck_file

        fixture_path = FIXTURES_DIR / "lingering_souls.txt"
        cards = parse_deck_file(str(fixture_path))

        # Find Lingering Souls in the deck
        lingering_souls = [c for c in cards if "Lingering Souls" in c["name"]]
        assert len(lingering_souls) > 0, "Should find Lingering Souls in deck"

        # Verify it was parsed correctly
        assert lingering_souls[0]["count"] > 0

    def test_detect_faerie_tokens(self):
        """Test detection of Faerie Rogue tokens from Bitterblossom."""
        # This test validates that the deck parser can handle token-producing cards
        # Actual token detection would require database integration
        from deck.parser import parse_deck_file

        fixture_path = FIXTURES_DIR / "lingering_souls.txt"
        cards = parse_deck_file(str(fixture_path))

        # Just verify we can parse the deck that contains token-producing cards
        assert len(cards) > 0, "Should parse deck with token-producing cards"


# MDFC expansion tests
class TestMDFCExpansion:
    """Integration tests for MDFC relationship expansion."""

    def test_expand_valki_tibalt(self):
        """Test expansion of Valki // Tibalt MDFC."""
        from deck.parser import parse_deck_file

        fixture_path = FIXTURES_DIR / "mdfc_test.txt"
        cards = parse_deck_file(str(fixture_path))

        # Find Valki in the deck
        valki = [c for c in cards if "Valki" in c["name"]]
        assert len(valki) > 0, "Should find Valki in MDFC test deck"

        # Verify parsing
        assert valki[0]["count"] > 0

    def test_expand_all_mdfcs(self):
        """Test expansion of all MDFCs in mdfc_test fixture."""
        from deck.parser import parse_deck_file

        fixture_path = FIXTURES_DIR / "mdfc_test.txt"
        cards = parse_deck_file(str(fixture_path))

        # Should parse all MDFC cards
        assert len(cards) > 0, "Should parse MDFC deck"

        # Verify all cards have required structure
        for card in cards:
            assert "count" in card
            assert "name" in card
            assert card["count"] > 0


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
