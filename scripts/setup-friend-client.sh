#!/bin/bash
# Quick setup script for friends to connect to your Proxy Machine server
# Run this after joining the Tailscale network

set -e

echo "=========================================="
echo "Proxy Machine Client Setup"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
INSTALL_DIR="$HOME/the-proxy-printer"
WORK_DIR="$INSTALL_DIR/proxy-machine"

echo "This script will:"
echo "  1. Install system dependencies"
echo "  2. Install uv (Python package manager)"
echo "  3. Clone the repository"
echo "  4. Configure to use Patrick's server"
echo "  5. Download bulk data from Patrick's server"
echo "  6. Build local database"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Get server URL from user
echo ""
echo "Enter the server URL Patrick gave you:"
echo "  Examples:"
echo "    http://100.x.y.z:8080 (Tailscale IP)"
echo "    https://proxy-machine.pagolin.com (Pagolin URL)"
echo ""
read -p "Server URL: " SERVER_URL

if [ -z "$SERVER_URL" ]; then
    echo "Error: Server URL is required"
    exit 1
fi

# Step 1: Install system dependencies
echo -e "${GREEN}[1/6] Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv python3-dev \
    libjpeg-dev libpng-dev libopencv-dev \
    sqlite3 libsqlite3-dev \
    git curl

# Step 2: Install uv
echo -e "${GREEN}[2/6] Installing uv...${NC}"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
else
    echo "uv already installed"
fi

# Step 3: Clone repository
echo -e "${GREEN}[3/6] Cloning repository...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Repository already exists, pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull
else
    # Use Patrick's repo URL
    REPO_URL="https://github.com/your-username/the-proxy-printer.git"
    read -p "Repository URL [$REPO_URL]: " INPUT_REPO
    REPO_URL=${INPUT_REPO:-$REPO_URL}

    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$WORK_DIR"

# Install dependencies
echo "Installing Python dependencies..."
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt

# Step 4: Configure client
echo -e "${GREEN}[4/6] Configuring client...${NC}"
cat > .env << EOFENV
# Proxy Machine Configuration
# Server URL (Patrick's server)
PM_BULK_DATA_URL=$SERVER_URL

# Disable prompts
PM_OFFLINE=0
PM_ASK_REFRESH=0

# Default profile
PROXY_PROFILE=default
EOFENV

echo "Configuration saved to .env"
echo "Server URL: $SERVER_URL"

# Load environment
export $(cat .env | xargs)

# Step 5: Download bulk data
echo -e "${GREEN}[5/6] Downloading bulk data from Patrick's server...${NC}"
echo "This will take a few minutes..."

# Test connection first
echo "Testing connection to server..."
if curl -f -s -o /dev/null "$SERVER_URL/bulk-data/"; then
    echo "Connection successful!"
else
    echo -e "${YELLOW}Warning: Could not connect to server${NC}"
    echo "Make sure you're connected to Tailscale and the server is running"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

mkdir -p bulk-data

# Download files
echo "Downloading all-cards.json.gz..."
curl -f "$SERVER_URL/bulk-data/all-cards.json.gz" -o bulk-data/all-cards.json.gz || \
    uv run python tools/fetch_bulk.py --id all-cards

echo "Downloading oracle-cards.json.gz..."
curl -f "$SERVER_URL/bulk-data/oracle-cards.json.gz" -o bulk-data/oracle-cards.json.gz || \
    uv run python tools/fetch_bulk.py --id oracle-cards

echo "Downloading unique-artwork.json.gz..."
curl -f "$SERVER_URL/bulk-data/unique-artwork.json.gz" -o bulk-data/unique-artwork.json.gz || \
    uv run python tools/fetch_bulk.py --id unique-artwork

# Step 6: Build database
echo -e "${GREEN}[6/6] Building local database...${NC}"
echo "This may take 10-15 minutes..."
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# Optimize database
echo "Optimizing database..."
uv run python tools/optimize_db.py all

# Verify setup
echo "Verifying setup..."
uv run python tools/verify.py

echo ""
echo -e "${GREEN}=========================================="
echo "Setup Complete!"
echo "==========================================${NC}"
echo ""
echo "You're now connected to Patrick's server!"
echo "Server URL: $SERVER_URL"
echo ""
echo "To use the proxy machine:"
echo "  cd $WORK_DIR"
echo "  source .venv/bin/activate"
echo "  export \$(cat .env | xargs)"
echo "  uv run python create_pdf.py your-deck.txt"
echo ""
echo "Useful commands:"
echo "  Verify setup:  uv run python tools/verify.py"
echo "  Update data:   curl -f \$PM_BULK_DATA_URL/bulk-data/bulk.db -o bulk-data/bulk.db"
echo ""
echo "For help, see:"
echo "  WORKFLOW.md - How to use the proxy machine"
echo "  PROJECT_OVERVIEW.md - Project documentation"
echo ""
