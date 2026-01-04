SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables
.DEFAULT_GOAL := help

UV ?= uv
PYTHON_VERSION ?= 3.11
# Require uv and route all Python through uv (pin runtime to PYTHON_VERSION)
export PATH := $(HOME)/.local/bin:$(PATH)
UV_BIN := $(shell command -v $(UV) 2>/dev/null)
ifndef UV_BIN
  $(error "uv not found. Install: https://github.com/astral-sh/uv")
endif
# Use uv pip for dependency installation; use uv run for execution (same environment)
VENV_DIR := .venv
PIP := $(UV_BIN) pip
PYRUN := $(UV_BIN) run --with-requirements requirements.txt --python 3.12
BACKUPS ?= 10
PM_SCRIPT := src/create_pdf.py
REQ_FILE := requirements.txt

# Optional variables - define defaults to suppress warnings
TYPE ?=
NAME ?=
SUBTYPE ?=
SET ?=
ARTIST ?=
RARITY ?=
COLORS ?=
LANGS ?=
FULLART ?=
LIMIT ?=
DRY ?=
RETRY ?=
NO_TOKENS ?=
NO_LANDS ?=
LANG ?=
LAYOUT ?=
FRAME ?=
UV_PIP_FLAGS ?=
DECK ?=

# Non-parallel targets that mutate DB/cache or rely on shared resources
.NOTPARALLEL: db-upgrade db-downgrade bulk-index-build bulk-index-rebuild bulk-index-refresh bulk-sync benchmark benchmark-compare backup migrate-archives

.PHONY: \
	help \
	help-full \
	setup \
	status \
	clean \
	test \
	verify-docs \
	test-plugins \
	test-schema \
	test-integration \
	test-ai-recommendations \
	benchmark \
	benchmark-compare \
	query-relationships \
	bulk-audit \
	collection-report \
	profile-stats \
	shared-sync \
	set-check \
	token-sync \
	search \
	search-save \
	search-list \
	test-new-features \
	generate-docs \
	generate-coverage-badge \
	pdf-batch \
	db-version \
	db-history \
	db-upgrade \
	db-downgrade \
	db-migrate \
	populate-token-relationships \
	detect-duplicates-scan \
	detect-duplicates-find \
	score-image-quality \
	venv \
	deps \
	deps-offline \
	menu \
	pdf \
	fetch-basics \
	fetch-nonbasics \
	fetch-by-arttype \
	preview-lands \
	tokens-list \
	tokens-explorer \
	deck-report \
	tokens-keyword \
	token-language-report \
	fetch-tokens \
	cards-search \
	notifications-config \
	dashboard \
	ua-cli \
	verify \
	land-coverage \
	hooks-install \
	precommit-install \
	precommit-run \
	backup \
	migrate-archives \
	library-health \
	random-commander \
	token-pack-from-deck \
	bulk-index-build \
	bulk-index-rebuild \
	bulk-index-vacuum \
	bulk-index-info \
	bulk-fetch-allcards \
	bulk-fetch-oracle \
	bulk-fetch-unique \
	bulk-fetch-all \
	bulk-index-refresh \
	bulk-sync \
	plugins-list \
	plugins-enable \
	plugins-disable \
	plugins-new \
	plugins-list-json \
	rules-delta \
	optimize-images \
	system-memory \
	memory-test \
	discord-test \
	discord-stats \
	discord-daily \
	discord-alert \
	discord \
	dedupe-images \
	fetch-cards \
	scrape-art \
	db-optimize \
	db-info \
	artist-search \
	random-cards \
	explore-set \
	progress-demo \
	sync-tokens \
	sync-lands \
	list-profiles \
	ci

