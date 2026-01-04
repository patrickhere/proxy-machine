# The Proxy Machine: Engineering Workflow

**Architecture and conventions for AI agents and contributors.** For user workflows, see `GUIDE.md`. For complete command reference, see `REFERENCE.md`.

---

## Recent Updates

See `CHANGELOG.md` for detailed session-by-session changes. Major updates:

- **2025-10-14**: Makefile cleanup, web scraper, file corruption recovery
- **2025-10-06**: Hobby features (artist search, random discovery, set exploration)
- **2025-10-03**: DFC land face detection, set folder normalization
- **2025-09-27**: Database schema v5, universal card fetching, multi-language support

---

## Repository Map (key paths)

- `proxy-machine/create_pdf.py` — main CLI + menu, PDF generation, token/land tools, bulk index, notifications. Refactored with helper utilities and constants module.
- `proxy-machine/constants.py` — shared constants (RARITIES, SPELL_TYPES, CARD_TYPES) for consistent user prompts and validation.
- `proxy-machine/db/bulk_index.py` — comprehensive database functions with 32-field schema and multi-language support:
  - `query_cards()` — universal card search with 15+ filter parameters
  - `query_basic_lands()` / `query_non_basic_lands()` — enhanced land queries with comprehensive filtering
  - `query_tokens()` — token search with metadata filtering
- `proxy-machine/assets/profiles.json` — profile definitions and path overrides.
- `proxy-machine/mds/GUIDE.md` — user quick-start guide.
- `proxy-machine/mds/REFERENCE.md` — complete command/API documentation.
- `proxy-machine/mds/IDEAS.md` — roadmap and planning.
- `proxy-machine/mds/CHANGELOG.md` — development history.
- `proxy-machine/Makefile` — curated commands for daily workflows.
- `proxy-machine/coverage.py` — land coverage report tool (outputs CSV/JSON under `magic-the-gathering/shared/reports/land-coverage/`).
- `proxy-machine/tools/optimize_images.py` — image optimizer used by `make optimize-images` (dry run by default; set `EXECUTE=1` to apply changes).
- `proxy-machine/coverage.py` — coverage reports for lands and tokens. Outputs CSV/JSON under `magic-the-gathering/shared/reports/<land-coverage|token-coverage>/` including per-set and missing-only CSVs.
- `proxy-machine/dashboard.py` — local web dashboard (HTML + JSON APIs). Phase 3 adds:
  - JSON: `/api/search`, `/api/unique_art`, `/api/unique_art/counts`, `/api/set`, `/api/rulings`, `/api/coverage`, `/coverage_csv`, `/api/db_info`, `/api/rules_delta`
  - HTML: `/coverage` (pagination + downloads), `/rules_delta`, `/admin/db_maintenance` (offline-safe by default)
- `magic-the-gathering/proxied-decks/<profile>/` — per-profile workspace (front/back/double_sided images, PDFs, deck-reports, etc.).
- `magic-the-gathering/shared/` — shared libraries:
  - `tokens/<tokentype>/` — type-based organization (e.g., `tokens/soldier/`, `tokens/zombie/`)
  - `basic-lands/<landtype>/` — type-based organization (e.g., `basic-lands/mono/plains/`, `basic-lands/colorless/wastes/`)
  - `non-basic-lands/<landtype>/` — type-based organization (e.g., `non-basic-lands/dual/`, `non-basic-lands/utility/legendary/`)
  - `card-backs/` — card back images
  - `bulk-data/` — Scryfall bulk JSON files and SQLite database
  - `token-packs/` — curated token collections
- `proxy-machine/config/notifications.json` — notification settings (macOS + webhook).
- `proxy-machine/tools/` — small CLIs for maintenance and search:
  - `tools/cards.py` (oracle/type search), `tools/ua.py` (unique artworks), `tools/db.py` (DB wrapper), `tools/verify.py` (workspace health), `tools/notify_test.py` (sample notification)

- `archived/profile-backups/` — zipped profile directories created when deleting a profile.
- `archived/proxy-printer-backups/` — git bundles and snapshot zips created by `make backup` and the pre-push hook.

## Operational Invariants

- PDF defaults (unless overridden):
  - `--card_size standard`
  - `--crop 3mm`
  - `--ppi 600`
  - `--quality 100`
