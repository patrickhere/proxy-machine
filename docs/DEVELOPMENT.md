# Development Workflow

This guide covers the development workflow for the Proxy Machine project now that it's on GitHub.

---

## Quick Start for Development Sessions

### Starting a new feature or fix:
```bash
cd /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine

# 1. Make sure you're on main and up to date
git checkout main
git pull origin main

# 2. Create a feature branch (optional but recommended)
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description

# 3. Make your changes
# ... edit files ...

# 4. Test your changes
make test
make test-integration

# 5. Commit your work (pre-commit hooks will run automatically)
git add .
git commit -m "Description of your changes"

# 6. Push to GitHub
git push -u origin feature/your-feature-name
# or if working directly on main:
git push origin main
```

---

## Working with Claude Code

When working with Claude Code on this project:

### Session Start Checklist:
1. **Pull latest changes:**
   ```bash
   git pull origin main
   ```

2. **Check current state:**
   ```bash
   git status
   make test  # Quick syntax check
   ```

3. **Tell Claude Code your goal** - be specific about what you want to accomplish

### During Development:
- Claude will make changes and create commits
- Pre-commit hooks will run automatically (formatting, linting)
- Review changes with `git diff` or `git status`

### Session End Checklist:
1. **Review all changes:**
   ```bash
   git status
   git log --oneline -5
   ```

2. **Push to GitHub:**
   ```bash
   git push origin main
   ```

3. **Update docs if needed** (CHANGELOG.md, IDEAS.md, etc.)

---

## Branch Strategy

### Recommended approach:

**Option 1: Simple (recommended for solo development)**
- Work directly on `main` branch
- Push frequently to GitHub
- Create backups before major refactors using tags:
  ```bash
  git tag -a v1.1-pre-refactor -m "Backup before Phase 3 refactor"
  git push origin v1.1-pre-refactor
  ```

**Option 2: Feature branches (recommended for experimental work)**
- Create feature branches for new features: `feature/web-ui-improvements`
- Create fix branches for bugs: `fix/pdf-generation-error`
- Merge to main when ready:
  ```bash
  git checkout main
  git merge feature/web-ui-improvements
  git push origin main
  ```

---

## Pre-commit Hooks

The project uses pre-commit hooks that run automatically on `git commit`:

### What runs:
- **trim trailing whitespace** - removes trailing spaces
- **fix end of files** - ensures files end with newline
- **check yaml** - validates YAML syntax
- **check json** - validates JSON syntax
- **mixed line ending** - ensures consistent line endings
- **ruff** - Python linting (warnings are non-blocking)
- **ruff-format** - Auto-formats Python code
- **black** - Additional Python formatting
- **compile Python files** - checks for syntax errors
- **verify documentation** - checks docs are in sync with code

### If hooks fail:
The hooks will auto-fix most issues. Just re-add the fixed files:
```bash
git add .
git commit -m "Your message"  # Try again
```

### Skip hooks (only if needed):
```bash
git commit --no-verify -m "Emergency fix"
```

---

## File Organization

### What to commit:
- ✅ Source code (`.py` files)
- ✅ Configuration (`.json`, `.yaml`, `.toml`)
- ✅ Documentation (`.md` files)
- ✅ Scripts (`scripts/`, `tools/`)
- ✅ Tests (`tests/`)
- ✅ Requirements (`requirements.txt`, `pyproject.toml`)
- ✅ Dockerfiles and docker-compose

### What NOT to commit (already in `.gitignore`):
- ❌ Virtual environments (`.venv/`, `venv/`)
- ❌ Python cache (`__pycache__/`, `*.pyc`)
- ❌ Database files (`*.db`, `bulk-data/`)
- ❌ Generated PDFs/images (`*.pdf`, `*.png` outside examples/)
- ❌ Secrets (`.env`, `config/notifications.json`)
- ❌ IDE files (`.vscode/`, `.idea/`)
- ❌ macOS files (`.DS_Store`)

---

## GitHub Workflow

### Clone on another machine:
```bash
git clone https://github.com/patrickhere/proxy-machine.git
cd proxy-machine
make setup  # Install dependencies
```