help:
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "           Proxy Printer - Quick Reference"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "TESTING & VALIDATION"
	@echo "  make test                        Quick syntax check"
	@echo "  make verify-docs                 Check documentation consistency"
	@echo "  make test-plugins                Run plugin regression tests"
	@echo "  make test-schema                 Validate database schema"
	@echo "  make test-integration            Run integration tests with pytest"
	@echo "  make test-ai-recommendations     Test all AI recommendation features"
	@echo "  make test-new-features           Test Phase 1-3 features"
	@echo ""
	@echo "FETCH ASSETS"
	@echo "  make fetch-basics                [LANG=en,ph] [SET=ltr] [RETRY=1]"
	@echo "  make fetch-nonbasics             [LANG=en] [SET=ltr]"
	@echo "  make fetch-tokens                [LANGS=en] [SUBTYPE=Spirit]"
	@echo "  make fetch-cards                 [TYPE=creature] [RARITY=rare] [SET=znr]"
	@echo "  make scrape-art                  URL=https://... [PAGES=10]"
	@echo ""
	@echo "GENERATE PDFS"
	@echo "  make pdf                         PROFILE=name [DECK=deckname]"
	@echo "  make deck-report                 DECK=path/to/list.txt"
	@echo ""
	@echo "PROFILES & COLLECTIONS"
	@echo "  make list-decks                  PROFILE=name - List deck subfolders"
	@echo "  make create-deck                 PROFILE=name DECK=deckname - Create deck subfolder"
	@echo "  make profile-stats               PROFILE=name - View statistics"
	@echo "  make shared-sync                 PROFILE=name - Sync shared library"
	@echo ""
	@echo "DATABASE & MIGRATIONS"
	@echo "  make db-version                  Check current schema version"
	@echo "  make db-history                  Show migration history"
	@echo "  make db-upgrade                  Upgrade to latest schema"
	@echo "  make db-downgrade                Downgrade one version"
	@echo "  make db-migrate                  MESSAGE='description'"
	@echo "  make db-optimize                 Optimize database performance"
	@echo ""
	@echo "SEARCH & EXPLORE"
	@echo "  make cards-search                QUERY=\"flying\" [SET=mh3]"
	@echo "  make artist-search               ARTIST=\"Rebecca Guay\""
	@echo "  make explore-set                 SET=ltr [TYPE=creature]"
	@echo "  make random-cards                [COUNT=5]"
	@echo "  make search                      QUERY='text' - Advanced search"
	@echo ""
	@echo "MAINTENANCE & AUTOMATION"
	@echo "  make doctor                      Run system health diagnostics"
	@echo "  make library-health              [FIX_NAMES=1] [FIX_DUPES=1]"
	@echo "  make bulk-sync                   Update all bulk data"
	@echo "  make backup                      Create backup"
	@echo "  make clean                       Remove temp files"
	@echo "  make set-check                   Check for new set releases"
	@echo "  make token-sync                  Sync token coverage"
	@echo "  make land-coverage               [TYPE=basic] [MISSING=1]"
	@echo "  make discord-stats               Send stats to Discord"
	@echo ""
	@echo "DOCUMENTATION"
	@echo "  make generate-docs               Generate CLI and schema docs"
	@echo ""
	@echo "────────────────────────────────────────────────────────────────"
	@echo "  make help-full                   Show all available commands"
	@echo "────────────────────────────────────────────────────────────────"
	@echo ""

help-full:
	@echo "All Available Commands:"
	@echo ""
	@echo "Core workflows:"
	@echo "  make menu                # Launch interactive menu"
	@echo "  make pdf PROFILE=name    # Generate profile PDF"
	@echo "  make deck-report DECK=path [PROFILE=...]"
	@echo "  make random-commander [COLORS=wu] [TYPE=human,wizard]"
	@echo ""
	@echo "Land & token tools:"
	@echo "  make fetch-basics [LANG=en,ph] [SET=ltr] [DRY=1]"
	@echo "  make fetch-nonbasics [LANG=en,ph] [SET=ltr] [DRY=1]"
	@echo "  make fetch-tokens [LANGS=en] [SET=mh3] [SUBTYPE=Spirit] [DRY=1]"
	@echo "  make tokens-list [FILTER=Spirit] [SETCODE=mh3] [LIMIT=25]"
	@echo "  make tokens-keyword KEYWORD=flying [SET=mh3]"
	@echo "  make token-language-report [WARN=ph,ja] [JSON=1]"
	@echo "  make token-pack-from-deck DECK=path|url [NAME=packname]"
	@echo "  make tokens-explorer"
	@echo ""
	@echo "Maintenance & automation:"
	@echo "  make library-health [FIX_NAMES=1] [FIX_DUPES=1] [HASH=6]"
	@echo "  make optimize-images [EXECUTE=1]"
	@echo "  make dedupe-images"
	@echo "  make land-coverage TYPE=basic|nonbasic|all|tokens [MISSING=1] [OPEN=1]"
	@echo "  make notifications-config"
	@echo "  make discord-stats             # Send collection stats"
	@echo "  make discord-daily             # Send daily summary"
	@echo "  make discord-alert MSG=..."
	@echo "  make backup"
	@echo "  make migrate-archives"
	@echo ""
	@echo "Database & search:"
	@echo "  make bulk-index-refresh"
	@echo "  make bulk-index-info"
	@echo "  make db-optimize"
	@echo "  make db-info"
	@echo "  make cards-search QUERY=... [SET=...] [LIMIT=...] [INCLUDE=1]"
	@echo ""
	@echo "Web & plugins:"
	@echo "  make dashboard            # Run local dashboard"
	@echo "  make plugins-list         # List plugins"
	@echo "  make plugins-enable NAME=x"
	@echo "  make plugins-disable NAME=x"
	@echo ""
	@echo "Setup & utilities:"
	@echo "  make venv                # Create Python venv via uv"
	@echo "  make deps                # Install dependencies"
	@echo "  make deps-offline        # Install from uv cache only"
	@echo "  make progress-demo       # Demo progress bars"
	@echo "  make list-profiles       # List configured profiles"

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment with uv..."; \
		$(UV_BIN) venv $(VENV_DIR) --python $(PYTHON_VERSION); \
	fi