- Output path per profile defaults to:
  - `magic-the-gathering/proxied-decks/<profile>/pdfs-of-decks/<profile>.pdf`
  - Resolved relative to the project root (not relative to images folder).

- Interactive PDF filename prompt (menu/TTY): requires letters/numbers/dashes (no spaces). Filename becomes `<name>.pdf` under the profile’s default `pdfs-of-decks/` folder. Use `--pdf_name <name>` in CLI to skip the prompt.
- No-overwrite safeguard: if the target PDF already exists, a unique timestamp suffix is appended automatically.
- Required profile directories created/maintained by the menu (Initialize Profiles):
  - `other/`
  - `deck-reports/`
  - `pdfs-of-decks/`
  - `pictures-of-cards/`
  - `pictures-of-cards/shared-cards/`
  - `pictures-of-cards/archived/`
  - `pictures-of-cards/misc-alt-arts/`
  - `pictures-of-cards/to-print/`
  - `pictures-of-cards/to-print/front/`
  - `pictures-of-cards/to-print/back/`
  - `pictures-of-cards/to-print/double_sided/`
- Profile symlinks under `pictures-of-cards/shared-cards/`:
  - `tokens -> magic-the-gathering/shared/tokens`
  - `card-backs -> magic-the-gathering/shared/card-backs`
  - `basic-lands -> magic-the-gathering/shared/basic-lands`
  - `non-basic-lands -> magic-the-gathering/shared/non-basic-lands`
- Preflight checks before PDF generation:
  - If fronts are not a multiple of 8, prompt to auto-pad with random shared tokens or pause for manual fix.
  - If backs are empty while single-sided fronts exist, prompt to copy a random shared back or pause for manual fix.
- Progress UX: Long-running tasks (bulk fetches) must update a single in-place status line periodically (every ~100 items) and print a final summary only — no per-file spam.
- Scryfall usage: Prefer cached bulk dumps (`all-cards` + `oracle-cards` + `unique-artwork`). API calls are rate-limited via the built-in limiter; image CDN downloads are decoupled and use a capped thread pool for polite parallelism.

---

## Database Management

The project uses a SQLite database built from Scryfall bulk data. Simple workflow:

**Commands:**
- `make bulk-fetch-all` — Download all bulk data files from Scryfall
- `make bulk-rebuild` — Rebuild database from bulk JSON files
- `make bulk-vacuum` — Optimize database (VACUUM + ANALYZE)
- `make bulk-verify` — Check database health
- `make bulk-sync` — All-in-one: fetch + rebuild + vacuum
- `make db-info` — Show database statistics

**Workflow:**
1. Initial setup or update: `make bulk-sync`
2. Check status: `make db-info`
3. Verify health: `make bulk-verify`

**No migrations needed:** Database rebuilds from source of truth (Scryfall). Schema changes = just rebuild.

---

## File Organization

**Tokens:** Type-based flat structure
```
tokens/<tokentype>/<filename>
Example: tokens/soldier/soldier-standard-en-ltr-015.png
```

**Lands:** Type-based structure (multi-level folders based on `_classify_land_type`)
```
basic-lands/<landtype>/<filename>
non-basic-lands/<landtype>/<filename>
Examples:
  basic-lands/mono/plains/plains-standard-en-ltr-260.png
  non-basic-lands/utility/legendary/yavimaya_hollow-fullart-en-usg-330.png
```

**Naming conventions:**
- Tokens: `<tokenname>-<arttype>-<lang>-<set>-<collector>.png`
- Lands: `<landname>-<arttype>-<lang>-<set>-<collector>.png`

**Rationale:**
- Tokens organized by type for easy browsing (all soldiers, all zombies, etc.)
- Lands organized by function (mono/dual/tri, utility, special) to group interchangeable prints regardless of set
- Library health: duplicate handling is non-destructive. Lower-priority perceptual duplicates are quarantined (archived) with actions recorded in the summary JSON. A dedicated restore flow is available via the menu.

## Profiles System

- Location: `proxy-machine/assets/profiles.json`.
- Purpose: Map profile names to directories and default output path. Values can be absolute or project-relative. Output paths are resolved relative to the project root.
- Minimal schema example:

  ```json
  {
    "profiles": {
      "patrick": {
        "base_directory": "magic-the-gathering/proxied-decks/patrick/pictures-of-cards/to-print",
        "front_dir": "front",
        "back_dir": "back",
        "double_sided_dir": "double_sided",
        "output_path": "magic-the-gathering/proxied-decks/patrick/pdfs-of-decks/patrick.pdf"
      }
    }
  }
  ```

