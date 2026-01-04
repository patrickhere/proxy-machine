# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Quick Start

**First time in this codebase?**
1. Run `make deps` to install dependencies via UV package manager
2. Run `make bulk-sync` to download Scryfall data and build database (5-10 min, ~3GB)
3. Run `make menu` to launch the interactive menu (primary interface)
4. Read `mds/guides/WORKFLOW.md` for engineering conventions
5. Use `make` commands, not direct Python - Makefile is the primary interface

**Most common workflow:** Add card images to a profile's `to-print/front/` folder → run `make pdf PROFILE=name` → get a print-ready PDF.

---

## Project Overview

**The Proxy Machine** is a CLI-first Python application for managing Magic: The Gathering proxy card generation, deck parsing, and asset fetching. It supports 500K+ cards via a SQLite database built from Scryfall bulk data, with type-based land/token organization and multi-language support.

**Key Technologies:**
- Python 3.9+ with Click CLI framework
- SQLite database (764MB, schema v6) with FTS5 full-text search
- UV package manager for dependencies (not pip/poetry)
- ThreadPoolExecutor for concurrent image downloads (8 workers, thread-safe SQLite connections)
- ReportLab for PDF generation
- Makefile-driven workflow (100+ targets)

**Architectural Note:** Main CLI is monolithic (`create_pdf.py`, 10,500+ lines) by design - keeps all card/token/PDF logic together with shared state. Utilities extracted to modules (`pdf/`, `deck/`, `db/`) but core domain logic stays centralized.

---

## Development Commands

### Environment Setup
```bash
make deps                    # Install dependencies via uv
make venv                    # Create virtual environment
make setup                   # First-time setup
```

### Running the Application
```bash
make menu                    # Interactive menu (primary interface)
make pdf PROFILE=patrick     # Generate PDF from profile's to-print folder
uv run python create_pdf.py --help  # Direct CLI access
```

### Testing
```bash
make test                    # Syntax check
make test-schema             # Database schema validation (9 tests)
make test-integration        # Integration tests (17 tests)
make test-plugins            # Plugin system tests
uv run pytest tests/         # Run pytest directly
```

### Database Operations
```bash
make bulk-sync               # Download bulk data + rebuild database (5-10 min)
make bulk-index-rebuild      # Rebuild database from existing bulk files
make bulk-vacuum             # Optimize database (VACUUM + ANALYZE)
make db-info                 # Show database statistics
```

**Critical Philosophy:** Database is **ephemeral** - it rebuilds from Scryfall bulk data (the source of truth). Schema changes = just rebuild, **no migrations needed**. Never treat the database as authoritative storage - Scryfall JSON is the canonical source.

Thread safety: Each thread gets its own SQLite connection via `_get_connection()`. WAL mode enabled for concurrent reads during downloads.

---

## Code Architecture

### Main Entry Point
- `create_pdf.py` - Main CLI (10,500+ lines), contains menu system, PDF generation, card fetching, token tools
  - Helper utilities grouped at top: `_prompt_text()`, `_prompt_yes_no()`, `_run_subprocess()`
  - Uses shared constants from `constants.py` (RARITIES, SPELL_TYPES, CARD_TYPES)

### Database Layer (`db/`)
- `db/bulk_index.py` - SQLite query interface, schema management (schema v6)
  - `query_cards_optimized()` - Universal card search with 15+ filters, optimized for memory
  - `query_basic_lands()` / `query_non_basic_lands()` - Land queries with comprehensive filtering
  - `query_tokens()` - Token search with metadata filtering
  - Schema: `prints` (508K cards), `card_relationships` (130K), `unique_artworks`, `created_tokens`
- `db/types.py` - Type-safe column constants, TypedDict definitions

### Modular Utilities
- `pdf/utils.py` - Pure PDF utility functions (7 functions)
- `deck/parser.py` - Deck parsing functions (5 parsers)
- `utilities.py` - PDF generation engine with ReportLab
- `constants.py` - Shared constants for validation and user prompts
- `errors.py` - Exception hierarchy (8 custom classes)

### Plugin System (`plugins/`)
Plugin discovery: subdirectories with `__init__.py` exporting `PLUGIN` metadata dict. Supports 10+ games including MTG (primary), Lorcana, Flesh and Blood, One Piece, Yu-Gi-Oh!

State persisted in `proxy-machine/config/plugins.json`. Manage via Menu → Plugins or CLI (`--plugins_list`, `--plugins_enable`, `--plugins_disable`).

---

## File Organization

