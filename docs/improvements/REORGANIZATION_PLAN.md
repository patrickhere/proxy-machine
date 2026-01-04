# Project Reorganization Plan

**Goal:** Clean, logical structure that's easy to navigate

---

## Current Problems

1. **Root directory chaos**: 30+ Python files, 9 markdown files
2. **Unclear purpose**: Hard to tell which files are main vs. utility
3. **Mixed concerns**: Tools, scripts, documentation all mixed together
4. **No clear entry point**: Which file do I run?

---

## Proposed New Structure

```
proxy-machine/
├── README.md                          # Main entry point (keep)
├── CLAUDE.md                          # AI guidance (keep)
├── pyproject.toml                     # NEW: Modern Python project config
├── requirements.txt                   # Keep for backwards compat
│
├── src/                               # NEW: Main application code
│   └── proxy_machine/
│       ├── __init__.py
│       ├── __main__.py               # Entry: python -m proxy_machine
│       ├── cli.py                    # CLI commands (from create_pdf.py)
│       ├── menu.py                   # Interactive menu
│       ├── constants.py              # Keep
│       ├── errors.py                 # Keep
│       └── utilities.py              # Keep (PDF generation)
│
├── core/                              # Business logic (existing)
│   ├── __init__.py
│   ├── logging.py                    # ✓ Already created
│   ├── classification.py             # TODO: Extract
│   ├── art_types.py                  # TODO: Extract
│   └── naming.py                     # TODO: Extract
│
├── db/                                # Database (existing, good)
│   ├── __init__.py
│   ├── bulk_index.py
│   ├── types.py
│   └── query_cache.py
│
├── pdf/                               # PDF utilities (existing, good)
│   └── utils.py
│
├── deck/                              # Deck parsing (existing, good)
│   └── parser.py
│
├── services/                          # External services (existing, good)
│   └── fetch.py
│
├── plugins/                           # Game plugins (existing, good)
│   ├── mtg/
│   ├── lorcana/
│   └── ...
│
├── config/                            # Configuration (existing, good)
│   ├── __init__.py
│   ├── settings.py                   # ✓ Already created
│   └── schema.py
│
├── scripts/                           # NEW: Utility scripts
│   ├── maintenance/
│   │   ├── clean_up.py               # Move from root
│   │   ├── dedupe_shared_images.py   # Move from root
│   │   ├── normalize_set_folders.py  # Move from root
│   │   └── optimize_images.py        # Move from root
│   ├── migration/
│   │   ├── fix_dfc_lands.py          # Move from root
│   │   ├── migrate_mdfc_lands.py     # Move from root
│   │   └── merge_set_variants.py     # Move from root
│   ├── analysis/
│   │   ├── coverage.py               # Move from root
│   │   ├── rules_delta.py            # Move from root
│   │   └── enhanced_validation.py    # Move from root
│   └── utilities/
│       ├── calibration.py            # Move from root
│       ├── offset_pdf.py             # Move from root
│       ├── scrape_mythic_blackcore.py # Move from root
│       ├── scryfall_enrich.py        # Move from root
│       └── token_fetch_clean.py      # Move from root
│
├── tools/                             # CLI tools (existing)
│   ├── cards.py
│   ├── db.py
│   └── ...
│
├── tests/                             # Tests (existing, expand)
│   ├── unit/                         # NEW
│   │   ├── test_classification.py
│   │   ├── test_art_types.py
│   │   └── test_naming.py
│   ├── integration/
│   │   └── test_integration.py       # Existing
│   └── data/fixtures/                # Existing
│
├── docs/                              # Documentation
│   ├── guides/                       # Move from mds/guides/
│   │   ├── GUIDE.md
│   │   ├── WORKFLOW.md
│   │   ├── DEVELOPER_GUIDE.md
│   │   └── REFERENCE.md
│   ├── planning/                     # Move from mds/planning/
│   ├── archive/                      # Move from mds/archive/
│   ├── PROJECT_OVERVIEW.md           # Move from mds/
│   ├── IMPLEMENTATION_SUMMARY.md     # Move from root
│   ├── IMPROVEMENTS_ROADMAP.md       # Move from root
│   ├── QUICKSTART_IMPROVEMENTS.md    # Move from root
│   └── OPTIONS_ABC_COMPLETE.md       # Move from root
│
├── examples/                          # Example configs (existing, good)
│
├── archived/                          # Backups (existing, good)
│
├── .cache/                            # Runtime cache (existing, good)
│
├── logs/                              # Log files (existing, good)
│
└── [UNCHANGED]
    ├── assets/
    ├── benchmarks/
    ├── calibration/
    ├── cutting_templates/
    ├── fetch/
    ├── game/
    ├── hugo/
    └── magic-the-gathering/
```

---

## Migration Strategy

### Phase 1: Create New Structure (No Breaking Changes)
1. Create `src/proxy_machine/` directory
2. Create `scripts/` with subdirectories
3. Move markdown files to `docs/`
4. Keep everything working with symlinks

### Phase 2: Move Python Scripts
1. Move utility scripts to `scripts/` subdirectories
2. Update imports (if any)
3. Update Makefile targets
4. Test everything still works

### Phase 3: Consolidate Entry Points
1. Create `src/proxy_machine/cli.py` (copy from create_pdf.py)
2. Add `__main__.py` for `python -m proxy_machine`
3. Keep `create_pdf.py` as symlink for backwards compat
4. Update documentation