deps: venv
	@if [ "$$PM_OFFLINE" = "1" ] || [ "$$PM_OFFLINE" = "true" ] || [ "$$PM_OFFLINE" = "yes" ] || [ "$$PM_OFFLINE" = "on" ]; then \
		echo "Offline mode: skipping dependency install"; \
	else \
		$(PIP) install -r $(REQ_FILE) $(UV_PIP_FLAGS); \
	fi

deps-offline:
	$(PIP) install --no-index -r $(REQ_FILE)

menu: deps
	$(PYRUN) $(PM_SCRIPT)

pdf: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "PROFILE is required. Usage: make pdf PROFILE=patrick [DECK=deckname]"; \
		exit 1; \
	fi
	$(PYRUN) $(PM_SCRIPT) --profile "$(PROFILE)" $(if $(DECK),--deck "$(DECK)",)

list-decks: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "PROFILE is required. Usage: make list-decks PROFILE=patrick"; \
		exit 1; \
	fi
	$(PYRUN) $(PM_SCRIPT) --profile "$(PROFILE)" --list_decks

create-deck: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "PROFILE is required. Usage: make create-deck PROFILE=patrick DECK=deckname"; \
		exit 1; \
	fi
	@if [ -z "$(DECK)" ]; then \
		echo "DECK is required. Usage: make create-deck PROFILE=patrick DECK=deckname"; \
		exit 1; \
	fi
	$(PYRUN) $(PM_SCRIPT) --profile "$(PROFILE)" --create_deck "$(DECK)"

fetch-basics: deps
	$(PYRUN) $(PM_SCRIPT) --fetch_basics $(if $(LANG),--lang "$(LANG)",) $(if $(SET),--land_set "$(SET)",) $(if $(FULLART),--fullart_only,) $(if $(DRY),--fetch_dry_run,) $(if $(RETRY),--retry_only,)

fetch-nonbasics: deps
	$(PYRUN) $(PM_SCRIPT) --fetch_non_basics $(if $(LANG),--lang "$(LANG)",) $(if $(SET),--land_set "$(SET)",) $(if $(FULLART),--fullart_only,) $(if $(DRY),--fetch_dry_run,) $(if $(RETRY),--retry_only,)

fetch-cards: deps
	$(PYRUN) $(PM_SCRIPT) --fetch_cards \
		$(if $(TYPE),--card_type "$(TYPE)",) \
		$(if $(NAME),--card_name "$(NAME)",) \
		$(if $(LANG),--lang "$(LANG)",) \
		$(if $(SET),--land_set "$(SET)",) \
		$(if $(FULLART),--fullart_only,) \
		$(if $(LIMIT),--card_limit $(LIMIT),) \
		$(if $(NO_TOKENS),--exclude_tokens,) \
		$(if $(NO_LANDS),--exclude_lands,) \
		$(if $(DRY),--fetch_dry_run,) \
		$(if $(RETRY),--retry_only,)

fetch-tokens: deps
	$(PYRUN) $(PM_SCRIPT) --fetch_tokens_clean \
		$(if $(SUBTYPE),--token_subtype "$(SUBTYPE)",) \
		$(if $(SET),--land_set "$(SET)",) \
		$(if $(LANGS),--lang "$(LANGS)",) \
		$(if $(LIMIT),--card_limit $(LIMIT),) \
		$(if $(DRY),--fetch_dry_run,)

tokens-list: deps
	$(PYRUN) $(PM_SCRIPT) --list_tokens $(if $(FILTER),--token_filter "$(FILTER)",) $(if $(SUBTYPE),--token_subtype "$(SUBTYPE)",) $(if $(SETCODE),--token_set "$(SETCODE)",) $(if $(COLORS),--token_colors "$(COLORS)",) $(if $(LIMIT),--token_limit $(LIMIT),)

tokens-explorer: deps
	$(PYRUN) $(PM_SCRIPT) --token_explorer

deck-report: deps
	@if [ -z "$(DECK)" ]; then \
		echo "DECK is required. Usage: make deck-report DECK=path/to/list.txt"; \
		exit 1; \
	fi
	$(PYRUN) $(PM_SCRIPT) --deck_list "$(DECK)" $(if $(NAME),--deck_name "$(NAME)",) $(if $(OUT),--deck_output_dir "$(OUT)",) $(if $(PROFILE),--profile "$(PROFILE)",)

tokens-keyword: deps
	@if [ -z "$(KEYWORD)" ]; then \
		echo "KEYWORD is required. Usage: make tokens-keyword KEYWORD=flying"; \
		exit 1; \
	fi
	$(PYRUN) $(PM_SCRIPT) --token_keyword "$(KEYWORD)" $(if $(SET),--token_keyword_set "$(SET)",) $(if $(LIMIT),--token_keyword_limit $(LIMIT),)

token-language-report: deps
	$(PYRUN) $(PM_SCRIPT) --token_language_report $(if $(WARN),--token_language_warn "$(WARN)",) $(if $(JSON),--json,)

cards-search: deps
	@if [ -z "$(QUERY)" ]; then \
		echo "QUERY is required. Usage: make cards-search QUERY=\"enter the battlefield\""; \
		exit 1; \
	fi
	$(PYRUN) $(PM_SCRIPT) --card_search "$(QUERY)" $(if $(SET),--card_search_set "$(SET)",) $(if $(LIMIT),--card_search_limit $(LIMIT),) $(if $(INCLUDE),--card_include_tokens,)

