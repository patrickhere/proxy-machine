# Developer Guide

**Last Updated:** 2025-10-16
**Target Audience:** Developers contributing to The Proxy Machine

---

## Table of Contents

1. [Setup](#setup)
2. [Architecture Overview](#architecture-overview)
3. [Development Workflow](#development-workflow)
4. [Testing](#testing)
5. [Plugin Development](#plugin-development)
6. [Database Operations](#database-operations)
7. [CLI Development](#cli-development)
8. [Code Style](#code-style)
9. [Common Tasks](#common-tasks)
10. [Troubleshooting](#troubleshooting)

---

## Setup

### Prerequisites

- Python 3.9+
- Git
- 3GB+ free disk space
- macOS, Linux, or WSL (Windows)

### Initial Setup

```bash
# Clone repository
cd /path/to/the-proxy-printer/proxy-machine

# Create virtual environment
make venv

# Install dependencies
make deps

# Verify installation
make test

# Build database (first time only, takes 5-10 minutes)
make bulk-index-rebuild
```

### Directory Structure

```
proxy-machine/
├── create_pdf.py          # Main CLI (10K+ lines)
├── utilities.py           # PDF generation engine
├── db/                    # Database layer
│   ├── bulk_index.py      # Query interface
│   ├── types.py           # Type definitions
│   └── bulk_index_progress.py
├── net/                   # Network utilities
│   ├── __init__.py
│   └── network.py         # Retry logic, HTTP requests
├── plugins/               # Game-specific plugins
│   ├── mtg/               # Magic: The Gathering
│   ├── lorcana/
│   └── [8 more games]
├── tools/                 # Utility scripts
│   ├── query_relationships.py
│   ├── test_schema.py
│   └── [40+ more tools]
├── tests/                 # Test suite
│   ├── data/fixtures/     # Golden datasets
│   └── test_integration.py
└── mds/                   # Documentation
    ├── GUIDE.md
    ├── WORKFLOW.md
    └── PROJECT_OVERVIEW.md
```

---

## Architecture Overview

### Data Flow

```
Scryfall API → Download → Parse JSON → SQLite Database
                                            ↓
                                    Query Interface
                                            ↓
                                    Card Filtering
                                            ↓
                                    Image Download
                                            ↓
                                    PDF Generation
```

### Core Components

#### 1. Database Layer (`db/`)

**Purpose:** SQLite-backed card database with 508K+ cards

**Key Files:**
- `bulk_index.py` - Query interface, schema management
- `types.py` - Type-safe column constants, TypedDict definitions

**Schema (v6):**
- `prints` table - 508,405 cards, 33 columns
- `card_relationships` table - 130,077 relationships
- `unique_artworks` table - Deduplicated art
- `metadata` table - Schema version, config

**Example Query:**
```python
from db.bulk_index import query_cards_optimized

cards = query_cards_optimized(
    card_type="creature",
    set_filter="znr",
    rarity_filter="rare",
    lang_filter="en",
    limit=100
)
```

#### 2. Network Layer (`net/`)

**Purpose:** Centralized HTTP requests with retry logic

**Key Functions:**
- `fetch_bytes()` - Download binary content
- `fetch_json()` - Download and parse JSON
- `download_file()` - Download to file with atomic writes
- `fetch_with_etag()` - Conditional requests for incremental updates

**Example:**
```python
from net import fetch_bytes, download_file, RetryConfig

# Simple download
content = fetch_bytes("https://example.com/data.json")

# Custom retry config
config = RetryConfig(max_retries=5, base_delay=1.0)
download_file(url, Path("output.png"), config=config)
```

#### 3. Plugin System (`plugins/`)

**Purpose:** Modular game-specific functionality

**Structure:**
```
plugins/{game}/
├── __init__.py          # Metadata
├── fetch.py             # Asset fetching
├── deck_formats.py      # Deck parsers
└── {game}.py           # API client (optional)
```

**Supported Games:**
- MTG (primary)
- Lorcana
- Flesh and Blood
- One Piece
- Yu-Gi-Oh!
- [5 more]

---

## Development Workflow

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes
# ... edit files ...

# Run tests
make test
make test-schema
make test-integration

# Commit with conventional commits
git commit -m "feat: Add new feature"

# Push and create PR
git push origin feature/my-feature
```

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `refactor` - Code refactoring
- `test` - Test additions
- `chore` - Build/tooling

**Example:**
```
feat(database): Add query_cards_optimized function

Pushes all filters to SQL WHERE clause to minimize memory usage.
Reduces memory from 2GB to 100MB (95% reduction).

Closes #42
```

---

## Testing

### Test Types

#### 1. Syntax Check
```bash
make test
```

#### 2. Schema Validation
```bash
make test-schema
```

Tests:
- Database file exists
- All tables present
- Column definitions correct
- Indexes exist
- Data integrity

#### 3. Plugin Regression
```bash
make test-plugins
```

Tests:
- Plugin discovery
- Deck format parsers
- Enable/disable functionality

#### 4. Integration Tests
```bash
make test-integration
```

Tests:
- Fixture validation
- Deck parsing
- Token detection (placeholder)
- MDFC expansion (placeholder)

### Writing Tests

#### Golden Fixtures

Location: `tests/data/fixtures/`

**Add New Fixture:**
1. Create deck file (e.g., `my_deck.txt`)
2. Add entry to `manifest.json` with expected values
3. Document in `fixtures/README.md`
4. Add test case to `test_integration.py`

**Example Manifest Entry:**
```json
{
  "name": "my_deck",
  "file": "my_deck.txt",
  "format": "mtga",
  "description": "Description here",
  "expected": {
    "total_cards": 60,
    "unique_cards": 20,
    "tokens": 2
  }
}
```

#### Integration Test

```python
def test_my_deck_parsing():
    content = load_fixture("my_deck")
    manifest = load_manifest()
    expected = next(f for f in manifest["fixtures"] if f["name"] == "my_deck")

    # TODO: Parse and validate
    # cards = parse_deck(content)
    # assert len(cards) == expected["expected"]["total_cards"]
```

---

## Plugin Development

### Creating a New Plugin

```bash
# 1. Create plugin directory
mkdir -p plugins/mygame

# 2. Create required files
touch plugins/mygame/__init__.py
touch plugins/mygame/fetch.py
touch plugins/mygame/deck_formats.py
```

### Plugin Metadata

**`__init__.py`:**
```python
PLUGIN_METADATA = {
    'name': 'My Game',
    'short_name': 'mygame',
    'version': '1.0.0',
    'author': 'Your Name',
    'description': 'Card fetching for My Game',
    'api_base': 'https://api.mygame.com',
    'requires': ['requests'],
}
```

### Fetch Interface

**`fetch.py`:**
```python
def fetch_card(card_name: str, **kwargs) -> str:
    """Fetch card image and return local path.

    Args:
        card_name: Name of card to fetch
        **kwargs: Additional filters (set, language, etc.)

    Returns:
        Path to downloaded image
    """
    # Implementation here
    pass

def search_cards(query: str, **kwargs) -> list[dict]:
    """Search for cards matching query.

    Args:
        query: Search query
        **kwargs: Additional filters

    Returns:
        List of card dictionaries
    """
    # Implementation here
    pass
```

### Deck Parser

**`deck_formats.py`:**
```python
class MyGameParser:
    """Parser for My Game deck format."""

    @staticmethod
    def can_parse(content: str) -> bool:
        """Return True if this parser can handle the content."""
        return "MyGame" in content

    @staticmethod
    def parse(content: str) -> list[dict]:
        """Parse deck content into card list.

        Returns:
            List of dicts with keys: name, quantity, set (optional)
        """
        cards = []
        for line in content.strip().split('\n'):
            # Parse line
            # Add to cards list
            pass
        return cards
```

### Testing Plugin

```bash
# Add test to tools/test_plugins.py
def test_mygame_parser():
    content = "4 Card Name\n2 Another Card"
    cards = MyGameParser.parse(content)
    assert len(cards) == 2

# Run tests
make test-plugins
```

---

## Database Operations

### Schema Version

Current: **v6**

Location: `db/bulk_index.py:SCHEMA_VERSION`

### Type-Safe Queries

**Always use DBColumns constants:**
```python
from db.card_types import DBColumns

# Good
name = card.get(DBColumns.NAME)
set_code = card.get(DBColumns.SET_CODE)

# Bad (prone to typos)
name = card.get("name")
set_code = card.get("set")  # Wrong! Should be "set_code"
```

### Common Queries

**Query Basic Lands:**
```python
from db.bulk_index import query_basic_lands

lands = query_basic_lands(lang="en", set_code="znr")
```

**Query Tokens:**
```python
from db.bulk_index import query_tokens

tokens = query_tokens(subtype_filter="Spirit", set_filter="znr")
```

**Full-Text Search:**
```python
from db.bulk_index import query_oracle_fts

results = query_oracle_fts("destroy target creature", limit=20)
```

**Optimized Query:**
```python
from db.bulk_index import query_cards_optimized

cards = query_cards_optimized(
    card_type="creature",
    set_filter="znr",
    rarity_filter="rare",
    colors_filter="U",
    limit=100,
    db_path="/path/to/bulk.db"
)
```

### Database Maintenance

```bash
# Rebuild database from scratch
make bulk-index-rebuild

# Optimize database (VACUUM + ANALYZE)
make bulk-optimize

# Check database health
make bulk-check
```

---

## CLI Development

### Adding New Command

**1. Define Command:**
```python
@cli.command()
@click.option('--set', 'set_filter', help='Set code')
@click.option('--limit', type=int, default=10)
@click.pass_context
def my_command(ctx, set_filter, limit):
    """Description of command."""
    profile = ctx.obj['PROFILE']

    # Implementation
    click.echo(f"Running for profile: {profile}")
```

**2. Add to Makefile:**
```makefile
my-command: deps
	@echo "Running my command..."
	$(PYRUN) create_pdf.py --profile $(PROFILE) my-command \
		--set $(SET) \
		--limit $(LIMIT)
```

**3. Update Help:**
```makefile
help:
	@echo "  make my-command SET=znr LIMIT=20  # Description"
```

### CLI Best Practices

- Use `click.echo()` for output (not `print()`)
- Use `click.ClickException()` for errors
- Add `--dry-run` flag for destructive operations
- Use `click.confirm()` for confirmations
- Add progress bars for long operations

---

## Code Style

### Python Style

- Follow PEP 8
- Use type hints for new code
- Add docstrings for public functions
- Max line length: 100 characters
- Use f-strings for formatting

**Example:**
```python
def fetch_card(
    card_name: str,
    set_code: str | None = None,
    lang: str = "en"
) -> dict[str, Any]:
    """Fetch card data from database.

    Args:
        card_name: Name of card to fetch
        set_code: Optional set code filter
        lang: Language code (default: "en")

    Returns:
        Card dictionary with all fields

    Raises:
        ValueError: If card not found
    """
    # Implementation
    pass
```

### No Emojis

**Never use emojis in:**
- Python code
- Markdown documentation
- Console output
- Comments

**Use plain text alternatives:**
- OK, PASS, [PASS] instead of checkmark
- FAIL, ERROR, [FAIL] instead of X
- Analyzing instead of magnifying glass

---

## Common Tasks

### Add New Card Type

**1. Update Query Function:**
```python
# In db/bulk_index.py
def query_my_type(
    set_filter: str | None = None,
    limit: int | None = None,
    db_path: str = DB_PATH,
) -> list[Dict[str, Any]]:
    conn = _get_connection(db_path)
    try:
        cur = conn.cursor()
        clauses = ["type_line LIKE '%MyType%'"]
        # Add more filters
        # ...
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()
```

**2. Add CLI Command:**
```python
@cli.command()
def fetch_my_type():
    """Fetch MyType cards."""
    # Implementation
    pass
```

**3. Add Makefile Target:**
```makefile
fetch-my-type: deps
	$(PYRUN) create_pdf.py fetch-my-type
```

### Add New Relationship Type

**1. Update Schema:**
```python
# In db/types.py
class RelationshipType:
    MY_TYPE = "my_type"
```

**2. Populate Relationships:**
```python
# In tools/resolve_card_relationships.py
def populate_my_type_relationships(db_path: str):
    conn = _get_connection(db_path)
    # Query and insert relationships
    conn.close()
```

**3. Query Relationships:**
```python
# In tools/query_relationships.py
def find_my_type_relationships(db_path: Path = DB_PATH):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM card_relationships
        WHERE relationship_type = 'my_type'
    """)
    # Process results
```

---

## Troubleshooting

### Database Issues

**Problem:** Database not found
```bash
# Solution: Build database
make bulk-index-rebuild
```

**Problem:** Schema version mismatch
```bash
# Solution: Rebuild database
make bulk-index-rebuild
```

**Problem:** Slow queries
```bash
# Solution: Optimize database
make bulk-optimize
```

### Import Errors

**Problem:** Module not found
```bash
# Solution: Install dependencies
make deps
```

**Problem:** Virtual environment not activated
```bash
# Solution: Activate venv
source venv/bin/activate
# or
make venv
```

### Memory Issues

**Problem:** Out of memory during query
```python
# Solution: Use optimized query with filters
cards = query_cards_optimized(
    set_filter="znr",  # Reduce result set
    limit=100          # Limit results
)
```

**Problem:** Out of memory during PDF generation
```bash
# Solution: Process in smaller batches
make pdf PROFILE=patrick
# Move processed files, repeat
```

### Network Issues

**Problem:** Download failures
```python
# Solution: Use retry logic from net module
from net import download_file, RetryConfig

config = RetryConfig(max_retries=5, base_delay=1.0)
download_file(url, dest, config=config)
```

**Problem:** Rate limiting (429 errors)
```python
# Solution: Increase retry delay
config = RetryConfig(
    max_retries=3,
    base_delay=2.0,  # Longer delay
    retry_on_429=True
)
```

---

## Additional Resources

- **PROJECT_OVERVIEW.md** - Complete technical documentation
- **GUIDE.md** - User guide and workflows
- **WORKFLOW.md** - Development workflows
- **AI_PROJECT_DESCRIPTION.md** - High-level project overview
- **CHANGELOG.md** - Change history
- **IDEAS.md** - Future feature ideas

---

## Getting Help

1. Check this guide first
2. Review PROJECT_OVERVIEW.md for architecture details
3. Check existing tests for examples
4. Review similar code in the codebase
5. Ask for help with specific error messages

---

**Last Updated:** 2025-10-16
**Maintained By:** Patrick Hart
**Version:** 1.0
