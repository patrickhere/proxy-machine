#!/bin/bash
# Automated setup script for Proxy Machine data server with Tailscale
# Run this on your Ubuntu server after installing Tailscale

set -e

echo "=========================================="
echo "Proxy Machine Tailscale Server Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="$HOME/the-proxy-printer"
WORK_DIR="$INSTALL_DIR/proxy-machine"
PORT=8080

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}ERROR: Do not run this script as root${NC}"
    echo "Run as your regular user: ./setup-tailscale-server.sh"
    exit 1
fi

echo "This script will:"
echo "  1. Install system dependencies"
echo "  2. Install uv (Python package manager)"
echo "  3. Clone/update the repository"
echo "  4. Download bulk data from Scryfall"
echo "  5. Build the SQLite database"
echo "  6. Create a simple HTTP server"
echo "  7. Set up systemd services"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Install system dependencies
echo -e "${GREEN}[1/7] Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv python3-dev \
    libjpeg-dev libpng-dev libopencv-dev \
    sqlite3 libsqlite3-dev \
    git curl

# Step 2: Install uv
echo -e "${GREEN}[2/7] Installing uv...${NC}"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
else
    echo "uv already installed"
fi

# Step 3: Clone/update repository
echo -e "${GREEN}[3/7] Setting up repository...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Repository exists, pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Cloning repository..."
    read -p "Enter repository URL: " REPO_URL
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$WORK_DIR"

# Create virtual environment and install dependencies
echo "Installing Python dependencies..."
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt

# Step 4: Download bulk data
echo -e "${GREEN}[4/7] Downloading bulk data from Scryfall...${NC}"
echo "This will take several minutes..."
mkdir -p bulk-data

uv run python tools/fetch_bulk.py --id all-cards
uv run python tools/fetch_bulk.py --id oracle-cards
uv run python tools/fetch_bulk.py --id unique-artwork

# Step 5: Build database
echo -e "${GREEN}[5/7] Building SQLite database...${NC}"
echo "This may take 10-15 minutes..."
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# Optimize database
echo "Optimizing database..."
uv run python tools/optimize_db.py all

# Verify setup
echo "Verifying setup..."
uv run python tools/verify.py

# Step 6: Create HTTP server
echo -e "${GREEN}[6/7] Creating HTTP server...${NC}"
cat > "$WORK_DIR/serve_data.py" << 'EOFSERVER'
#!/usr/bin/env python3
"""Simple HTTP server for sharing Proxy Machine data via Tailscale."""

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import sys

PORT = 8080
DATA_ROOT = Path(__file__).parent

class ProxyDataHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DATA_ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')

        if self.path.endswith(('.json.gz', '.db')):
            self.send_header('Cache-Control', 'public, max-age=604800')
        elif self.path.endswith(('.jpg', '.png', '.webp')):
            self.send_header('Cache-Control', 'public, max-age=2592000')

        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

def main():
    httpd = HTTPServer(('', PORT), ProxyDataHandler)
    print(f"Serving on port {PORT}")
    print(f"Data root: {DATA_ROOT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()

if __name__ == '__main__':
    main()
EOFSERVER

chmod +x "$WORK_DIR/serve_data.py"

# Step 7: Set up systemd service
echo -e "${GREEN}[7/7] Setting up systemd service...${NC}"

sudo tee /etc/systemd/system/proxy-data-server.service > /dev/null << EOFSERVICE
[Unit]
Description=Proxy Machine Data Server
After=network.target tailscaled.service
Wants=tailscaled.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORK_DIR
Environment="PATH=$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$HOME/.cargo/bin/uv run python serve_data.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable proxy-data-server
sudo systemctl start proxy-data-server

# Create update script
echo "Creating update script..."
cat > "$HOME/update-proxy-data.sh" << 'EOFUPDATE'
#!/bin/bash
set -e

WORK_DIR=~/the-proxy-printer/proxy-machine
LOG_FILE=~/proxy-data-update.log

echo "[$(date)] Starting update..." | tee -a "$LOG_FILE"

cd "$WORK_DIR"
source .venv/bin/activate

echo "Downloading bulk data..." | tee -a "$LOG_FILE"
uv run python tools/fetch_bulk.py --id all-cards 2>&1 | tee -a "$LOG_FILE"
uv run python tools/fetch_bulk.py --id oracle-cards 2>&1 | tee -a "$LOG_FILE"
uv run python tools/fetch_bulk.py --id unique-artwork 2>&1 | tee -a "$LOG_FILE"

echo "Rebuilding database..." | tee -a "$LOG_FILE"
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)" 2>&1 | tee -a "$LOG_FILE"

echo "Optimizing database..." | tee -a "$LOG_FILE"
uv run python tools/optimize_db.py all 2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] Update complete!" | tee -a "$LOG_FILE"
EOFUPDATE

chmod +x "$HOME/update-proxy-data.sh"

# Get Tailscale IP
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "NOT_INSTALLED")

echo ""
echo -e "${GREEN}=========================================="
echo "Setup Complete!"
echo "==========================================${NC}"
echo ""
echo "Server is running on port $PORT"
echo ""

if [ "$TAILSCALE_IP" != "NOT_INSTALLED" ]; then
    echo -e "${GREEN}Tailscale IP: $TAILSCALE_IP${NC}"
    echo ""
    echo "Friends should use:"
    echo "  PM_BULK_DATA_URL=http://$TAILSCALE_IP:$PORT"
else
    echo -e "${YELLOW}Tailscale not detected!${NC}"
    echo "Install Tailscale: curl -fsSL https://tailscale.com/install.sh | sh"
    echo "Then run: sudo tailscale up"
fi

echo ""
echo "Service status:"
sudo systemctl status proxy-data-server --no-pager -l

echo ""
echo "Useful commands:"
echo "  Check status:  sudo systemctl status proxy-data-server"
echo "  View logs:     sudo journalctl -u proxy-data-server -f"
echo "  Restart:       sudo systemctl restart proxy-data-server"
echo "  Update data:   ~/update-proxy-data.sh"
echo ""
echo "To set up weekly updates:"
echo "  crontab -e"
echo "  Add: 0 3 * * 0 $HOME/update-proxy-data.sh"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "  1. Invite friends to your Tailscale network"
echo "  2. Share your Tailscale IP: $TAILSCALE_IP"
echo "  3. Friends set: PM_BULK_DATA_URL=http://$TAILSCALE_IP:$PORT"
echo ""