notifications-config: deps
	$(PYRUN) $(PM_SCRIPT) --configure_notifications

dashboard: deps
	$(PYRUN) src/dashboard.py --host 0.0.0.0 --port 5001

ua-cli: deps
	$(PYRUN) tools/ua.py $(if $(NAME),--name "$(NAME)",) $(if $(ORACLE),--oracle-id $(ORACLE),) $(if $(ILLUSTRATION),--illustration-id $(ILLUSTRATION),) $(if $(SET),--set $(SET),) $(if $(ARTIST),--artist "$(ARTIST)",) $(if $(FRAME),--frame $(FRAME),) $(if $(EFFECT),--effect $(EFFECT),) $(if $(FULLART),--full-art $(FULLART),) $(if $(LIMIT),--limit $(LIMIT),) $(if $(COUNTS),--counts,) $(if $(JSON),--json,)

verify: deps
	$(PYRUN) tools/verify.py $(if $(JSON),--json,) $(if $(MIN_GB),--min-disk-gb $(MIN_GB),)

doctor: deps
	$(PYRUN) tools/doctor.py

land-coverage: deps
	$(PYRUN) scripts/analysis/coverage.py $(if $(TYPE),--type "$(TYPE)",) $(if $(SET),--set "$(SET)",) $(if $(OUT),--out "$(OUT)",) $(if $(MISSING),--missing-only,) $(if $(OPEN),--open,)

