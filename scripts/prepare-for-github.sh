#!/bin/bash
# Prepare Proxy Machine for GitHub
# Checks for sensitive data, updates documentation, and commits changes

set -e

echo "=================================================="
echo "Proxy Machine - GitHub Preparation"
echo "=================================================="
echo ""

# Check we're in the right directory
if [ ! -f "create_pdf.py" ]; then
    echo "Error: Run this script from the proxy-machine directory"
    exit 1
fi

# Step 1: Check for sensitive data
echo "Step 1/7: Checking for sensitive data..."
echo ""

ISSUES=0

# Check for hardcoded IPs
if git grep -i "192\.168\|10\." -- '*.py' '*.sh' | grep -v "example" | grep -v "#"; then
    echo "⚠️  Warning: Found hardcoded IP addresses (review above)"
    ISSUES=$((ISSUES + 1))
fi

# Check for API keys/secrets
if git grep -i "api.key\|secret\|password" -- '*.py' '*.sh' | grep -v "placeholder" | grep -v "#" | grep -v "variable"; then
    echo "⚠️  Warning: Found potential secrets (review above)"
    ISSUES=$((ISSUES + 1))
fi

# Check for webhook URLs
if git grep "hooks\.discord\|webhook" -- '*.py' '*.json' | grep -v "gitignore" | grep -v "example"; then
    echo "⚠️  Warning: Found webhook URLs (review above)"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "✓ No sensitive data found"
fi
echo ""

# Step 2: Verify .gitignore
echo "Step 2/7: Verifying .gitignore..."
if [ ! -f .gitignore ]; then
    echo "❌ Error: .gitignore missing!"
    exit 1
fi

REQUIRED=(
    ".env"
    "bulk-data/"
    "*.db"
    "config/notifications.json"
    "*.log"
)

for pattern in "${REQUIRED[@]}"; do
    if grep -q "$pattern" .gitignore; then
        echo "  ✓ Ignoring $pattern"
    else
        echo "  ❌ Missing: $pattern"
        ISSUES=$((ISSUES + 1))
    fi
done
echo ""

# Step 3: Check for large files
echo "Step 3/7: Checking for large files..."
LARGE_FILES=$(find . -type f -size +10M ! -path "./.git/*" ! -path "./bulk-data/*" ! -path "./data/*" 2>/dev/null || true)

if [ -n "$LARGE_FILES" ]; then
    echo "⚠️  Warning: Large files found (>10MB):"
    echo "$LARGE_FILES"
    echo ""
    echo "Consider adding these to .gitignore"
    ISSUES=$((ISSUES + 1))
else
    echo "✓ No large files found"
fi
echo ""

# Step 4: Clean up junk files
echo "Step 4/7: Cleaning up junk files..."
find . -name ".DS_Store" -type f -delete 2>/dev/null || true
find . -name "*.pyc" -type f -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
echo "✓ Cleaned up .DS_Store and Python cache files"
echo ""

# Step 5: Verify required files
echo "Step 5/7: Verifying required files..."
REQUIRED_FILES=(
    "README.md"
    "LICENSE"
    ".gitignore"
    ".dockerignore"
    "Dockerfile"
    "docker-compose.yml"
    ".env.example"
    "requirements.txt"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ❌ Missing: $file"
        ISSUES=$((ISSUES + 1))
    fi
done
echo ""

# Step 6: Check documentation
echo "Step 6/7: Checking documentation..."
DOCS=(
    "mds/guides/GUIDE.md"
    "mds/guides/REFERENCE.md"
    "mds/guides/WORKFLOW.md"
    "docs/UNRAID_DEPLOYMENT.md"
)

for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo "  ✓ $doc"
    else
        echo "  ⚠️  Missing: $doc (optional)"
    fi
done
echo ""

# Step 7: Show git status
echo "Step 7/7: Current git status..."
echo ""
git status --short
echo ""

# Summary
echo "=================================================="
echo "Preparation Summary"
echo "=================================================="
echo ""

if [ $ISSUES -gt 0 ]; then
    echo "⚠️  Found $ISSUES issue(s) - review above"
    echo ""
    echo "Fix issues before pushing to GitHub"
    exit 1
else
    echo "✓ All checks passed!"
    echo ""
    echo "Ready to commit and push to GitHub:"
    echo ""
    echo "  git add ."
    echo "  git commit -m 'Add Docker support and web dashboard features'"
    echo "  git push origin main"
    echo ""
    echo "Or create a new repository:"
    echo ""
    echo "  # On GitHub, create a new repository, then:"
    echo "  git remote add origin git@github.com:yourusername/proxy-machine.git"
    echo "  git push -u origin main"
    echo ""
fi
