# Ubuntu Server Deployment Guide

This guide covers deploying the Proxy Machine project on Ubuntu Server 22.04 LTS or newer.

## Prerequisites

- Ubuntu Server 22.04+ (Python 3.10+ required)
- Sudo access
- At least 5GB free disk space (for bulk data and dependencies)
- Internet connection for initial setup

## 1. System Dependencies

Install required system packages:

```bash
# Update package list
sudo apt update

# Install Python 3.10+ and build essentials
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Install image processing libraries (required for Pillow/OpenCV)
sudo apt install -y \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev

# Install OpenCV dependencies
sudo apt install -y \
    libopencv-dev \
    python3-opencv

# Install SQLite3 (usually pre-installed)
sudo apt install -y sqlite3 libsqlite3-dev

# Install git if not present
sudo apt install -y git

# Install curl for downloading uv
sudo apt install -y curl
```

## 2. Install uv (Python Package Manager)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (add to ~/.bashrc for persistence)
export PATH="$HOME/.cargo/bin:$PATH"

# Verify installation
uv --version
```

## 3. Clone and Setup Project

```bash
# Clone repository (adjust URL to your repo)
cd ~
git clone <your-repo-url> the-proxy-printer
cd the-proxy-printer/proxy-machine

# Create Python virtual environment with uv
uv venv --python 3.10

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

## 4. Initial Data Setup

```bash
# Create necessary directories
mkdir -p bulk-data
mkdir -p ../magic-the-gathering/shared/{tokens,basic-lands,non-basic-lands,card-backs}
mkdir -p ../archived

# Download bulk data (this will take several minutes)
uv run python tools/fetch_bulk.py --id all-cards
uv run python tools/fetch_bulk.py --id oracle-cards
uv run python tools/fetch_bulk.py --id unique-artwork

# Build SQLite database (this may take 10-15 minutes)
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# Verify setup
uv run python tools/verify.py
```

## 5. Environment Configuration

Create a `.env` file for configuration:

```bash
cat > .env << 'EOF'
# Proxy Machine Configuration
PM_OFFLINE=0
PM_ASK_REFRESH=0
PROXY_PROFILE=default

# Custom bulk data server (optional, see SELF_HOSTING.md)
# PM_BULK_DATA_URL=https://your-server.com/bulk-data

# Performance tuning
SCRYFALL_MAX_WORKERS=4
PM_HTTP_TIMEOUT=30
PM_HTTP_RETRIES=4

# Logging
PM_LOG_LEVEL=INFO
EOF
```

Load environment variables:
```bash
export $(cat .env | xargs)
```

## 6. Test Basic Functionality

```bash
# Test database query
uv run python -c "from db.bulk_index import query_cards; results = query_cards(name_filter='Lightning Bolt', limit=3); print(f'Found {len(results)} results')"

# Test PDF generation (requires deck file)
# uv run python create_pdf.py path/to/deck.txt --output test.pdf
```

## 7. Automated Updates (Optional)

Create a cron job to refresh bulk data weekly:

```bash
# Edit crontab
crontab -e

# Add this line (runs every Sunday at 2 AM)
0 2 * * 0 cd ~/the-proxy-printer/proxy-machine && source .venv/bin/activate && uv run python tools/fetch_bulk.py --id all-cards && uv run python tools/fetch_bulk.py --id oracle-cards && uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"
```

## 8. Systemd Service (Optional)

If you want to run a web service (Flask API), create a systemd service:

```bash
sudo nano /etc/systemd/system/proxy-machine.service
```

```ini
[Unit]
Description=Proxy Machine Service
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/the-proxy-printer/proxy-machine
Environment="PATH=/home/your-username/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/your-username/.cargo/bin/uv run python your_service.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable proxy-machine
sudo systemctl start proxy-machine
sudo systemctl status proxy-machine
```

## 9. Firewall Configuration (if needed)

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (if hosting web service)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

## 10. Monitoring and Logs

```bash
# View service logs
sudo journalctl -u proxy-machine -f

# Check disk usage
df -h ~/the-proxy-printer/proxy-machine/bulk-data

# Monitor system resources
htop
```

## Troubleshooting

### Issue: Python version too old
```bash
# Check Python version
python3 --version

# If < 3.10, install from deadsnakes PPA (Ubuntu 20.04)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev
```

### Issue: Image processing errors
```bash
# Reinstall image libraries
sudo apt install --reinstall libjpeg-dev libpng-dev
uv pip install --force-reinstall Pillow opencv-python-headless
```

### Issue: Database locked
```bash
# Check for stale locks
lsof ~/the-proxy-printer/proxy-machine/bulk-data/bulk.db

# Kill process if needed
kill -9 <PID>
```

### Issue: Permission denied
```bash
# Fix ownership
sudo chown -R $USER:$USER ~/the-proxy-printer

# Fix permissions
chmod -R u+rw ~/the-proxy-printer/proxy-machine/bulk-data
```

## Performance Tuning

### For servers with limited RAM (<4GB):
```bash
# Reduce worker count
export SCRYFALL_MAX_WORKERS=2

# Use swap if needed
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### For faster database queries:
```bash
# Optimize database
uv run python tools/optimize_db.py all

# Enable WAL mode for concurrent access
sqlite3 bulk-data/bulk.db "PRAGMA journal_mode=WAL;"
```

## Security Considerations

1. **Never expose bulk.db directly to the internet** - it contains no sensitive data but is large
2. **Use HTTPS** for any web services
3. **Implement rate limiting** if exposing APIs publicly
4. **Keep system updated**: `sudo apt update && sudo apt upgrade`
5. **Use SSH keys** instead of password authentication
6. **Consider fail2ban** for SSH protection

## Next Steps

- See `SELF_HOSTING.md` for setting up a shared data server
- See `WORKFLOW.md` for usage documentation
- See `PROJECT_OVERVIEW.md` for architecture details