### Shared Asset Library
```
magic-the-gathering/shared/
├── tokens/<tokentype>/               # Type-based flat structure
│   └── soldier/soldier-standard-en-ltr-015.png
├── basic-lands/<landtype>/           # Type-based multi-level
│   └── mono/plains/plains-standard-en-ltr-260.png
├── non-basic-lands/<landtype>/
│   └── utility/legendary/yavimaya_hollow-fullart-en-usg-330.png
└── card-backs/                       # Card back images
```

### Profile Workspace
```
magic-the-gathering/proxied-decks/<profile>/
├── pictures-of-cards/
│   ├── to-print/
│   │   ├── front/                    # Must be multiple of 8
│   │   ├── back/                     # Auto-filled if empty
│   │   └── double_sided/
│   ├── shared-cards/                 # SYMLINKS to shared/ (not copies!)
│   │   ├── tokens -> ../../shared/tokens
│   │   ├── card-backs -> ../../shared/card-backs
│   │   ├── basic-lands -> ../../shared/basic-lands
│   │   └── non-basic-lands -> ../../shared/non-basic-lands
│   └── archived/
├── pdfs-of-decks/
└── deck-reports/
```

**Why symlinks?** Shared library (15K+ images) is centralized. Profiles link to it rather than duplicating assets. Menu's "Initialize Profiles" creates/repairs these symlinks.

### Naming Convention
- **Tokens:** `<tokenname>-<arttype>-<lang>-<set>-<collector>.png`
- **Lands:** `<landname>-<arttype>-<lang>-<set>-<collector>.png`

Art types (priority order): `textless`, `borderless`, `showcase`, `extended`, `retro`, `fullart`, `standard`
Modifiers: `-oilslick`, `-etched`, `-glossy`, `-gilded`, `-serialized`, `-ub`

See `create_pdf.py:6058-6147` (`_derive_art_type()`) for complete taxonomy.

---

## Critical Workflows

### Adding CLI Command
1. Define Click command in `create_pdf.py` with `@cli.command()` (add near related commands ~line 9000+)
2. Add Makefile target with proper variable defaults (define optional vars at top, target in logical section)
3. Update `mds/guides/REFERENCE.md` (command docs)
4. Update `mds/guides/GUIDE.md` (if user-facing)
5. Update `mds/guides/WORKFLOW.md` (if architectural change)
6. Update `CHANGELOG.md` with session notes

**Never skip step 2** - users expect `make <command>` to work, not direct Python invocation.

### Database Query Pattern
Always use optimized queries with filters pushed to SQL:
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

Use type-safe column access:
```python
from db.types import DBColumns

name = card.get(DBColumns.NAME)  # Good
name = card.get("name")          # Avoid - prone to typos
```

### PDF Generation Safeguards
- Fronts must be multiple of 8 (auto-pad with tokens if needed)
- Backs auto-filled with shared card back if empty
- Unique timestamp suffix prevents overwrites
- Default settings: `--card_size standard`, `--crop 3mm`, `--ppi 600`, `--quality 100`

---

## Engineering Conventions

### Python Style
- Type hints throughout (use `pyright` for static analysis)
- Follow PEP 8, max line length 100 chars
- Prefer readability over premature optimization
- Keep imports at top (never mid-file)
- Use helper utilities: `_prompt_text()`, `_prompt_yes_no()`, `_run_subprocess()`

### Console Output
- Long tasks: single-line in-place progress updates (every ~100 items), final summary only
- **No per-file spam** - bulk operations that print every file create unusable logs
- Use `click.echo()` for output (not `print()`)
- **NO EMOJIS** in code, docs, or console output - use plain text (OK, PASS, FAIL)
- Progress bars: Use `MagicProgressBar` from `tools/mtg_progress.py` for MTG-themed output

### Path Resolution
All paths resolved relative to project root at runtime:
```python
script_directory = os.path.dirname(os.path.abspath(__file__))
project_root_directory = os.path.dirname(script_directory)
```
Never use absolute paths like `/Users/...`

### Documentation Policy
Update these files for any non-trivial change:
- `mds/guides/GUIDE.md` - User workflows
- `mds/guides/REFERENCE.md` - Command/API reference
- `mds/guides/WORKFLOW.md` - Engineering conventions
- `mds/IDEAS.md` - Roadmap adjustments (remove completed items!)
- `mds/CHANGELOG.md` - Session notes (always add entry)

**Rule:** If it's worth committing, it's worth documenting. Users rely on docs to discover features.

---

## Common Patterns

### Scryfall API Usage
Prefer cached bulk dumps (`all-cards.json.gz`, `oracle-cards.json.gz`, `unique-artwork.json.gz`) over live API calls. Rate limit: 10 req/sec (not enforced in code for bulk).