- Shorthands: The CLI registers `--profile <name>` and also `--<name>` flags (e.g., `--patrick`). Shorthands appear after restart.
- Menu Option “Profiles”: Create, delete (with archive), and initialize profiles, and ensure symlinks/directories exist.

## Shared Libraries

- Tokens: `magic-the-gathering/shared/tokens/` with `_index.json` maintained by token tools.
- Card backs: `magic-the-gathering/shared/card-backs/`.
- Bulk data: `proxy-machine/bulk-data/` contains `all-cards.json.gz`, `oracle-cards.json.gz`, and SQLite database.

### Art Type Derivation System

The `_derive_art_type()` function (lines 6058-6147 in `create_pdf.py`) maps Scryfall metadata to a comprehensive art type taxonomy used in file naming.

**Priority Order (Primary Classification):**
1. **textless** - Highest priority (very distinctive)
2. **borderless** - `border_color == "borderless"`
3. **showcase** - `"showcase"` in `frame_effects`
4. **extended** - `"extendedart"` in `frame_effects`
5. **retro** - `frame == "1993"`
6. **fullart** - `full_art == True` or `"fullart"` in `frame_effects`
7. **standard** - Default fallback

**Modifiers (Applied After Primary):**
Modifiers are appended with hyphens in sorted order:
- **inverted** → `-oilslick` (for ONE/MOM/MAT sets) or `-inverted` (other sets)
- **etched** → `-etched`
- **glossy** → `-glossy`
- **gilded** → `-gilded`
- **serialized** → `-serialized`
- **acorn** → `-acorn` (UNF set only)
- **universesbeyond** → `-ub`
- **booster/boosterfun** → `-booster`
- **concept** → `-concept`
- **thick** → `-thick`

**Examples:**
- `borderless-inverted` → `borderless-inverted` (generic set)
- `borderless-inverted` → `borderless-oilslick` (ONE/MOM/MAT sets)
- `showcase-etched-gilded` → `showcase-etched-gilded` (sorted modifiers)
- `fullart` → `fullart` (no modifiers)

**Usage:** This function is called by all naming functions (`_land_base_stem`, `_token_base_stem`, `_card_base_stem`) to ensure consistent art type classification across the entire collection.

## Menu and CLI Surface

**Interactive Menu** (`make menu`):
- Deck Tools - PDF generation, deck analysis
- Tokens - Search, fetch, pack builder
- Profiles - Create/delete, initialize folders
- Maintenance - Health checks, coverage reports
- Plugins - Enable/disable parsers

**Make Commands**: See `REFERENCE.md` for complete list. Key commands:
- `make setup` - First-time environment setup
- `make pdf PROFILE=name` - Generate PDF
- `make fetch-basics` / `make fetch-nonbasics` - Fetch lands
- `make fetch-tokens` - Fetch tokens
- `make deck-report DECK=path` - Analyze deck
- `make bulk-sync` - Update all bulk data
- `make library-health` - Audit shared libraries

**CLI Flags**: See `REFERENCE.md` for complete list. Run `uv run python create_pdf.py --help` for inline help.

## Notifications

- Config file: `proxy-machine/config/notifications.json` (auto-created with sensible defaults).
- Channels:
  - macOS Notification Center via AppleScript.
  - Webhook POST with `{title, message, event, timestamp}` payload.
- Toggle via `make notifications-config` or corresponding CLI/menu entry.
- Smoke test via `uv run python create_pdf.py --notifications_test`.

## Logging Modes

Environment variable `PM_LOG` controls common logging modes:

- `PM_LOG=json` — prefer JSON output for auxiliary tools where supported (`tools/cards.py`, `tools/ua.py`).
- `PM_LOG=quiet` — reduce non-essential output (equivalent to `--quiet` where available).
- `PM_LOG=verbose` — increase verbosity (equivalent to `--verbose`).

Many CLI surfaces also expose `--quiet` / `--verbose` flags (e.g., `create_pdf.py`, `tools/cards.py`, `tools/ua.py`).

## Engineering Conventions

