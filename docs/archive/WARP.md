# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

The Proxy Machine is a sophisticated Magic: The Gathering proxy card generation system with enterprise-grade data integration, multi-language support, and comprehensive card management capabilities. The system manages 508,074+ cards from Scryfall's complete dataset and features advanced PDF generation, token management, and plugin architecture.

## Common Development Commands

### Environment Setup
```bash
# Install/update all dependencies (uses uv package manager)
make deps

# Install dependencies in offline mode (from cache only)
make deps-offline
```

### Main Application
```bash
# Launch interactive menu system (primary interface)
make menu

# Generate PDF for specific profile
make pdf PROFILE=patrick

# Launch web dashboard
make dashboard
```

### Database Management
```bash
# Build SQLite bulk index for fast queries (auto-built on first use)
make bulk-index-build

# Force rebuild database
make bulk-index-rebuild

# Optimize database performance
make bulk-index-vacuum

# Show database statistics
make bulk-index-info

# Download bulk data from Scryfall
make bulk-fetch-all
```

### Card Management
```bash
# Fetch basic lands with multi-language support
make fetch-basics [LANG=en,ph] [SET=ltr] [FULLART=1] [DRY=1] [RETRY=1]

# Fetch non-basic lands
make fetch-nonbasics [LANG=en,ph] [SET=ltr] [FULLART=1] [DRY=1] [RETRY=1]

# Fetch by specific art type
make fetch-by-arttype ARTTYPE=showcase [LANG=ph] [SET=one] [DRY=1]

# Preview lands without downloading
make preview-lands LANG=ph SET=one [LIMIT=10]
```

### Search and Analysis
```bash
# Search cards by oracle text
make cards-search QUERY="enter the battlefield" [SET=khm] [LIMIT=30] [INCLUDE=1]

# Search tokens by keyword
make tokens-keyword KEYWORD=flying [SET=mh3] [LIMIT=25]

# Generate deck report from file or URL
make deck-report DECK=path/to/list.txt [PROFILE=patrick]

# Coverage reports for lands/tokens
make land-coverage TYPE=basic|nonbasic|all [SET=abc] [OUT=dir]
```

### Development and Maintenance
```bash
# Run pre-commit hooks
make precommit-run

# Install git hooks
make hooks-install

# Create backup
make backup

# Run library health checks
make library-health [FIX_NAMES=1] [FIX_DUPES=1] [HASH=6]

# System verification
make verify [JSON=1] [MIN_GB=1.0]
```

### Testing Individual Components
```bash
# Run single test
uv run python -m pytest tests/test_specific.py::test_function -v

# Test specific functionality
uv run python create_pdf.py --help
```

## High-Level Architecture

### Core System Components

#### 1. Main Application (`create_pdf.py`)
- **Central CLI and Menu System**: Primary interface with comprehensive Click-based CLI
- **PDF Generation Engine**: Handles proxy card printing with configurable layouts
- **Multi-Language Card Fetching**: Advanced Scryfall integration with 18 language support
- **Memory Monitoring**: Enterprise-grade tracking with psutil integration
- **Notification System**: macOS and webhook notification support

#### 2. Database Layer (`db/bulk_index.py`)
- **32-Field Schema**: Comprehensive card metadata (artist, rarity, cmc, colors, etc.)
- **Multi-Language SQL Queries**: Efficient `lang IN (?,?)` handling
- **Performance Indexes**: Optimized for common query patterns
- **Automatic Database Management**: Self-building from Scryfall bulk data
- **Graceful Fallbacks**: JSON fallback when SQLite unavailable

#### 3. Plugin Architecture (`plugins/`)
- **Discoverable Plugins**: Auto-detection via `__init__.py` metadata
- **State Management**: Persistent enable/disable via `config/plugins.json`
- **Game Support**: Pre-built plugins for MTG, Digimon, Flesh & Blood, etc.
- **Plugin Manager**: CLI and menu-driven plugin lifecycle management

#### 4. Web Dashboard (`dashboard.py`)
- **Flask-Based UI**: Local web interface for browser workflows
- **JSON API**: Comprehensive REST endpoints for search, coverage, etc.
- **Async Task Management**: Background processing with live status
- **Offline Mode Support**: `PM_OFFLINE=1` for network-free operation

#### 5. Profile System (`assets/profiles.json`)
- **User Workspaces**: Per-user directory structures and configurations
- **Symlink Management**: Shared asset libraries linked into profiles
- **Path Resolution**: Project-relative paths with automatic resolution

### Data Flow Architecture

```
Scryfall API → Bulk Data Downloads → SQLite Database → Search/Filter → Card Images → PDF Generation
     ↓              ↓                      ↓              ↓              ↓
  Rate Limited   Cached JSON         Performance     CLI/Menu      Profile Dirs
  API Calls      Fallbacks          Acceleration     Interface      Output PDFs
```

### Key Design Patterns

#### 1. Dual Storage Strategy
- **Primary**: SQLite database for fast queries (508K+ cards)
- **Fallback**: JSON index files when database unavailable
- **Auto-Building**: Database created automatically on first fetch operation