### Phase 4: Extract Modules
1. Extract classification, art_types, naming to `core/`
2. Update imports
3. Comprehensive testing

---

## Benefits

### Before (Current)
```
proxy-machine/
├── create_pdf.py
├── calibration.py
├── clean_up.py
├── coverage.py
├── dashboard.py
├── [25+ more Python files]
├── README.md
├── CLAUDE.md
├── [7+ more markdown files]
└── [20+ directories]
```
❌ Overwhelming
❌ No clear organization
❌ Hard to find things

### After (Proposed)
```
proxy-machine/
├── README.md                  # Start here
├── CLAUDE.md                  # For AI agents
├── src/                       # Main code
├── scripts/                   # Utilities (organized)
├── docs/                      # All documentation
├── tests/                     # All tests
├── core/db/pdf/deck/          # Modules
└── [data directories]         # Unchanged
```
✅ Clear entry point
✅ Logical grouping
✅ Easy to navigate

---

## Implementation Commands

### Phase 1: Documentation (SAFE - No code changes)
```bash
# Create docs structure
mkdir -p docs/{guides,planning,archive,reference}

# Move markdown files
mv mds/guides/*.md docs/guides/
mv mds/planning/*.md docs/planning/
mv mds/archive/*.md docs/archive/
mv mds/*.md docs/

# Move root-level docs
mv IMPLEMENTATION_SUMMARY.md docs/
mv IMPROVEMENTS_ROADMAP.md docs/
mv QUICKSTART_IMPROVEMENTS.md docs/
mv OPTIONS_ABC_COMPLETE.md docs/
mv CONTRIBUTING.md docs/
mv AI_PROJECT_DESCRIPTION.md docs/
mv WARP.md docs/archive/

# Update README to point to new locations
```

### Phase 2: Scripts (SAFE - Utility scripts)
```bash
# Create scripts structure
mkdir -p scripts/{maintenance,migration,analysis,utilities}

# Move maintenance scripts
mv clean_up.py scripts/maintenance/
mv dedupe_shared_images.py scripts/maintenance/
mv normalize_set_folders.py scripts/maintenance/
mv optimize_images.py scripts/maintenance/

# Move migration scripts
mv fix_dfc_lands.py scripts/migration/
mv migrate_mdfc_lands.py scripts/migration/
mv merge_set_variants.py scripts/migration/

# Move analysis scripts
mv coverage.py scripts/analysis/
mv rules_delta.py scripts/analysis/
mv enhanced_validation.py scripts/analysis/

# Move utility scripts
mv calibration.py scripts/utilities/
mv offset_pdf.py scripts/utilities/
mv scrape_mythic_blackcore.py scripts/utilities/
mv scryfall_enrich.py scripts/utilities/
mv token_fetch_clean.py scripts/utilities/
```

### Phase 3: Update Makefile (IMPORTANT)
```makefile
# Update paths in Makefile
# Example:
# Old: python coverage.py
# New: python scripts/analysis/coverage.py
```

### Phase 4: Add pyproject.toml (MODERN)
```toml
[project]
name = "proxy-machine"
version = "2.0.0"
description = "MTG proxy card generation and deck management"
requires-python = ">=3.9"
dependencies = [
    "click>=8.1.8",
    "pydantic>=2.11.1",
    "pydantic-settings>=2.6.1",
    "loguru>=0.7.2",
    "diskcache>=5.6.3",
    # ... rest from requirements.txt
]

[project.scripts]
proxy-machine = "proxy_machine.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.pyright]
exclude = ["**/.venv", "**/—python", "**/magic-the-gathering"]
```

---

## Backwards Compatibility

Keep these as symlinks for existing users:
```bash
ln -s src/proxy_machine/cli.py create_pdf.py
ln -s docs/guides/GUIDE.md mds/guides/GUIDE.md
# etc.
```

---

## Testing Checklist

After each phase:
- [ ] `make menu` works
- [ ] `make pdf` works
- [ ] `make test` passes
- [ ] All Makefile targets work
- [ ] Documentation builds
- [ ] No broken imports

---

## Timeline

- **Phase 1 (Docs)**: 30 minutes (SAFE)
- **Phase 2 (Scripts)**: 30 minutes (SAFE)
- **Phase 3 (Makefile)**: 30 minutes (test carefully)
- **Phase 4 (pyproject)**: 15 minutes (optional)

**Total**: 1-2 hours

---

## Risks & Mitigation

### Risk: Breaking imports
**Mitigation**: Do Phase 1 and 2 first (no imports affected)

### Risk: Breaking Makefile targets
**Mitigation**: Update and test one target at a time

### Risk: Users confused by new structure
**Mitigation**:
- Keep backwards compat symlinks
- Update README with new structure
- Add MIGRATION_GUIDE.md

---

## Decision Points

**Do you want to:**
1. ✅ Move docs → `docs/` (SAFE, recommended)
2. ✅ Move scripts → `scripts/` (SAFE, recommended)
3. ⏳ Create `src/proxy_machine/` (future, optional)
4. ⏳ Add `pyproject.toml` (modern, optional)

**I recommend:** Start with #1 and #2 (safe, high value)

---

**Ready to execute?** I can do Phase 1 and 2 right now!