### Keep in sync:
```bash
# Before starting work
git pull origin main

# After completing work
git push origin main
```

### Handle conflicts (if working from multiple machines):
```bash
git pull origin main
# If conflicts occur, resolve them in the files marked
git add .
git commit -m "Merge remote changes"
git push origin main
```

---

## Environment-Specific Configuration

### Local development (Mac):
Uses default paths from `config_paths.py`:
```python
PROXY_MACHINE_ROOT = /Users/patrick/Documents/projects/the-proxy-printer/proxy-machine
SHARED_ROOT = /Users/patrick/Documents/projects/the-proxy-printer/magic-the-gathering/shared
PROFILES_ROOT = /Users/patrick/Documents/projects/the-proxy-printer/magic-the-gathering/proxied-decks
```

### Unraid deployment:
Uses environment variables (configured in `docker-compose.yml`):
```bash
PROXY_MACHINE_ROOT=/app
SHARED_ROOT=/data/shared
PROFILES_ROOT=/data/profiles
```

**Never commit local paths to code** - use `config_paths.py` with environment variable overrides.

---

## Deployment Workflow

### Deploy to Unraid:
```bash
# From your Mac
./scripts/deploy-to-unraid.sh 10.1.0.50

# Or for just updating code:
./scripts/deploy-to-unraid.sh 10.1.0.50 --update
```

### Pull latest on Unraid:
```bash
ssh root@10.1.0.50
cd /mnt/user/appdata/proxy-machine/app
git pull origin main
docker-compose down
docker-compose up -d --build
```

---

## Common Git Commands

### Check status:
```bash
git status                    # See what's changed
git diff                      # See detailed changes
git log --oneline -10         # See recent commits
```

### Undo changes:
```bash
git restore <file>            # Discard changes to a file
git restore .                 # Discard all changes
git reset --soft HEAD~1       # Undo last commit (keep changes)
git reset --hard HEAD~1       # Undo last commit (discard changes)
```

### Branches:
```bash
git branch                    # List branches
git branch feature/new-thing  # Create branch
git checkout feature/new-thing # Switch to branch
git checkout -b fix/bug       # Create and switch
git branch -d feature/done    # Delete branch
```

### Remote:
```bash
git remote -v                 # Show remote URLs
git fetch origin              # Download changes (don't merge)
git pull origin main          # Download and merge changes
git push origin main          # Upload changes
```

---

## Continuous Integration (Future)

Consider adding GitHub Actions for:
- Automated testing on push
- Docker image builds
- Documentation generation
- Release automation

Example `.github/workflows/test.yml`:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: make test
      - run: make test-integration
```

---

## Best Practices

1. **Commit often** - small, focused commits are better than large ones
2. **Write clear commit messages** - describe what changed and why
3. **Pull before push** - always pull latest changes before pushing
4. **Test before commit** - run `make test` before committing
5. **Update docs** - keep documentation in sync with code changes
6. **Use branches for experiments** - protect main branch from broken code
7. **Tag releases** - use git tags for version milestones
8. **Keep secrets out** - never commit `.env` or API keys

---

## Troubleshooting

### "Your branch has diverged"
```bash
git fetch origin
git rebase origin/main  # Replay your changes on top of remote
# or
git pull --rebase origin main
```

### "Merge conflict"
```bash
# Edit conflicted files (look for <<<<<<< markers)
git add .
git commit -m "Resolve merge conflict"
```

### "Detached HEAD state"
```bash
git checkout main  # Return to main branch
```

### Pre-commit hooks taking too long
```bash
# Skip verification temporarily
git commit --no-verify -m "Quick fix"
```

### Need to change last commit message
```bash
git commit --amend -m "Better commit message"
git push --force origin main  # Only if not pushed yet
```

---

## Resources

- **GitHub Repository:** https://github.com/patrickhere/proxy-machine.git
- **Git Documentation:** https://git-scm.com/doc
- **Pre-commit Hooks:** https://pre-commit.com/
- **Conventional Commits:** https://www.conventionalcommits.org/
