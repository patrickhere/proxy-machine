# Quick Reference Card

Quick commands and workflows for the Proxy Machine project.

---

## Starting a New Session

### 1. Pull Latest Changes
```bash
cd /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine
git pull origin main
```

### 2. Check Status
```bash
git status
make test
```

### 3. Tell Claude Code Your Goal
Use the template from `docs/SESSION_TEMPLATE.md`

---

## Common Git Commands

```bash
# Status
git status                    # What changed?
git diff                      # Show changes
git log --oneline -10         # Recent commits

# Commit
git add .                     # Stage all changes
git commit -m "Message"       # Commit with message
git push origin main          # Push to GitHub

# Branches
git checkout -b feature/name  # Create feature branch
git checkout main             # Switch to main
git merge feature/name        # Merge branch to main

# Undo
git restore <file>            # Discard changes
git reset --soft HEAD~1       # Undo last commit (keep changes)
```

---

## Project Commands

```bash
# Development
make menu                     # Interactive menu
make pdf PROFILE=name         # Generate PDF
make dashboard                # Start web UI
make test                     # Run tests

# Database
make bulk-sync                # Rebuild database
make db-info                  # Database stats

# Deployment
./scripts/deploy-to-unraid.sh 10.1.0.50
```

---

## File Locations

```bash
# Key files
create_pdf.py                 # Main CLI
dashboard.py                  # Web UI
config_paths.py               # Path configuration
CLAUDE.md                     # Project instructions

# Documentation
docs/DEVELOPMENT.md           # Git workflow
docs/SESSION_TEMPLATE.md      # Claude Code templates
docs/guides/GUIDE.md          # User guide
docs/guides/REFERENCE.md      # Command reference
```

---

## GitHub URLs

- **Repository:** https://github.com/patrickhere/proxy-machine.git
- **Clone:** `git clone https://github.com/patrickhere/proxy-machine.git`

---

## Session End Checklist

- [ ] `git status` - Review changes
- [ ] `make test` - Run tests
- [ ] `git commit -m "Description"` - Commit
- [ ] `git push origin main` - Push to GitHub
- [ ] Update docs if needed

---

## Getting Help

```bash
make help                     # Makefile commands
uv run python create_pdf.py --help  # CLI help
```

See `docs/DEVELOPMENT.md` for detailed workflows.