hooks-install:
	@git config core.hooksPath .githooks
	@chmod +x .githooks/* 2>/dev/null || true
	@PARENT=$$(cd .. && pwd); \
	mkdir -p "$$PARENT/archived/proxy-printer-backups" "$$PARENT/archived/profile-backups"; \
	echo "Installed .githooks and prepared $$PARENT/archived/{proxy-printer-backups,profile-backups}."

precommit-install:
	@# If core.hooksPath is set, we skip 'pre-commit install' to avoid its warning.
	@HOOKS_PATH=$$(git config --get core.hooksPath || true); \
	if [ -n "$$HOOKS_PATH" ]; then \
		echo "core.hooksPath is set to '$$HOOKS_PATH' — skipping 'pre-commit install'."; \
		echo "The .githooks/pre-commit shim will run pre-commit automatically if available."; \
		echo "Tip: run 'make precommit-run' to execute checks now."; \
	else \
		if command -v uvx >/dev/null 2>&1; then \
			uvx pre-commit install; \
			echo "pre-commit hooks installed via uvx."; \
		elif command -v $(UV) >/dev/null 2>&1; then \
			$(UV) run pre-commit install || echo "pre-commit not found in env. Try: uvx pre-commit install"; \
		else \
			if command -v pre-commit >/dev/null 2>&1; then \
				pre-commit install; \
				echo "pre-commit hooks installed (system)."; \
			else \
				echo "pre-commit not installed. Try 'make precommit-install'"; \
			fi; \
		fi; \
	fi

precommit-run:
	@# Run pre-commit across the repo using available tool
	@if command -v uvx >/dev/null 2>&1; then \
		uvx pre-commit run --all-files; \
	elif command -v $(UV) >/dev/null 2>&1; then \
		$(UV) run pre-commit run --all-files; \
	elif command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files; \
	else \
		echo "pre-commit not installed. Try 'make precommit-install'"; \
	fi

backup:
	@PARENT=$$(cd .. && pwd); \
	BACKUP_DIR="$$PARENT/archived/proxy-printer-backups"; \
	mkdir -p "$$BACKUP_DIR"; \
	STAMP=$$(date +%Y%m%d_%H%M%S); \
	BUNDLE="$$BACKUP_DIR/backup_$${STAMP}.bundle"; \
	if git rev-parse --verify HEAD >/dev/null 2>&1; then \
		git bundle create "$$BUNDLE" --all || true; \
		echo "Wrote $$BUNDLE"; \
	else \
		echo "No commits yet; skipping bundle."; \
	fi; \
	ZIP="$$BACKUP_DIR/snapshot_$${STAMP}.zip"; \
	ITEMS="mds assets Makefile create_pdf.py scripts/analysis/coverage.py config"; \
	EXISTING=""; \
	for p in $$ITEMS; do \
		if [ -e "$$p" ]; then EXISTING="$$EXISTING $$p"; fi; \
	done; \
	if [ -n "$$EXISTING" ]; then \
		zip -rq "$$ZIP" $$EXISTING; \
		echo "Wrote $$ZIP"; \
	else \
		echo "No snapshot contents found; skipping zip."; \
	fi; \
	# Prune old git bundles by count (keep newest $(BACKUPS)) \
	COUNT=$$(printf '%d' "$(BACKUPS)" 2>/dev/null || echo 10); \
	ls -1t "$$BACKUP_DIR"/backup_*.bundle 2>/dev/null | tail -n +$$((COUNT+1)) | xargs -I {} rm -f {} || true; \
	# Prune old snapshot zips by count (keep newest $(BACKUPS)) \
	ls -1t "$$BACKUP_DIR"/snapshot_*.zip 2>/dev/null | tail -n +$$((COUNT+1)) | xargs -I {} rm -f {} || true

migrate-archives:
	@PARENT=$$(cd .. && pwd); \
	SRC_ROOT="archived"; \
	DEST_BACKUPS="$$PARENT/archived/proxy-printer-backups"; \
	mkdir -p "$$DEST_BACKUPS"; \
	MOVED=0; \
	# Move old git bundles if present \
	if [ -d "$$SRC_ROOT/git-backups" ]; then \
		for f in "$$SRC_ROOT/git-backups"/backup_*.bundle; do \
			[ -e "$$f" ] || continue; \
			mv "$$f" "$$DEST_BACKUPS"/; \
			MOVED=1; \
		done; \
	fi; \
	# Move old snapshot zips if present \
	if [ -d "$$SRC_ROOT/snapshots" ]; then \
		for z in "$$SRC_ROOT/snapshots"/snapshot_*.zip; do \
			[ -e "$$z" ] || continue; \
			mv "$$z" "$$DEST_BACKUPS"/; \
			MOVED=1; \
		done; \
	fi; \
	# Cleanup empty source dirs \
	rmdir "$$SRC_ROOT/git-backups" 2>/dev/null || true; \
	rmdir "$$SRC_ROOT/snapshots" 2>/dev/null || true; \
	rmdir "$$SRC_ROOT" 2>/dev/null || true; \
	if [ "$$MOVED" = "1" ]; then \
		echo "Migrated archives into $$DEST_BACKUPS"; \
	else \
		echo "No archives to migrate."; \
	fi

library-health: deps
	$(PYRUN) create_pdf.py --library_health $(if $(FIX_NAMES),--library_health_fix_names,) $(if $(FIX_DUPES),--library_health_fix_dupes,) $(if $(HASH),--library_health_hash_threshold $(HASH),)

random-commander: deps
	$(PYRUN) create_pdf.py --random_commander $(if $(COLORS),--rc_colors "$(COLORS)",$(if $(COLOR),--rc_colors "$(COLOR)",)) $(if $(filter 0 no false,$(EXACT)),--no-rc_exact,) $(if $(filter 0 no false,$(LEGAL)),--no-rc_commander_legal,) $(if $(TYPE),--rc_type "$(TYPE)",)

token-pack-from-deck: deps
	@if [ -z "$(DECK)" ]; then \
		echo "DECK is required. Usage: make token-pack-from-deck DECK=path/or/url [NAME=packname]"; \
		exit 1; \
	fi
	$(PYRUN) create_pdf.py --token_pack_from_deck "$(DECK)" $(if $(NAME),--token_pack_wizard_name "$(NAME)",)

# --- Bulk index (SQLite) tools ---
bulk-index-build: deps
	$(PYRUN) db/bulk_index.py build

bulk-index-rebuild: deps
	$(PYRUN) db/bulk_index.py rebuild

bulk-index-vacuum: deps
	$(PYRUN) db/bulk_index.py vacuum

bulk-index-info: deps
	$(PYRUN) db/bulk_index.py info

# --- Database Migrations (Alembic) ---
# Point Alembic at a config path so local/CI can override via ALEMBIC_CONFIG
export ALEMBIC_CONFIG ?= db/migrations/alembic.ini

db-version: deps
	@echo "Checking database schema version..."
	$(PYRUN) -m alembic -c $(ALEMBIC_CONFIG) current

db-history: deps
	@echo "Showing migration history..."
	$(PYRUN) -m alembic -c $(ALEMBIC_CONFIG) history --verbose

db-upgrade: deps
	@echo "Upgrading database to latest version..."
	$(PYRUN) -m alembic -c $(ALEMBIC_CONFIG) upgrade head

db-downgrade: deps
	@echo "Downgrading database one version..."
	$(PYRUN) -m alembic -c $(ALEMBIC_CONFIG) downgrade -1

db-migrate: deps
	@echo "Creating new migration: $(MESSAGE)"
	$(PYRUN) -m alembic -c $(ALEMBIC_CONFIG) revision -m "$(MESSAGE)"

bulk-update-incremental: deps
	@echo "Checking for incremental updates..."
	$(PYRUN) tools/incremental_update.py --type all

bulk-check-updates: deps
	@echo "Checking for updates (no download)..."
	$(PYRUN) tools/incremental_update.py --type all --check-only

# --- Bulk JSON fetchers (no deps; standard library only) ---
bulk-fetch-allcards:
	$(PYRUN) tools/fetch_bulk.py --id all-cards

bulk-fetch-oracle:
	$(PYRUN) tools/fetch_bulk.py --id oracle-cards

bulk-fetch-unique:
	$(PYRUN) tools/fetch_bulk.py --id unique-artwork

bulk-fetch-all: bulk-fetch-allcards bulk-fetch-oracle bulk-fetch-unique

bulk-index-refresh: bulk-fetch-all
	$(PYRUN) db/bulk_index.py rebuild
	$(PYRUN) db/bulk_index.py vacuum

# --- Plugin manager ---
plugins-list: deps
	$(PYRUN) plugins/plugin_manager.py list

plugins-enable: deps
	@if [ -z "$(NAME)" ]; then \
		echo "NAME is required. Usage: make plugins-enable NAME=plugin_name"; \
		exit 1; \
	fi
	$(PYRUN) plugins/plugin_manager.py enable "$(NAME)"

plugins-disable: deps
	@if [ -z "$(NAME)" ]; then \
		echo "NAME is required. Usage: make plugins-disable NAME=plugin_name"; \
		exit 1; \
	fi
	$(PYRUN) plugins/plugin_manager.py disable "$(NAME)"

plugins-new: deps
	@if [ -z "$(NAME)" ]; then \
		echo "NAME is required. Usage: make plugins-new NAME=plugin_name"; \
		exit 1; \
	fi
	$(PYRUN) plugins/plugin_manager.py new "$(NAME)"

plugins-list-json: deps
	$(PYRUN) plugins/plugin_manager.py list --json

# --- Medium Priority utilities ---
rules-delta: deps
	$(PYRUN) scripts/analysis/rules_delta.py

optimize-images: deps
	$(UV_BIN) run python scripts/maintenance/optimize_images.py $(if $(DIRECTORY),--directory "$(DIRECTORY)",) $(if $(NO_BACKUP),--no-backup,) $(if $(DRY_RUN),--dry-run,)

# Memory monitoring commands
system-memory: deps
	@echo "Checking system memory status..."
	$(PYRUN) -c "from create_pdf import MemoryMonitor; monitor = MemoryMonitor(); stats = monitor.check_memory(); print(f'Current Memory: {stats.get(\"current_mb\", \"N/A\")}MB'); print(f'System Total: {stats.get(\"system_total_gb\", \"N/A\")}GB'); print(f'System Available: {stats.get(\"system_available_gb\", \"N/A\")}GB'); print(f'System Usage: {stats.get(\"system_percent_used\", \"N/A\")}%') if stats.get('available') else print('Memory monitoring not available')"

memory-test: deps
	@echo "Testing memory monitoring with sample data..."
	$(PYRUN) -c "from create_pdf import MemoryMonitor; monitor = MemoryMonitor(); monitor.log_memory('test'); summary = monitor.get_summary(); print('Memory Summary:', summary)"

# Discord monitoring commands
discord-test: deps
	@echo "Testing Discord integration..."
	$(PYRUN) tools/discord_monitor.py --test

discord-stats: deps
	@echo "Sending collection stats to Discord..."
	$(PYRUN) tools/discord_monitor.py --stats

discord-daily: deps
	@echo "Sending daily summary to Discord..."
	$(PYRUN) tools/discord_monitor.py --daily

discord-alert: deps
	@if [ -z "$(MSG)" ]; then \
		echo "MSG is required. Usage: make discord-alert MSG='System updated successfully' TYPE=success"; \
		exit 1; \
	fi
	$(PYRUN) tools/discord_monitor.py --alert "$(MSG)" --alert-type $(or $(TYPE),info)

dedupe-images: deps
	$(PYRUN) scripts/maintenance/dedupe_shared_images.py

# Enhanced CLI commands for art type filtering and preview modes
fetch-by-arttype: deps
	@if [ -z "$(ARTTYPE)" ]; then \
		echo "ARTTYPE is required. Usage: make fetch-by-arttype ARTTYPE=showcase LANG=ph SET=one"; \
		echo "Available art types: standard, fullart, showcase, borderless, extended, retro, textless, doublefaced"; \
		exit 1; \
	fi
	@$(PYRUN) -c "import sys; sys.path.insert(0, '.'); from create_pdf import _bulk_iter_basic_lands, _derive_art_type, _normalize_langs; \
	langs = _normalize_langs('$(or $(LANG),en)'); \
	all_lands = [l for l in _bulk_iter_basic_lands(lang_filter=langs, set_filter='$(SET)' if '$(SET)' else None)]; \
	filtered = [l for l in all_lands if _derive_art_type(l) == '$(ARTTYPE)']; \
	print(f'Found {len(filtered)} $(ARTTYPE) lands with filters: LANG=$(or $(LANG),en) SET=$(SET)'); \
	[print(f'  {l.get(\"name\")} ({l.get(\"set\").upper()} #{l.get(\"collector_number\")}) - {l.get(\"artist\", \"Unknown\")}') for l in filtered[:20]]; \
	print(f'... {len(filtered)-20} more cards' if len(filtered) > 20 else '')"

preview-lands: deps
	@$(PYRUN) -c "import sys; sys.path.insert(0, '.'); from create_pdf import _bulk_iter_basic_lands, _normalize_langs; \
	langs = _normalize_langs('$(or $(LANG),en)'); \
	cards = [c for c in _bulk_iter_basic_lands(lang_filter=langs, set_filter='$(SET)' if '$(SET)' else None)]; \
	limit = min(int('$(or $(LIMIT),10)'), len(cards)); \
	print(f'Preview: {limit}/{len(cards)} lands with LANG=$(or $(LANG),en) SET=$(SET)'); \
	[print(f'  {c.get(\"name\")} ({c.get(\"set\").upper()} #{c.get(\"collector_number\")}) - {c.get(\"rarity\")} - {c.get(\"artist\", \"Unknown\")}') for c in cards[:limit]]"

# === Hobby Features ===

db-optimize: deps
	@echo "Optimizing database with composite indexes..."
	@$(PYRUN) tools/optimize_db.py optimize

db-info: deps
	@echo "Database index information..."
	@$(PYRUN) tools/optimize_db.py info

artist-search: deps
	@if [ -z "$(ARTIST)" ]; then \
		echo "ARTIST is required. Usage: make artist-search ARTIST=\"Rebecca Guay\" [TYPE=creature] [LIMIT=20]"; \
		exit 1; \
	fi
	@$(PYRUN) tools/hobby_features.py artist "$(ARTIST)" $(if $(TYPE),--type "$(TYPE)") $(if $(LIMIT),--limit $(LIMIT))

random-cards: deps
	@echo "Random Card Discovery"
	@$(PYRUN) tools/hobby_features.py random $(if $(TYPE),--type "$(TYPE)") $(if $(RARITY),--rarity "$(RARITY)") $(if $(SET),--set "$(SET)") $(if $(COUNT),--count $(COUNT))

explore-set: deps
	@if [ -z "$(SET)" ]; then \
		echo "SET is required. Usage: make explore-set SET=ltr [TYPE=creature] [RARITY=rare] [SORT=name] [LIMIT=50]"; \
		exit 1; \
	fi
	@$(PYRUN) tools/hobby_features.py explore "$(SET)" $(if $(TYPE),--type "$(TYPE)") $(if $(RARITY),--rarity "$(RARITY)") $(if $(SORT),--sort "$(SORT)") $(if $(LIMIT),--limit $(LIMIT))

progress-demo: deps
	@echo "Magic-themed progress bar demo"
	@$(PYRUN) tools/mtg_progress.py

# === Asset Sync Helpers ===

sync-tokens: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "PROFILE is required. Usage: make sync-tokens PROFILE=commander [DRY=1] [VERBOSE=1]"; \
		exit 1; \
	fi
	@$(PYRUN) tools/asset_sync.py sync-tokens "$(PROFILE)" $(if $(DRY),--dry-run) $(if $(VERBOSE),--verbose)

sync-lands: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "PROFILE is required. Usage: make sync-lands PROFILE=commander [TYPE=all] [DRY=1] [VERBOSE=1]"; \
		exit 1; \
	fi
	@$(PYRUN) tools/asset_sync.py sync-lands "$(PROFILE)" $(if $(TYPE),--type $(TYPE)) $(if $(DRY),--dry-run) $(if $(VERBOSE),--verbose)

list-profiles: deps
	@$(PYRUN) tools/asset_sync.py profiles

# === New Commands ===

setup: venv deps hooks-install
	@echo "Environment ready! Run 'make menu' to start."

status: deps
	@echo "Collection Status"
	@$(PYRUN) -c "from pathlib import Path; \
	shared = Path('../magic-the-gathering/shared'); \
	folders = sorted([d for d in shared.iterdir() if d.is_dir() and d.name != 'reports']); \
	counts = {f.name: len(list(f.rglob('*.png'))) for f in folders}; \
	total = sum(counts.values()); \
	[print(f'  {k.replace(\"-\", \" \").title()}: {v:,}') for k, v in counts.items() if v > 0]; \
	print(f'  ───────────────────'); \
	print(f'  Total Assets: {total:,}')"

clean:
	@rm -rf __pycache__ .pytest_cache .ruff_cache *.pyc
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up temporary files"

test: deps
	@echo "Running quick tests..."
	@$(PYRUN) -m py_compile create_pdf.py
	@echo "Syntax check passed"

verify-docs: deps
	@echo "Verifying documentation consistency..."
	$(PYRUN) tools/verify_docs.py

test-plugins: deps
	@echo "Running plugin regression tests..."
	$(PYRUN) tools/test_plugins.py

test-schema: deps
	@echo "Running database schema validation tests..."
	@$(PYRUN) tools/test_schema.py

test-integration: deps
	@echo "Running integration tests with pytest..."
	$(PYRUN) -m pytest tests/test_integration.py -v

test-ai-recommendations: deps
	@echo "Running comprehensive AI recommendations test suite..."
	$(PYRUN) tools/test_ai_recommendations.py

benchmark: deps
	@echo "Running performance benchmarks..."
	$(PYRUN) tests/benchmarks/run_benchmarks.py

benchmark-compare: deps
	@echo "Comparing benchmark results..."
	@if [ ! -f benchmarks/baseline.json ]; then \
		echo "Error: baseline.json not found. Run 'make benchmark' first."; \
		exit 1; \
	fi
	@if [ ! -f benchmarks/current.json ]; then \
		echo "Error: current.json not found. Run 'make benchmark' first."; \
		exit 1; \
	fi
	$(PYRUN) tools/bench_report.py benchmarks/baseline.json benchmarks/current.json

query-relationships: deps
	@echo "Querying card relationships..."
	$(PYRUN) tools/query_relationships.py $(ARGS)

bulk-audit: deps
	@echo "Auditing bulk data integrity..."
	$(PYRUN) tools/audit_bulk.py

collection-report: deps
	@echo "Generating collection insights report..."
	@$(PYRUN) tools/collection_insights.py $(if $(PROFILE),$(PROFILE),)

profile-stats: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "Error: PROFILE required. Usage: make profile-stats PROFILE=patrick"; \
		exit 1; \
	fi
	$(PYRUN) tools/profile_stats.py "$(PROFILE)" $(ARGS)

shared-sync: deps
	@if [ -z "$(PROFILE)" ]; then \
		echo "Error: PROFILE required. Usage: make shared-sync PROFILE=patrick"; \
		exit 1; \
	fi
	$(PYRUN) tools/shared_library_sync.py sync "$(PROFILE)" $(ARGS)

set-check: deps
	@echo "Checking for new set releases..."
	$(PYRUN) tools/set_release_automation.py check $(ARGS)

token-sync: deps
	@echo "Syncing token coverage..."
	$(PYRUN) tools/token_coverage_sync.py check $(ARGS)

search: deps
	@if [ -z "$(QUERY)" ]; then \
		echo "Error: QUERY required. Usage: make search QUERY='goblin AND red'"; \
		exit 1; \
	fi
	$(PYRUN) tools/advanced_search.py search "$(QUERY)"

search-save: deps
	@if [ -z "$(NAME)" ] || [ -z "$(QUERY)" ]; then \
		echo "Error: NAME and QUERY required. Usage: make search-save NAME=red-goblins QUERY='type:creature AND color:red'"; \
		exit 1; \
	fi
	$(PYRUN) tools/advanced_search.py save "$(NAME)" "$(QUERY)"

search-list: deps
	$(PYRUN) tools/advanced_search.py list

test-new-features: deps
	@echo "Testing all Phase 1-3 features..."
	$(PYRUN) tools/test_new_features.py

generate-docs: deps
	@echo "Generating CLI and schema documentation..."
	$(PYRUN) tools/generate_cli_docs.py
	$(PYRUN) tools/generate_schema_docs.py

generate-coverage-badge: deps
	@echo "Generating coverage badge..."
	$(PYRUN) tools/generate_coverage_badge.py

# Batch PDF generation across profiles (single shell for loop)
.ONESHELL:
pdf-batch: deps
	@if [ -z "$(PROFILES)" ]; then \
		echo "Error: PROFILES not specified. Usage: make pdf-batch PROFILES=patrick,jack,wyatt"; \
		exit 1; \
	fi
	echo "Generating PDFs for profiles: $(PROFILES)"
	IFS=',' read -ra PROFILE_ARRAY <<< "$(PROFILES)"
	for profile in "$${PROFILE_ARRAY[@]}"; do
		echo "Processing $$profile..."
		$(MAKE) --no-print-directory pdf PROFILE="$$profile" || echo "Failed for $$profile"
	done
	echo "Batch PDF generation complete"

populate-token-relationships: deps
	@echo "Populating token relationships from all_parts..."
	@$(PYRUN) tools/populate_token_relationships.py

detect-duplicates-scan: deps
	@echo "Scanning and hashing images for duplicate detection..."
	@$(PYRUN) tools/detect_duplicates.py --scan

detect-duplicates-find: deps
	@echo "Finding duplicate images..."
	@$(PYRUN) tools/detect_duplicates.py --find $(if $(THRESHOLD),--threshold $(THRESHOLD),)

score-image-quality: deps
	@echo "Scoring image quality..."
	@$(PYRUN) tools/score_image_quality.py $(if $(RESCORE),--rescore,)

bulk-sync: bulk-fetch-all bulk-index-rebuild bulk-index-vacuum
	@echo "Bulk data synchronized"

discord: deps
	@if [ "$(STATS)" = "1" ]; then $(MAKE) discord-stats; fi
	@if [ "$(DAILY)" = "1" ]; then $(MAKE) discord-daily; fi
	@if [ -n "$(MSG)" ]; then $(MAKE) discord-alert MSG="$(MSG)"; fi

scrape-art: deps
	@if [ -z "$(URL)" ]; then \
		echo "URL is required. Usage: make scrape-art URL=https://... [START=1] [PAGES=10]"; \
		exit 1; \
	fi
	$(PYRUN) scripts/utilities/scrape_mythic_blackcore.py $(if $(START),$(START),1) $(if $(PAGES),$(PAGES),10)

# --- CI meta target ---
ci: deps test-integration generate-docs generate-coverage-badge
	@echo "CI pipeline complete"