- Python

  - Use type hints throughout.
  - Follow PEP 8.
  - Prefer readability over premature optimization.
  - Keep imports at the top of files; never insert imports mid-file.
  - Structure code modularly (helpers at the top of `create_pdf.py` are grouped by concern; keep new utilities cohesive and testable).

- Environment

  - Use `uv` for dependency management (`make deps`).
  - Add/lock dependencies in `requirements.txt` (installed via `uv pip install -r requirements.txt`).

- Contribution hygiene

  - Update docs when adding features:
    - `GUIDE.md` - User-facing workflows
    - `REFERENCE.md` - Command/API documentation
    - `WORKFLOW.md` - Engineering conventions
    - `IDEAS.md` - Roadmap adjustments
    - `CHANGELOG.md` - Session notes
  - Keep console output clean. For long tasks, use in-place single-line progress and a final summary.
  - Respect Scryfall rate limiting. Prefer cached bulk over live API calls.
  - When changing CLI flags or defaults, also update `Makefile` and `REFERENCE.md`.
  - If adding DB-backed helpers, ensure JSON-index fallbacks remain intact.
  - File-producing flows should call `_offer_open_in_folder(path, kind=...)` to prompt opening the containing folder in Finder.
  - PDF naming: prefer the interactive legal-name prompt or the `--pdf_name` flag; never overwrite an existing PDF (timestamp suffix is required if a collision occurs).
  - Tests: add small sanity checks where possible; include descriptive logging around tricky flows.
  - Pre-commit: ensure linters/formatters run cleanly if configured.
- Linting & static checks
  - Run `uv run pyright` before submitting changes; all plugin deck parsers and helpers now export precise types.
  - `pyrightconfig.json` excludes heavy data directories (including `**/—python/**` vendored site-packages) to keep analysis focused on project code. Extend this list if new third-party bundles are added.

### Editor/Indexer Tips

- For large workspaces in Windsurf/VS Code, add a `pyrightconfig.json` at repo root to exclude heavy non-code directories from analysis, e.g.:

  ```json
  {
    "exclude": [
      "**/.git/**", "**/.venv/**", "**/node_modules/**",
      "**/magic-the-gathering/**", "**/archived/**", "**/assets/**"
    ]
  }
  ```

  This avoids slow file enumeration and reduces background CPU.

## Typical Agent Playbooks

- Add a new CLI feature
  1. Identify surface (menu item, CLI flag, and/or Make target).
  2. Implement helpers near related utilities in `create_pdf.py`.
  3. Wire flag(s) into Click/CLI and menu flow.
  4. Add/adjust `Makefile` targets.
  5. Update `REFERENCE.md` (command docs), `GUIDE.md` (if user-facing), `WORKFLOW.md` (if architectural).
  6. If future work remains, update `IDEAS.md`.
  7. Add session notes to `CHANGELOG.md`.
  8. Manually validate via `make ...` and through the menu; ensure console UX matches the single-line progress rule.

- Add post-deck-report PDF generation
  1. After writing `deck_summary.json` and CSV, prompt the user (interactive only) to generate a PDF if a profile was provided.
  2. Create deck-named subfolders under the profile: `front/<deck-slug>/`, `back/<deck-slug>/`, `double_sided/<deck-slug>/`.
  3. Fetch any missing card fronts into `front/<deck-slug>/` using Scryfall image URLs derived from the cached bulk index (no per-card API calls).
  4. Invoke the standard PDF generation path with the interactive filename prompt and no-overwrite safeguard.

- Add a shared library routine (e.g., new asset sync)
  1. Reuse the bulk index filtering pattern (see land fetchers).
  2. Save assets under `magic-the-gathering/shared/<library>/<set>/` with `name_collector.png` naming.
  3. Add profile symlink under `pictures-of-cards/shared-cards/` if needed.
  4. Add Make target + CLI flag; ensure idempotency and summaries.
  5. Document and test.

- Debug profile path issues
  1. Verify `profiles.json` values; prefer project-relative paths.
  2. Confirm output resolution is relative to project root (not the images folder).
  3. Use the menu’s Initialize action to recreate folders/symlinks.
  4. Generate PDF and check the exact printed “PDF created at …” path.

## Troubleshooting Playbooks

- “No matches” for token or card searches
  - Force a bulk rebuild so oracle data is attached: run `make fetch-basics` once (downloads `all-cards`, `oracle-cards`, and `unique-artwork` then rebuilds the index), or delete `bulk-data/*_index.json` and rebuild.