Image downloads use ThreadPoolExecutor with retry logic:
```python
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {
        executor.submit(_download_image_with_retry, url, dest, max_retries=3)
        for url, dest in download_jobs
    }
```

### Land Classification
Type-based organization via `_classify_land_type()` in `create_pdf.py` (search for function definition):
- **Basic:** `mono/plains`, `mono/island`, `mono/mountain`, `mono/forest`, `mono/swamp`, or `colorless/wastes`
- **Non-basic:** `dual/`, `tri/`, `utility/legendary/`, `utility/special/`, `utility/common/`

**Algorithm:** Uses `produced_mana` field for dual/tri detection (checks length of array), `type_line` for legendary/basic keywords. Special cases handled: tri-lands with multiple types, colorless utility lands.

**Rationale:** Groups functionally interchangeable lands regardless of set (e.g., all mono blue sources together), unlike set-based organization. Makes it easy to browse alternatives when building decks.

### Token Relationship Expansion
System automatically expands relationships:
- MDFC back faces (modal double-faced cards)
- Token creation (via `created_tokens` table)
- Meld partners

See `create_pdf.py:_fetch_cards_universal()` for universal fetch flow.

---

## Testing Strategy

### Test Files
- `tests/test_integration.py` - 17 integration tests
- `tests/data/fixtures/` - Golden datasets with `manifest.json`
- `tools/test_schema.py` - 9 schema validation tests

### Adding Tests
1. Create fixture in `tests/data/fixtures/`
2. Add entry to `manifest.json` with expected values
3. Document in `fixtures/README.md`
4. Add test case to `test_integration.py`

---

## Important Constraints

### PDF Generation
- Output path resolved relative to project root (not images folder)
- Interactive mode requires alphanumeric PDF filename (no spaces)
- No-overwrite safeguard: timestamp suffix if collision
- **Fronts % 8 == 0 or auto-pad prompt** - This is for 8-up printing layouts (3x3 with one slot empty)
- Back faces: if fronts exist but backs are empty, prompts to auto-fill with shared card back

### Profile System
- Configuration in `proxy-machine/assets/profiles.json`
- CLI shorthand flags auto-generated (`--patrick` for profile "patrick")
- Directory structure enforced by "Initialize Profiles" menu option
- **Symlinks required** - shared-cards/ must link to shared/ library or searches fail

### Database Schema
- Schema v6 (current)
- Foreign keys enabled: `PRAGMA foreign_keys = ON;`
- WAL mode: `PRAGMA journal_mode = WAL;`
- **No in-app migrations** - rebuild from source on schema change
- Schema version checked on startup - mismatches fail fast

### When NOT to Use Database
- **Don't** store user data in database (profiles, preferences, etc.) - use JSON configs
- **Don't** modify Scryfall data - database is read-only after build
- **Don't** rely on database for file paths - files are canonical, database is index

---

## Troubleshooting

### "No matches" for searches
Force bulk rebuild: `make bulk-sync` or `make bulk-index-rebuild`

Common cause: Database out of sync with bulk files after manual edits.

### Database issues
```bash
make bulk-verify      # Check health
make bulk-vacuum      # Optimize
make db-info          # Show stats
```

If database is corrupted: **just rebuild** - it's ephemeral by design. Don't try to repair.

### Import errors
```bash
make deps             # Reinstall dependencies
uv run pyright        # Check type errors
```

If `uv` not found: Install from https://github.com/astral-sh/uv (required, not optional).

### Memory issues during queries
Use `query_cards_optimized()` with filters to reduce result set:
```python
cards = query_cards_optimized(set_filter="znr", limit=100)  # Good
cards = query_all_cards()  # Bad - loads 500K+ cards
```

Original design loaded everything into memory (2GB+). Phase 2 refactor pushed filters to SQL (95% memory reduction). Always use optimized queries.

### Symlink issues (profile can't find shared assets)
Run `make menu` → Profiles → Initialize Profiles. This recreates all required symlinks.

On Windows: Symlinks require admin privileges. Consider using WSL instead.

---

## References

- `mds/PROJECT_OVERVIEW.md` - Complete technical documentation (27K+ words)
- `mds/guides/WORKFLOW.md` - Engineering workflow and conventions
- `mds/guides/DEVELOPER_GUIDE.md` - Setup, architecture, common tasks
- `mds/guides/REFERENCE.md` - All commands, flags, APIs
- `mds/guides/GUIDE.md` - User quick-start guide
