from re import compile
from enum import Enum
from typing import Callable, Optional, Tuple

card_data_tuple = Tuple[str, str, str, int]


def parse_deck_helper(
    deck_text: str,
    is_card_line: Callable[[str], bool],
    extract_card_data: Callable[[str], Optional[card_data_tuple]],
    handle_card: Callable[[int, str, int], None],
) -> None:
    error_lines = []

    index = 0
    for line in deck_text.strip().split("\n"):
        if is_card_line(line):
            index = index + 1

            extracted = extract_card_data(line)
            if extracted is None:
                continue
            name, set_code, url, quantity = extracted

            print(
                f"Index: {index}, quantity: {quantity}, name: {name}, set: {set_code}, url: {url}"
            )
            try:
                handle_card(index, name, quantity)
            except Exception as e:
                print(f"Error: {e}")
                error_lines.append((line, e))

        else:
            print(f'Skipping: "{line}"')

    if len(error_lines) > 0:
        print(f"Errors: {error_lines}")


def parse_text(deck_text: str, handle_card: Callable) -> None:
    pattern = compile(
        r"^(\d+)x\s+(.+?)\s+\((.+?)\)\s*(?:[•\s]+)?$"
    )  # '{Quantity}x {Name} ({Set})' possibly followed by influence pips "•"

    def is_text_line(line) -> bool:
        return bool(pattern.match(line))

    def extract_plaintext_card_data(line: str) -> Optional[card_data_tuple]:
        match = pattern.match(line)
        if match:
            quantity = int(match.group(1).strip())
            name = match.group(2).strip()
            set_name = match.group(3).strip()

            return (name, set_name, "", quantity)
        return None

    parse_deck_helper(deck_text, is_text_line, extract_plaintext_card_data, handle_card)


def parse_bbcode(deck_text: str, handle_card: Callable) -> None:
    pattern = compile(
        r"(\d+)x \[url=(https://netrunnerdb.com/en/card/\d+)\](.+)\[/url\] \[i\]\((.+)\)\[/i\].+"
    )  # '{Quantity}x [url={URL}]{Name}[/url] [i]({Set})[/i] '

    def is_bbcode_line(line) -> bool:
        return bool(pattern.match(line))

    def extract_bbcode_card_data(line: str) -> Optional[card_data_tuple]:
        match = pattern.match(line)
        if match:
            name = match.group(3).strip()
            url = match.group(2).strip()
            set_name = match.group(4).strip()
            quantity = int(match.group(1).strip())

            return (name, set_name, url, quantity)
        return None

    parse_deck_helper(deck_text, is_bbcode_line, extract_bbcode_card_data, handle_card)


def parse_markdown(deck_text: str, handle_card: Callable) -> None:
    pattern = compile(
        r"^\* (\d+)x \[(.+)\]\((.+)\) _\((.+)\)_.+$"
    )  # '* {Quantity}x [{Name}]({URL}) _({Set})_ '

    def is_markdown_line(line) -> bool:
        return bool(pattern.match(line))

    def extract_markdown_card_data(line: str) -> Optional[card_data_tuple]:
        match = pattern.match(line)
        if match:
            name = match.group(2).strip()
            url = match.group(3).strip()
            set_name = match.group(4).strip()
            quantity = int(match.group(1).strip())

            return (name, set_name, url, quantity)
        return None

    parse_deck_helper(
        deck_text, is_markdown_line, extract_markdown_card_data, handle_card
    )


def parse_plain_text(deck_text: str, handle_card: Callable) -> None:
    pattern = compile(
        r"^(\d+)x\s+([^(]+?)(?:\s+\(([^)]+)\))?(?:\s+([^\w\s].*))?$"
    )  # '{Quantity}x {Name} ({Set}) {Symbols}' where Set and Symbols are optional

    def is_plaintext_line(line) -> bool:
        return bool(pattern.match(line))

    def extract_plaintext_card_data(line: str) -> Optional[card_data_tuple]:
        match = pattern.match(line)
        if match:
            name = match.group(2).strip()
            quantity = int(match.group(1).strip())
            set_name = match.group(3).strip() if match.group(3) else ""

            return (name, set_name, "", quantity)
        return None

    parse_deck_helper(
        deck_text, is_plaintext_line, extract_plaintext_card_data, handle_card
    )


def parse_jinteki(deck_text: str, handle_card: Callable) -> None:
    pattern = compile(r"^(\d+) (.+)$")  # '{Quantity} {Name}'

    def is_tabletop_simulator_line(line) -> bool:
        return bool(pattern.match(line))

    def extract_tabletop_simulator_card_data(line: str) -> Optional[card_data_tuple]:
        match = pattern.match(line)
        if match:
            name = match.group(2).strip()
            quantity = int(match.group(1).strip())

            return (name, "", "", quantity)
        return None

    parse_deck_helper(
        deck_text,
        is_tabletop_simulator_line,
        extract_tabletop_simulator_card_data,
        handle_card,
    )


class DeckFormat(str, Enum):
    TEXT = "text"
    BBCODE = "bbcode"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    JINTEKI = "jinteki"


def parse_deck(deck_text: str, format: DeckFormat, handle_card: Callable) -> None:
    if format == DeckFormat.TEXT:
        return parse_text(deck_text, handle_card)
    elif format == DeckFormat.BBCODE:
        return parse_bbcode(deck_text, handle_card)
    elif format == DeckFormat.MARKDOWN:
        return parse_markdown(deck_text, handle_card)
    elif format == DeckFormat.PLAIN_TEXT:
        return parse_plain_text(deck_text, handle_card)
    elif format == DeckFormat.JINTEKI:
        return parse_jinteki(deck_text, handle_card)
    else:
        raise ValueError("Unrecognized deck format.")