- Bulk fetch “stalls” on a line
  - This is expected when the worker queue is large. The process updates a single status line every 100 items and prints a final summary. Use Activity Monitor or `ps` to confirm it’s running.
- PDF count/back checks block progress
  - Follow prompts to auto-fill/pause; these guards protect print layout integrity.
- iTerm launcher does nothing
  - Check iterm2 Python scripting permissions and that `uv` is on PATH. Script path: `~/Library/Application Support/iTerm2/Scripts/LaunchProxyMachine.py`.

## Documentation Policy

- Any non-trivial change should update:
  - `mds/GUIDE.md` for end-user tasks and commands.
  - `mds/REFERENCE.md` for command/API documentation.
  - `mds/WORKFLOW.md` for engineering guidance.
  - `mds/IDEAS.md` to remove completed items and add new proposals.
  - `mds/CHANGELOG.md` with session notes and highlights.

## Portability & Path Resolution

- All paths are resolved relative to the project root at runtime. Key anchors:
  - `script_directory = os.path.dirname(os.path.abspath(__file__))`
  - `project_root_directory = os.path.dirname(script_directory)` (i.e., the parent of `proxy-machine/`)
- Do not introduce absolute paths (e.g., `/Users/...`). When accepting user-provided paths, resolve with `resolve_path(path, base_directory=project_root_directory)`.
- Archives and caches are kept under the repo (see below) so the folder can be moved to another machine without path edits.
- macOS notifications use AppleScript; they are optional and no-op on other platforms.
- Dependencies are installed via `uv` from `requirements.txt`. No global Python assumptions beyond having `uv` available.

## Handoff Checklist (for new humans or AI agents)

1. Install dependencies: `cd proxy-machine && make deps`
2. Run the menu: `make menu` and validate basic flows (Profiles → Initialize; Deck Tools → Generate PDF)
3. If new, configure notifications (optional): `make notifications-config`
4. Run a small workflow end-to-end:
   - Create a test profile, initialize, place a couple of images, generate a PDF
5. Validate backups work: `make backup` and confirm artifacts under `archived/proxy-printer-backups/`
6. Validate core reports/health checks:
   - `make optimize-images DRY_RUN=1`
   - `make token-language-report WARN=ph,ja`
   - `make land-coverage TYPE=all`
7. Read this file (`WORKFLOW.md`) and `GUIDE.md` to understand invariants and user flows
8. When adding features, follow the Playbooks below and update docs in the same PR

## Backups & Archives

- Manual backup: `make backup` writes a git bundle and snapshot zip to `archived/proxy-printer-backups/` (project root).
- Pre-push hook mirrors the same behavior and prunes older bundles (keeps last 10).
- Profile deletions archive the profile directory to `archived/profile-backups/<name>-<date>.zip`.
- Migration: `make migrate-archives` moves older `proxy-machine/archived/{git-backups,snapshots}` into `archived/proxy-printer-backups/` if present.

## Acceptance Checklist for PDF Generation

- Uses defaults unless overridden (standard, 3mm, 600 ppi, quality 100).
- Output lands in the profile’s `pdfs-of-decks/` folder.
- Fronts are a multiple of 8 (auto-padded or confirmed).
- Backs present for single-sided fronts, or user accepted a shared back.
- Final console message: `PDF created at <path>.`

## Glossary

- “Profile” — a per-user workspace with dedicated image folders and outputs.
- “Shared library” — common assets (tokens, card backs, lands) symlinked into profiles.
- “Bulk index” — offline merged dataset from Scryfall `all-cards`, `oracle-cards`, and `unique-artwork` to power searches and asset fetchers.
- “SQLite bulk index” — a materialized subset of the bulk index persisted in `bulk.db` for faster search; optional and automatically used when present.

## Plugins

- Discovery: subdirectories under `proxy-machine/plugins/` with `__init__.py` exporting a `PLUGIN` metadata dict are considered local plugins.
- Management: via Menu → Plugins, or CLI shims `--plugins_list`, `--plugins_enable <name>`, `--plugins_disable <name>`, or Make targets `plugins-*`.
- State: persisted in `proxy-machine/config/plugins.json`.

---
If anything in this workflow becomes outdated as features evolve, please update this file in the same PR as the related changes.
