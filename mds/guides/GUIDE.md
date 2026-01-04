# The Proxy Machine: User Guide

**Quick-start guide for first-time users.** For complete command reference, see `REFERENCE.md`. For engineering details, see `WORKFLOW.md`.

---

## Quick Start (5 Steps)

1. **Install prerequisites**: macOS, `uv`, git, make
2. **Clone repository**: `cd proxy-machine/`
3. **Setup environment**: `make setup`
4. **Fetch assets**: `make fetch-basics` (lands) and `make fetch-tokens` (tokens)
5. **Launch menu**: `make menu`

That's it! You're ready to print proxies.

---

## Common Workflows

### Print a Deck

**Option 1: Via Menu**
1. `make menu` → Deck Tools → Generate PDF
2. Select profile, enter PDF name
3. Done! PDF saved to `pdfs-of-decks/`

**Option 2: Via Command**
```bash
make pdf PROFILE=patrick
```

Place card images in `pictures-of-cards/to-print/front/` and `back/` first.

### Fetch Card Art

**Basic Lands**
```bash
make fetch-basics                    # English only
make fetch-basics LANG=en,ph         # Multiple languages
make fetch-basics SET=ltr            # Specific set
```

**Non-Basic Lands**
```bash
make fetch-nonbasics
make fetch-nonbasics SET=mh3
```

**Tokens**
```bash
make fetch-tokens
make fetch-tokens SUBTYPE=Spirit SET=mh3
```

**Any Card Type**
```bash
make fetch-cards TYPE=creature RARITY=rare
make fetch-cards TYPE=enchantment SET=ltr
```

### Analyze a Deck

```bash
make deck-report DECK=path/to/list.txt
```

Supports local files and URLs from Moxfield, Archidekt, TappedOut, MTGGoldfish.

### Search & Discover

```bash
make cards-search QUERY="destroy all creatures"
make artist-search ARTIST="Rebecca Guay"
make random-cards COUNT=5
make explore-set SET=ltr
```

---

## Interactive Menu

```bash
make menu
```

**Menu Sections:**
- **Deck Tools** - Generate PDFs, analyze deck lists
- **Tokens** - Search, fetch, build token packs
- **Profiles** - Manage profiles and folders
- **Maintenance** - Health checks, coverage reports, optimization
- **Plugins** - Enable/disable deck format parsers

Press `0` to exit at any time.

---

## Maintenance

### Health Checks
```bash
make status                          # Collection stats
make library-health                  # Audit shared libraries
make land-coverage TYPE=all          # Coverage reports
make verify                          # Workspace health
```

### Optimization
```bash
make optimize-images DRY_RUN=1       # Preview PNG optimization
make dedupe-images                   # Remove duplicates
make db-optimize                     # Add database indexes
make clean                           # Remove temp files
```

### Backups
```bash
make backup                          # Create git bundle + snapshot
```

Backups stored in `../archived/proxy-printer-backups/`

---

## Troubleshooting

**`uv` not found**
- Makefile auto-installs; if it fails, install manually from <https://github.com/astral-sh/uv>

**Bulk download errors**
- Re-run `make fetch-basics` - byte validation ensures corrupted files are retried

**Slow searches**
- Run `make db-optimize` to add SQLite indexes

**Missing images**
- Re-run fetchers: `make fetch-basics`, `make fetch-tokens`
- Check availability: `make tokens-list`

**PDF layout issues**
- Fronts must be multiple of 8 (tool offers auto-padding)
- Backs required for single-sided cards (tool prompts for shared back)

**Disk space low**
- Run `make verify MIN_GB=10` to check
- Clean up old archives in `magic-the-gathering/shared/`

---

## File Naming Quick Reference

When fetching assets, files are automatically named using these patterns:

**Basic/Non-Basic Lands:**
```
forest-fullart-en-280.png
commandtower-borderless-en-340.png
```
Format: `<name>-<arttype>-<lang>[-<collector>].png`

**Tokens:**
```
tokens/insect/tmh3/insect-standard-en-tmh3.png
tokens/spirit/tvow/spirit-fullart-en-tvow.png
```
Format: `<subtype>/<set>/<name>-<arttype>-<lang>-<set>.png`

**Other Cards:**
```
lightningbolt-standard-en-ltr-123.png
tarmogoyf-borderless-en-mh2.png
```
Format: `<name>-<arttype>-<lang>-<set>[-<collector>].png`

**Art Types:** standard, fullart, showcase, borderless, extended, retro, textless

See `REFERENCE.md` for complete naming documentation.

---

## Next Steps

- **Complete command reference**: See `REFERENCE.md` for all commands, flags, and APIs
- **Engineering details**: See `WORKFLOW.md` for architecture and conventions
- **Roadmap**: See `IDEAS.md` for upcoming features
- **More commands**: Run `make help` or `make help-full`

---

**You're all set!** Start with `make menu` and explore the interactive interface.