#### 2. Modular CLI Architecture
- **Click Framework**: Hierarchical command structure
- **Flag Registration**: Dynamic profile shortcuts (`--patrick`)
- **Menu System**: Interactive TUI with boxed interface
- **Make Integration**: Workflow automation via comprehensive Makefile

#### 3. Shared Library Management
- **Asset Categories**: tokens, card-backs, basic-lands, non-basic-lands, creatures, etc.
- **Naming Convention**: `%landtype%-%arttype%[-collector|-N].ext`
- **Symlink Strategy**: Per-profile links to shared libraries
- **Collision Resolution**: Collector number suffixes, then numeric

#### 4. Enterprise Error Handling
- **Graceful Degradation**: Continue operation when optional components fail
- **Retry Logic**: Failed downloads tracked and retried automatically
- **Memory Monitoring**: Track and report memory usage during bulk operations
- **Progress Reporting**: Single-line updates for long-running operations

### Plugin System Design

Plugins are discovered as subdirectories under `plugins/` with `__init__.py` files exposing `PLUGIN` metadata:

```python
PLUGIN = {
    "name": "plugin_name",
    "version": "1.0.0",
    "description": "Plugin description"
}
```

Management via:
- Menu interface (Option 5)
- CLI: `--plugins_list`, `--plugins_enable NAME`, `--plugins_disable NAME`
- Make targets: `make plugins-list`, `make plugins-enable NAME=x`

### Configuration Management

#### Critical Configuration Files
- `assets/profiles.json`: Profile definitions and paths
- `config/notifications.json`: Notification settings (auto-created)
- `config/plugins.json`: Plugin enable/disable state
- `requirements.txt`: Python dependencies (managed via uv)

#### Environment Variables
- `PM_OFFLINE`: Disable network operations
- `PM_ASK_REFRESH`: Prompt before bulk data refresh
- `PM_LOG`: Control logging modes (json|quiet|verbose)

### Path Resolution Strategy

All paths resolved relative to project root:
- `script_directory`: Location of `create_pdf.py`
- `project_root_directory`: Parent of `proxy-machine/`
- Profile paths: Resolved relative to project root, not script directory
- Shared libraries: Under `magic-the-gathering/shared/`

## Testing Strategy

### Manual Testing Workflows
```bash
# Test basic functionality
make menu  # Validate interactive menu
make pdf PROFILE=test_profile  # Test PDF generation

# Test data fetching
make fetch-basics LANG=en SET=mh3 LIMIT=5  # Small fetch test
make tokens-list FILTER=spirit LIMIT=10  # Test search

# Test plugin system
make plugins-list  # Verify plugin discovery
```

### Validation Commands
```bash
# Verify workspace health
make verify

# Check database integrity
make db-wrapper CMD=verify

# Test notification system
make notifications-test
```

## Key Development Principles

### 1. Scryfall API Courtesy
- Prefer cached bulk data over live API calls
- Rate limit API requests (built-in limiter)
- Decouple image CDN downloads from API throttling
- Respect Scryfall's Terms of Service

### 2. User Experience
- Single-line progress updates for long operations
- Interactive prompts with sensible defaults
- No-overwrite safeguards for PDF generation
- Comprehensive help text and examples

### 3. Data Integrity
- Graceful handling of malformed/missing data
- Non-destructive duplicate detection
- Automatic backup creation (pre-push hooks)
- Comprehensive error logging

### 4. Performance
- SQLite acceleration for large datasets
- Parallel image downloads (thread pool)
- Memory monitoring and optimization
- Lazy loading of optional components

## Common Development Tasks

### Adding New Card Types
1. Define shared directory path in `create_pdf.py`
2. Add to `PROFILE_SYMLINKS` dictionary
3. Implement fetching logic using existing patterns
4. Add CLI flags and menu options
5. Update `WORKFLOW.md` and `GUIDE.md`

### Creating New Plugins
```bash
make plugins-new NAME=new_plugin
# Edit plugins/new_plugin/__init__.py
make plugins-enable NAME=new_plugin
```

### Database Schema Updates
1. Modify schema in `db/bulk_index.py`
2. Increment `SCHEMA_VERSION`
3. Add migration logic in `_ensure_schema()`
4. Test with `make bulk-index-rebuild`

### Adding New Make Targets
1. Add target to `Makefile` with proper dependencies
2. Follow existing patterns for parameter handling
3. Update help text in `make help`
4. Document in `GUIDE.md`

## Important Notes for AI Agents

### Critical Invariants
- Never edit `requirements.txt` without running `make deps` afterward
- Always use project-relative paths, never absolute paths
- Preserve the single-line progress update pattern for long operations
- Maintain backwards compatibility with existing profile structures

### Error Patterns to Avoid
- Don't assume SQLite database exists (always check/fallback)
- Don't make direct filesystem changes to shared libraries without updating indexes
- Don't break the no-overwrite PDF naming safeguard
- Don't bypass the rate limiting for Scryfall API calls

### Performance Considerations
- Use `_db_index_available()` before attempting database queries
- Prefer bulk operations over individual card processing
- Always provide progress feedback for operations > 1 second
- Consider memory usage for large datasets (508K+ cards)

This architecture supports a sophisticated card management system while maintaining flexibility for future enhancements and plugin development.
