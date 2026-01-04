# The Proxy Machine: Complete Reference

This document provides exhaustive documentation for all commands, flags, APIs, and configuration options. For quick-start guidance, see `GUIDE.md`. For engineering details, see `WORKFLOW.md`.

---

## Table of Contents

1. [Make Commands](#make-commands)
2. [CLI Flags](#cli-flags)
3. [Dashboard API](#dashboard-api)
4. [Configuration Files](#configuration-files)
5. [Plugin System](#plugin-system)
6. [Environment Variables](#environment-variables)

---

## Make Commands

### Setup & Environment

**`make setup`** - First-time environment setup
```bash
make setup
```

**`make venv`** - Create Python virtual environment
```bash
make venv
```

**`make deps`** - Install dependencies
```bash
make deps
```

**`make deps-offline`** - Install from cache only
```bash
make deps-offline
```

### Core Workflows

**`make menu`** - Launch interactive menu
```bash
make menu
```

**`make pdf`** - Generate PDF for profile
```bash
make pdf PROFILE=patrick
```

**`make deck-report`** - Analyze deck list
```bash
make deck-report DECK=path/to/list.txt [PROFILE=patrick]
```

### Asset Fetching

**`make fetch-basics`** - Download basic lands
```bash
make fetch-basics [LANG=en,ph] [SET=ltr] [DRY=1]
```

**`make fetch-nonbasics`** - Download non-basic lands
```bash
make fetch-nonbasics [LANG=en] [SET=ltr] [DRY=1]
```

**`make fetch-tokens`** - Download tokens
```bash
make fetch-tokens [LANGS=en] [SET=mh3] [SUBTYPE=Spirit]
```

**`make fetch-cards`** - Universal card fetching
```bash
make fetch-cards TYPE=creature [RARITY=rare] [LIMIT=20]
```

**`make scrape-art`** - Scrape web galleries
```bash
make scrape-art URL=https://example.com [PAGES=10]
```

### Token Tools

**`make tokens-list`** - List cached tokens
```bash
make tokens-list [FILTER=Spirit] [LIMIT=25]
```

**`make tokens-explorer`** - Interactive token browser
```bash
make tokens-explorer
```

**`make tokens-keyword`** - Search by keyword
```bash
make tokens-keyword KEYWORD=flying [SET=mh3]
```

**`make token-pack-from-deck`** - Build token pack
```bash
make token-pack-from-deck DECK=path [NAME=packname]
```

### Search & Discovery

**`make cards-search`** - Oracle text search
```bash
make cards-search QUERY="destroy all" [SET=mh3]
```

**`make artist-search`** - Find cards by artist
```bash
make artist-search ARTIST="Rebecca Guay"
```

**`make random-cards`** - Random card discovery
```bash
make random-cards [TYPE=creature] [COUNT=5]
```

**`make explore-set`** - Browse set like binder
```bash
make explore-set SET=ltr [TYPE=creature]
```

**`make random-commander`** - Random commander
```bash
make random-commander [COLORS=wu]
```

### Maintenance

**`make status`** - Collection statistics
```bash
make status
```

**`make library-health`** - Audit libraries
```bash
make library-health [FIX_NAMES=1] [FIX_DUPES=1]
```

**`make land-coverage`** - Coverage reports
```bash
make land-coverage [TYPE=basic] [MISSING=1]
```

**`make optimize-images`** - PNG optimization
```bash
make optimize-images [DRY_RUN=1]
```

**`make clean`** - Remove temp files
```bash
make clean
```

**`make test`** - Syntax validation
```bash
make test
```

**`make verify`** - Workspace health check
```bash
make verify [MIN_GB=1.0]
```

### Database

**`make bulk-sync`** - Update all bulk data
```bash
make bulk-sync
```

**`make bulk-index-build`** - Build database
```bash
make bulk-index-build
```

**`make bulk-index-info`** - Database stats
```bash
make bulk-index-info
```

**`make db-optimize`** - Add indexes
```bash
make db-optimize
```

### Backup

**`make backup`** - Create backup
```bash
make backup
```

### Notifications

**`make discord-stats`** - Send stats
```bash
make discord-stats
```

**`make discord-alert`** - Send alert
```bash
make discord-alert MSG="text"
```

### Web Dashboard

**`make dashboard`** - Run dashboard
```bash
make dashboard
```

### Plugins

**`make plugins-list`** - List plugins
```bash
make plugins-list
```

**`make plugins-enable`** - Enable plugin
```bash
make plugins-enable NAME=myplugin
```

---

## CLI Flags

### Profile & Output
- `--profile <name>` - Load profile
- `--pdf_name <name>` - PDF filename

### PDF Generation
- `--card_size <size>` - Card size (standard/poker)
- `--crop <value>` - Crop margin (3mm)
- `--ppi <value>` - Resolution (600)
- `--quality <value>` - JPEG quality (100)

### Land Fetching
- `--fetch_basics` - Fetch basic lands
- `--fetch_non_basics` - Fetch non-basic lands
- `--lang <codes>` - Language codes
- `--land_set <code>` - Set filter
- `--fetch_dry_run` - Preview mode

### Token Fetching
- `--fetch_tokens` - Fetch tokens
- `--token_fetch_name <name>` - Name filter
- `--token_fetch_subtype <type>` - Subtype filter
- `--token_fetch_set <code>` - Set filter
- `--token_fetch_dry_run` - Preview mode

### Search
- `--card_search <query>` - Oracle search
- `--card_search_set <code>` - Set filter
- `--card_include_tokens` - Include tokens

### Card Filtering
- `--card_rarity <rarity>` - Filter by rarity (common, uncommon, rare, mythic)
- `--card_type <type>` - Filter by type (creature, artifact, etc.)
- `--card_artist <name>` - Filter by artist name
- `--card_colors <colors>` - Filter by colors (W,U,B,R,G)

### Global
- `--json` - JSON output
- `--quiet` - Minimal output
- `--verbose` - Detailed output

---

## Dashboard API

Base URL: `http://127.0.0.1:5001`

### Endpoints

**`GET /api/search`** - Search cards
```bash
curl 'http://127.0.0.1:5001/api/search?query=flying&limit=10'
```

**`GET /api/coverage`** - Coverage data
```bash
curl 'http://127.0.0.1:5001/api/coverage?kind=basic&set=ltr'
```

**`GET /coverage_csv`** - Download CSV
```bash
curl -o coverage.csv 'http://127.0.0.1:5001/coverage_csv?kind=basic'
```

**`GET /api/db_info`** - Database stats
```bash
curl 'http://127.0.0.1:5001/api/db_info'
```

---

## Configuration Files

### profiles.json
Location: `proxy-machine/assets/profiles.json`

```json
{
  "profiles": {
    "name": {
      "base_directory": "path/to/profile",
      "front_dir": "front",
      "back_dir": "back",
      "output_path": "path/to/pdfs/name.pdf"
    }
  }
}
```

### notifications.json
Location: `proxy-machine/config/notifications.json`

```json
{
  "macos_notifications": {"enabled": true},
  "webhook": {
    "enabled": false,
    "url": "https://hooks.example.com"
  }
}
```

---

## Plugin System

### Structure
```
proxy-machine/plugins/
└── my_plugin/
    ├── __init__.py
    └── deck_formats.py
```

### Minimal Plugin
```python
PLUGIN = {
    "name": "my_plugin",
    "version": "1.0.0",
    "description": "Description",
    "enabled": True
}
```

---

## Environment Variables

**`PM_OFFLINE=1`** - Disable network
```bash
PM_OFFLINE=1 make menu
```

**`PM_LOG=json|quiet|verbose`** - Logging mode
```bash
PM_LOG=json make cards-search QUERY="flying"
```

**`BACKUPS=N`** - Backup count
```bash
BACKUPS=20 make backup
```

---

## File Naming Conventions

### Basic Lands
**Path:** `shared/basic-lands/<landtype>/<filename>.png`
**Format:** `<landname>-<arttype>-<lang>-<set>-<collector>.png`

**Examples:**
- `basic-lands/mono/plains/plains-standard-en-ltr-260.png`
- `basic-lands/colorless/wastes/wastes-fullart-en-ogw-184.png`

**Components:**
- `<landtype>`: Output of `_classify_land_type` (e.g., `mono/plains`, `colorless/wastes`)
- `<landname>`: plains, island, swamp, mountain, forest, wastes (lowercase, hyphenated)
- `<arttype>`: standard, fullart, borderless, showcase, extended, retro, textless, etc.
- `<lang>`: Language code (en, ja, ph, es, fr, de, ...)
- `<set>`: Set code (always included)
- `<collector>`: Collector number (always included for stable stems)

### Non-Basic Lands
**Path:** `shared/non-basic-lands/<landtype>/<filename>.png`
**Format:** `<landname>-<arttype>-<lang>-<set>-<collector>.png`

**Examples:**
- `non-basic-lands/dual/watery_grave-borderless-en-rna-259.png`
- `non-basic-lands/utility/legendary/yavimaya_hollow-fullart-en-usg-330.png`

**Components:**
- `<landtype>`: Derived from `_classify_land_type` (e.g., `dual`, `tri`, `utility/legendary`, `special/gates`)
- `<landname>`: Lowercase, underscores instead of spaces/punctuation
- `<arttype>`: Can be compound (e.g., `borderless-oilslick`)
- `<lang>`: Language code
- `<set>`: Set code
- `<collector>`: Collector number (required)

### Tokens
**Path:** `shared/tokens/<subtype>/<set>/<filename>.png`
**Format:** `<tokenname>-<arttype>-<lang>-<set>.png`

**Examples:**
- `tokens/insect/tmh3/insect-standard-en-tmh3.png`
- `tokens/spirit/tvow/spirit-fullart-en-tvow.png`
- `tokens/soldier/tone/soldier-borderless-en-tone.png`

**Components:**
- `<subtype>`: Token subtype directory (insect, spirit, soldier, etc.)
- `<tokenname>`: Lowercase, no spaces/dashes
- `<arttype>`: standard, fullart, showcase, borderless
- `<lang>`: Language code
- `<set>`: Set code (always included in filename for tokens)

### Other Card Types (Creatures, Enchantments, Artifacts, etc.)
**Path:** `shared/<type>/<filename>.png`
**Format:** `<cardname>-<arttype>-<lang>-<set>[-<collector>].png`

**Examples:**
- `lightningbolt-standard-en-ltr-123.png`
- `tarmogoyf-borderless-en-mh2.png`
- `solring-showcase-en-cmr.png`

**Components:**
- `<type>`: creatures, enchantments, artifacts, instants, sorceries, planeswalkers
- `<cardname>`: Lowercase, no spaces/commas/apostrophes/dashes
- `<arttype>`: standard, fullart, showcase, borderless, extended, retro
- `<lang>`: Language code
- `<set>`: Set code (always included)
- `<collector>`: Collector number (optional)

### Card Backs
**Path:** `shared/card-backs/<filename>.png`
**Format:** Descriptive names (no standard format)

**Examples:**
- `magic-card-back.png`
- `custom-back-blue.png`

### Collision Resolution
All naming functions use 3-tier collision resolution:
1. Try with collector number: `basename-123.png`
2. Try without collector: `basename.png`
3. Numeric suffix: `basename-2.png`, `basename-3.png`, etc.

---

For complete parameter details and advanced usage, see the inline help:
```bash
uv run python create_pdf.py --help
make help-full
```
