#!/bin/bash
# Sanitize repository for GitHub upload
# Removes personal information and ensures clean state

set -e

echo "=========================================="
echo "Sanitizing Repository for GitHub"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo -e "${YELLOW}This script will:${NC}"
echo "  1. Check for personal information"
echo "  2. Verify .gitignore is comprehensive"
echo "  3. Remove sensitive files"
echo "  4. Create a clean commit"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Check for personal info patterns
echo -e "${GREEN}[1/5] Checking for personal information...${NC}"

PERSONAL_PATTERNS=(
    "/Users/patrick"
    "patrick@"
    "100\.64\.[0-9]+\.[0-9]+"  # Specific Tailscale IPs
)

FOUND_ISSUES=0

for pattern in "${PERSONAL_PATTERNS[@]}"; do
    echo "  Checking for: $pattern"
    if git grep -n "$pattern" -- '*.md' '*.sh' '*.py' 2>/dev/null | grep -v "sanitize-for-github.sh" | grep -v ".git/"; then
        echo -e "${YELLOW}    Found instances (review if these should be genericized)${NC}"
        FOUND_ISSUES=1
    fi
done

if [ $FOUND_ISSUES -eq 1 ]; then
    echo -e "${YELLOW}  Note: Some personal references found. These may be okay if they're in examples.${NC}"
    echo -e "${YELLOW}  Generic placeholders like 'YOUR_TAILSCALE_IP' are fine.${NC}"
fi

# Step 2: Verify .gitignore
echo -e "${GREEN}[2/5] Verifying .gitignore...${NC}"

REQUIRED_IGNORES=(
    ".env"
    "*.db"
    "bulk-data/"
    "config/notifications.json"
    "*.log"
)

for ignore in "${REQUIRED_IGNORES[@]}"; do
    if grep -q "$ignore" .gitignore; then
        echo "  [OK] $ignore"
    else
        echo -e "${RED}  [MISSING] $ignore${NC}"
        FOUND_ISSUES=1
    fi
done

# Step 3: Check for files that shouldn't be committed
echo -e "${GREEN}[3/5] Checking for sensitive files...${NC}"

SENSITIVE_FILES=(
    ".env"
    ".env.local"
    "config/notifications.json"
    "*.db"
    "bulk-data/"
)

for pattern in "${SENSITIVE_FILES[@]}"; do
    if find . -name "$pattern" -not -path "./.git/*" 2>/dev/null | grep -q .; then
        echo -e "${YELLOW}  Found: $pattern (should be gitignored)${NC}"
    fi
done

# Step 4: Clean up unnecessary files
echo -e "${GREEN}[4/5] Cleaning up...${NC}"

# Remove empty database file
if [ -f "bulk_index.db" ] && [ ! -s "bulk_index.db" ]; then
    echo "  Removing empty bulk_index.db"
    rm -f bulk_index.db
fi

# Remove .DS_Store files
find . -name ".DS_Store" -delete 2>/dev/null || true
echo "  Removed .DS_Store files"

# Remove Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "  Removed Python cache"

# Step 5: Summary
echo -e "${GREEN}[5/5] Summary${NC}"
echo ""

# Check git status
if git status --porcelain | grep -q .; then
    echo -e "${YELLOW}Uncommitted changes detected:${NC}"
    git status --short
    echo ""
    echo "Review these changes before committing."
else
    echo -e "${GREEN}Repository is clean!${NC}"
fi

echo ""
echo "=========================================="
echo "Sanitization Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Review any flagged personal information"
echo "  2. Test that scripts work with generic placeholders"
echo "  3. Commit changes: git add -A && git commit -m 'Sanitize for GitHub'"
echo "  4. Push to GitHub: git push origin main"
echo ""
echo "Remember:"
echo "  - Use YOUR_TAILSCALE_IP instead of specific IPs"
echo "  - Use /home/username instead of /Users/patrick"
echo "  - Keep example IPs generic (100.64.x.y)"
echo ""
