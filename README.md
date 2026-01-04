# The Proxy Machine

> Professional MTG proxy card generation and deck management

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blueviolet.svg)](https://claude.ai/code)

---

## Quick Start

```bash
# Install dependencies
make deps

# Download card database (first time only, 5-10 min)
make bulk-sync

# Launch interactive menu
make menu

# Generate PDF from your cards
make pdf PROFILE=yourname
```

---

## What Is This?

The Proxy Machine is a self-hosted system for creating high-quality Magic: The Gathering proxy cards for casual play. It features:

- 🎴 **500K+ Cards** - Complete Scryfall database with SQLite search
- 📦 **10+ Game Support** - MTG, Lorcana, Flesh and Blood, and more
- 🖨️ **Print-Ready PDFs** - Precise layouts for professional results
- 🎯 **Intelligent Organization** - Type-based land/token sorting
- 🌍 **Multi-Language** - Support for 15+ languages
- ⚡ **Fast Caching** - 6-10x query speedup
- 📊 **Collection Management** - Track your 15K+ proxy collection

---

## Project Structure

```
proxy-machine/
├── README.md              # You are here
├── CLAUDE.md              # AI agent guidance
├── Makefile               # Command shortcuts
│
├── src/                   # All source code
│   ├── create_pdf.py      # Main CLI (run this!)
│   ├── dashboard.py       # Web dashboard
│   ├── config_paths.py    # Path configuration
│   ├── core/              # Business logic
│   ├── db/                # Database layer (SQLite)
│   ├── pdf/               # PDF generation utilities
│   ├── deck/              # Deck parsing (15+ formats)
│   ├── services/          # External API clients
│   ├── plugins/           # Game-specific modules (10+ games)
│   ├── config/            # Configuration files
│   ├── cli/               # CLI modules
│   ├── fetch/             # Card fetching logic
│   ├── net/               # Network utilities
│   └── tests/             # Test suite
│
├── scripts/               # Utility scripts
│   ├── deploy-to-unraid.sh  # Deployment script
│   └── [more utilities]
│
├── tools/                 # Development tools
│
├── docs/                  # All documentation
│   ├── guides/            # User guides, workflows, reference
│   ├── improvements/      # Upgrade guides, roadmaps
│   ├── planning/          # Architecture decisions
│   ├── DEVELOPMENT.md     # Development workflow
│   ├── SESSION_TEMPLATE.md  # Claude Code templates
│   └── [more docs]
│
├── assets/                # Static assets
│   ├── cutting_templates/ # Cutting guides
│   ├── calibration/       # Calibration files
│   └── examples/          # Example files
│
├── data/                  # Runtime data (gitignored)
│   ├── bulk-data/         # Scryfall bulk data
│   ├── logs/              # Application logs
│   └── cache/             # Query cache (100MB)
│
└── magic-the-gathering/   # Card images & decks (optional)
    ├── shared/            # Shared card library
    └── proxied-decks/     # User profiles
```

---

## Common Commands

### PDF Generation
```bash
make pdf PROFILE=patrick           # Generate PDF
make menu                          # Interactive menu
```

### Card Fetching
```bash
make fetch-basics LANG=en SET=mh3    # Fetch basic lands
make fetch-nonbasics SET=ltr         # Fetch non-basic lands
make fetch-tokens SUBTYPE=Spirit     # Fetch tokens
make fetch-cards TYPE=creature RARITY=rare LIMIT=20  # Universal fetch
```

### Deck Management
```bash
make deck-report DECK=path/to/deck.txt  # Analyze deck
make tokens-list FILTER=Spirit          # List available tokens
```

### Database
```bash
make bulk-sync          # Download + rebuild database
make db-info            # Show database statistics
make bulk-vacuum        # Optimize database
```

### Maintenance
```bash
make library-health     # Check collection health
make land-coverage TYPE=basic    # Land coverage report
make optimize-images DRY_RUN=1   # Optimize images (dry run)
```

---

## Configuration

### Environment Variables

All settings support `PM_*` environment variables:

```bash
export PM_LOG_LEVEL=DEBUG            # Logging: DEBUG, INFO, WARNING, ERROR
export PM_MAX_DOWNLOAD_WORKERS=16    # Concurrent downloads (default: 8)
export PM_DEFAULT_PPI=1200           # Image quality (default: 600)
export PM_DB_CACHE_SIZE_MB=200       # Cache size (default: 100)
```

### Configuration File

Edit `config/settings.py` for defaults, or use environment variables for overrides.

---

## Documentation

### Start Here
- **README.md** (this file) - Project overview and quick start
- **[docs/guides/GUIDE.md](docs/guides/GUIDE.md)** - User guide and workflows
- **[docs/guides/REFERENCE.md](docs/guides/REFERENCE.md)** - Complete command reference

### For Developers
- **[CLAUDE.md](CLAUDE.md)** - Architecture guidance for AI agents
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Git workflow and development setup
- **[docs/SESSION_TEMPLATE.md](docs/SESSION_TEMPLATE.md)** - Template for Claude Code sessions
- **[docs/guides/DEVELOPER_GUIDE.md](docs/guides/DEVELOPER_GUIDE.md)** - Setup and contribution guide
- **[docs/guides/WORKFLOW.md](docs/guides/WORKFLOW.md)** - Engineering conventions
- **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** - How to contribute

### Recent Improvements
- **[docs/improvements/QUICKSTART_IMPROVEMENTS.md](docs/improvements/QUICKSTART_IMPROVEMENTS.md)** - New features activation (5 min)
- **[docs/improvements/OPTIONS_ABC_COMPLETE.md](docs/improvements/OPTIONS_ABC_COMPLETE.md)** - Infrastructure upgrade summary
- **[docs/improvements/IMPROVEMENTS_ROADMAP.md](docs/improvements/IMPROVEMENTS_ROADMAP.md)** - Future roadmap

### Technical Details
- **[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)** - Complete technical documentation (27K words)
- **[docs/planning/](docs/planning/)** - Architecture decisions and planning

---

## Features

### Database & Search
- SQLite database with 500K+ cards from Scryfall
- Full-text search (FTS5)
- Type-based land organization (mono, dual, tri, utility)
- Token relationship tracking
- Multi-language support (15+ languages)
- **6-10x faster queries** with disk caching

### PDF Generation
- Print-ready layouts (Letter, A4, Tabloid, A3)
- Duplex printing support
- Precise card positioning (2.5" x 3.5")
- Multiple card backs
- Automatic padding for 8-up layouts

### Deck Parsing
- 15+ deck formats supported (Moxfield, Archidekt, MTGA, etc.)
- Token detection and generation
- Deck analysis and reports
- Missing card identification

### Plugin System
- 10+ games supported:
  - Magic: The Gathering (primary)
  - Disney Lorcana
  - Flesh and Blood
  - One Piece TCG
  - Yu-Gi-Oh!
  - Pokemon
  - And more...
- Easy plugin creation

### Logging & Monitoring
- Structured logging with Loguru
- File rotation (10MB, 10 days retention)
- Colored console output
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

---

## Requirements

- Python 3.9+
- 3GB+ disk space (for database)
- macOS, Linux, or WSL
- UV package manager (recommended) or pip

---

## Installation

### 1. Clone & Setup
```bash
git clone https://github.com/patrickhere/proxy-machine.git
cd proxy-machine
make setup     # Install UV + dependencies
```

### 2. Build Database (first time only)
```bash
make bulk-sync   # Downloads 2.3GB, takes 5-10 minutes
```

### 3. Run!
```bash
make menu
```

---

## Troubleshooting

### Database Issues
```bash
make bulk-verify      # Check database health
make bulk-vacuum      # Optimize database
make bulk-sync        # Rebuild from scratch
```

### Cache Issues
```bash
du -sh .cache/        # Check cache size
rm -rf .cache/        # Clear cache (rebuilds automatically)
```

### Dependency Issues
```bash
make deps             # Reinstall dependencies
uv pip list           # Check installed packages
```

### Logs
```bash
tail -f logs/proxy-machine_*.log    # Watch logs
grep ERROR logs/*.log               # Find errors
```

---

## Performance

- **Database:** 508K cards, 130K relationships, 764MB
- **Query Time:** <2ms (cached), ~10ms (uncached)
- **Cache Hit Ratio:** 70-90% for typical usage
- **PDF Generation:** <10s for 100 cards
- **Download Throughput:** 100+ cards/minute

---

## Contributing

We welcome contributions! See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

---

## License

MIT License - See LICENSE file for details

---

## Credits

- **Built with Claude Code** - AI-assisted development and vibe-coding
- **Scryfall API** - Card data and images
- **Community Contributors** - Testing, feedback, and improvements

---

## Support

- **Documentation**: Check `docs/` directory
- **Issues**: Create a GitHub issue
- **Questions**: See `docs/guides/GUIDE.md`

---

**Happy proxy printing!** 🎴✨
