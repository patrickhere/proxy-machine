# Claude Code Session Template

Use this template when starting a new Claude Code session on this project.

---

## Session Start Message (copy this to Claude Code)

```
I'm working on the Proxy Machine project - a Python CLI/web app for Magic: The Gathering proxy card generation.

Project location: /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine
GitHub: https://github.com/patrickhere/proxy-machine.git

Before we start:
1. Pull latest changes from GitHub
2. Check git status
3. Review CLAUDE.md for project conventions

Today I want to: [DESCRIBE YOUR GOAL HERE]
```

---

## Common Session Goals

### Feature Development
```
Today I want to: Add [feature description] to the [component name]

Context:
- User-facing feature / Internal improvement
- Should work with [existing feature]
- Located in [file/module name]

Requirements:
- [Requirement 1]
- [Requirement 2]
- Update relevant documentation
```

### Bug Fixes
```
Today I want to: Fix bug where [description of problem]

Steps to reproduce:
1. [Step 1]
2. [Step 2]
3. [Expected vs actual behavior]

Error message (if any):
[Paste error message]

Suspected location: [file:line or function name]
```

### Documentation
```
Today I want to: Update documentation for [topic]

Files to update:
- [ ] GUIDE.md (user-facing)
- [ ] REFERENCE.md (technical reference)
- [ ] WORKFLOW.md (engineering conventions)
- [ ] CHANGELOG.md (session notes)
```

### Refactoring
```
Today I want to: Refactor [component/module] to [improvement goal]

Current issues:
- [Issue 1]
- [Issue 2]

Desired outcome:
- [Outcome 1]
- [Outcome 2]

Requirements:
- Don't break existing functionality
- Maintain test coverage
- Update docs to reflect changes
```

### Testing
```
Today I want to: Add tests for [feature/component]

Test coverage needed:
- [ ] Unit tests for [function/class]
- [ ] Integration tests for [workflow]
- [ ] Edge cases: [list scenarios]

Test files: tests/test_[name].py
```

---

## Project Quick Reference

### Architecture
- **Main CLI:** `create_pdf.py` (10,500+ lines, monolithic by design)
- **Database:** `db/bulk_index.py` (SQLite, schema v6)
- **PDF generation:** `utilities.py` (ReportLab)
- **Web dashboard:** `dashboard.py` (Flask)
- **Plugins:** `plugins/` (multi-game support)

### Key Commands
```bash
make menu              # Interactive menu
make pdf PROFILE=name  # Generate PDF
make bulk-sync         # Rebuild database
make test              # Run tests
make dashboard         # Start web UI
```

### File Paths (configurable)
```python
# config_paths.py
PROXY_MACHINE_ROOT     # Project root
SHARED_ROOT            # Shared assets (tokens, lands)
PROFILES_ROOT          # User profiles
BULK_DATA_DIR          # Database location
```

### Documentation
- `docs/DEVELOPMENT.md` - Development workflow
- `CLAUDE.md` - Project instructions for Claude
- `mds/guides/GUIDE.md` - User guide
- `mds/guides/REFERENCE.md` - Command reference
- `mds/guides/WORKFLOW.md` - Engineering conventions

---

## Session End Checklist

Before ending your Claude Code session:

- [ ] Review all changes: `git status` and `git diff`
- [ ] Run tests: `make test`
- [ ] Commit changes: `git commit -m "Description"`
- [ ] Push to GitHub: `git push origin main`
- [ ] Update CHANGELOG.md with session notes (if significant)
- [ ] Update IDEAS.md if new roadmap items identified

---

## Tips for Working with Claude Code

1. **Be specific** - "Add file upload to web dashboard" vs "improve web UI"
2. **Provide context** - mention related features, existing patterns
3. **State requirements** - tests needed? docs updates? compatibility?
4. **Reference files** - "in dashboard.py around line 500" is helpful
5. **Set scope** - "just research, don't implement yet" if exploring

### Good prompts:
- "Add CSV export to the deck analysis feature in dashboard.py"
- "Fix the error where tokens aren't auto-padding to multiples of 8"
- "Refactor the land classification logic to be more maintainable"
- "Add unit tests for the _parse_deck_file function"

### Less helpful prompts:
- "Make it better" (too vague)
- "Fix the bug" (which bug?)
- "Add features" (which features?)

---

## Current Project State (update as needed)

**Last updated:** 2026-01-04

**Recent additions:**
- Docker support (Dockerfile, docker-compose.yml)
- Web dashboard with file upload and deck import
- Configurable paths for Unraid deployment
- GitHub repository setup

**Active work areas:**
- Web UI improvements
- Unraid/Tailscale integration
- PDF generation enhancements

**Known issues:**
- (Add any known bugs or limitations here)

**Next priorities:**
- (Add planned features/fixes here)

---

## Examples

### Example 1: Starting a new feature session
```
I'm working on the Proxy Machine project.

Project: /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine
GitHub: https://github.com/patrickhere/proxy-machine.git

Before we start:
1. Pull latest from GitHub
2. Check git status

Today I want to: Add progress indicators to the web dashboard when generating PDFs

Requirements:
- Show real-time progress during PDF generation
- Use the existing MagicProgressBar style for consistency
- Update the API to stream progress updates
- Works for both profile-based and uploaded image generation

Let me know when you're ready to start!
```

### Example 2: Bug fix session
```
I'm working on the Proxy Machine project.

Project: /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine
GitHub: https://github.com/patrickhere/proxy-machine.git

Today I want to: Fix bug where deck list import fails on Moxfield URLs

Error message:
"Failed to parse deck list: Invalid URL format"

Steps to reproduce:
1. Go to web dashboard
2. Paste Moxfield URL: https://www.moxfield.com/decks/xyz123
3. Click Import
4. Gets error instead of importing deck

Expected: Should parse Moxfield URL and import the deck
Actual: Fails with error

Let's investigate the deck parser in deck/parser.py
```

### Example 3: Documentation session
```
I'm working on the Proxy Machine project.

Project: /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine
GitHub: https://github.com/patrickhere/proxy-machine.git

Today I want to: Document the new web dashboard features we added

Files to update:
- docs/GUIDE.md - add web UI quick start
- docs/REFERENCE.md - document all API endpoints
- README.md - add web UI to overview

New features to document:
- File upload (single and batch)
- Deck list import (URL and text)
- PDF download from browser
- Advanced PDF options (card size, paper size, crop, PPI, quality)
```
