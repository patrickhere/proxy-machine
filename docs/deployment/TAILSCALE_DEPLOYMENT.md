# Tailscale + Pagolin Deployment Guide

This guide covers the easiest way to share Proxy Machine data with friends using Tailscale (private network) and Pagolin (HTTPS tunneling).

## Why This Approach?

**Advantages:**
- No public IP or port forwarding needed
- Automatic HTTPS with valid certificates (via Pagolin)
- Private network - only your friends can access
- No firewall configuration
- Works behind NAT/CGNAT
- Zero-config for clients
- Built-in authentication via Tailscale

**vs Traditional Setup:**
- No nginx configuration needed
- No Let's Encrypt setup
- No DNS management
- No security hardening required
- Friends don't need to configure authentication

## Architecture

```
Your Server (Tailscale node)
  |
  +-- Pagolin HTTPS tunnel
  |     |
  |     +-- https://your-app.pagolin.com
  |
  +-- Simple HTTP server (Python)
        |
        +-- /bulk-data/
        +-- /tokens/
        +-- /lands/
```

Friends connect via:
1. Join your Tailscale network (one-time setup)
2. Access `https://your-app.pagolin.com` (or Tailscale IP)
3. Client automatically uses your server

## Setup (10 minutes)

### 1. Install Tailscale on Server

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start and authenticate
sudo tailscale up

# Note your Tailscale IP
tailscale ip -4
# Example: 100.x.y.z
```

### 2. Create Simple File Server

Create a lightweight Python server:

```bash
cd ~/the-proxy-printer/proxy-machine
nano serve_data.py
```

```python
#!/usr/bin/env python3
"""
Simple HTTP server for sharing Proxy Machine data via Tailscale.
Serves bulk data, tokens, and card images to friends on your Tailscale network.
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os
import sys

# Configuration
PORT = 8080
DATA_ROOT = Path(__file__).parent

class ProxyDataHandler(SimpleHTTPRequestHandler):
    """Custom handler with CORS and better logging."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DATA_ROOT), **kwargs)

    def end_headers(self):
        # CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')

        # Cache headers
        if self.path.endswith(('.json.gz', '.db')):
            self.send_header('Cache-Control', 'public, max-age=604800')  # 1 week
        elif self.path.endswith(('.jpg', '.png', '.webp')):
            self.send_header('Cache-Control', 'public, max-age=2592000')  # 30 days

        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Cleaner logging
        print(f"[{self.address_string()}] {format % args}")

def main():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, ProxyDataHandler)

    print(f"Serving Proxy Machine data on port {PORT}")
    print(f"Data root: {DATA_ROOT}")
    print(f"\nClients should use:")
    print(f"  Tailscale: http://$(tailscale ip -4):{PORT}")
    print(f"  Pagolin: https://your-app.pagolin.com")
    print("\nPress Ctrl+C to stop")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()

if __name__ == '__main__':
    main()
```

Make it executable:
```bash
chmod +x serve_data.py
```

### 3. Test Locally

```bash
# Start server
uv run python serve_data.py

# In another terminal, test
curl http://localhost:8080/bulk-data/
```

### 4. Set Up Pagolin Tunnel

```bash
# Install Pagolin (if not already installed)
# Follow: https://pagolin.com/docs/installation

# Start Pagolin tunnel
pagolin http 8080 --subdomain proxy-machine

# Pagolin will give you a URL like:
# https://proxy-machine.pagolin.com
```

### 5. Create Systemd Service

```bash
sudo nano /etc/systemd/system/proxy-data-server.service
```

```ini
[Unit]
Description=Proxy Machine Data Server
After=network.target tailscaled.service
Wants=tailscaled.service

[Service]
Type=simple
User=patrick
WorkingDirectory=/home/patrick/the-proxy-printer/proxy-machine
Environment="PATH=/home/patrick/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/patrick/.cargo/bin/uv run python serve_data.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable proxy-data-server
sudo systemctl start proxy-data-server
sudo systemctl status proxy-data-server
```

### 6. Set Up Pagolin Service (Optional)

```bash
sudo nano /etc/systemd/system/pagolin-tunnel.service
```

```ini
[Unit]
Description=Pagolin HTTPS Tunnel
After=network.target proxy-data-server.service
Wants=proxy-data-server.service

[Service]
Type=simple
User=patrick
ExecStart=/usr/local/bin/pagolin http 8080 --subdomain proxy-machine
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pagolin-tunnel
sudo systemctl start pagolin-tunnel
```

## Friend Setup (2 minutes per friend)

### Step 1: Join Tailscale Network

```bash
# Install Tailscale on their machine
curl -fsSL https://tailscale.com/install.sh | sh

# Join your network (you'll need to approve them)
sudo tailscale up
```

### Step 2: Configure Client

Create `.env` file:

```bash
cd ~/the-proxy-printer/proxy-machine

cat > .env << 'EOF'
# Use Pagolin URL (HTTPS, works everywhere)
PM_BULK_DATA_URL=https://proxy-machine.pagolin.com

# Or use Tailscale IP (faster, only works on Tailscale network)
# PM_BULK_DATA_URL=http://100.x.y.z:8080

# Disable Scryfall fallback prompts
PM_OFFLINE=0
PM_ASK_REFRESH=0
EOF

# Load environment
export $(cat .env | xargs)
```

### Step 3: Test

```bash
# Test connection
curl $PM_BULK_DATA_URL/bulk-data/

# Download bulk data
uv run python tools/fetch_bulk.py --id all-cards

# Build database
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# Verify
uv run python tools/verify.py
```

## Automated Updates

### Server-Side Update Script

```bash
nano ~/update-proxy-data.sh
```

```bash
#!/bin/bash
set -e

WORK_DIR=~/the-proxy-printer/proxy-machine
LOG_FILE=~/proxy-data-update.log

echo "[$(date)] Starting update..." | tee -a "$LOG_FILE"

cd "$WORK_DIR"
source .venv/bin/activate

# Download latest bulk data
echo "Downloading bulk data..." | tee -a "$LOG_FILE"
uv run python tools/fetch_bulk.py --id all-cards 2>&1 | tee -a "$LOG_FILE"
uv run python tools/fetch_bulk.py --id oracle-cards 2>&1 | tee -a "$LOG_FILE"
uv run python tools/fetch_bulk.py --id unique-artwork 2>&1 | tee -a "$LOG_FILE"

# Rebuild database
echo "Rebuilding database..." | tee -a "$LOG_FILE"
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)" 2>&1 | tee -a "$LOG_FILE"

# Optimize database
echo "Optimizing database..." | tee -a "$LOG_FILE"
uv run python tools/optimize_db.py all 2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] Update complete!" | tee -a "$LOG_FILE"

# Optional: Notify friends via Tailscale
# tailscale status --json | jq -r '.Peer[].HostName' | while read host; do
#     echo "Updated data available" | tailscale ssh "$host" wall
# done
```

Make executable and schedule:
```bash
chmod +x ~/update-proxy-data.sh

# Add to crontab (every Sunday at 3 AM)
crontab -e
# Add: 0 3 * * 0 /home/patrick/update-proxy-data.sh
```

## Monitoring

### Check Server Status

```bash
# Check services
sudo systemctl status proxy-data-server
sudo systemctl status pagolin-tunnel

# Check Tailscale connectivity
tailscale status

# View logs
sudo journalctl -u proxy-data-server -f
sudo journalctl -u pagolin-tunnel -f

# Check connected friends
tailscale status | grep -v "^#"
```

### Monitor Bandwidth

```bash
# Install vnstat
sudo apt install -y vnstat

# Monitor usage
vnstat -l
vnstat -d
```

## Advantages of This Setup

### For You (Server Admin)
- No port forwarding or firewall configuration
- No public IP exposure
- No certificate management (Pagolin handles it)
- Simple Python server (no nginx)
- Built-in access control (Tailscale)
- Easy to monitor who's connected

### For Friends (Clients)
- One-time Tailscale setup
- No authentication credentials to manage
- Works from anywhere (Pagolin)
- Fast local network speeds (Tailscale)
- Automatic HTTPS
- No complex configuration

## Troubleshooting

### Server not accessible via Tailscale

```bash
# Check Tailscale status
tailscale status

# Check if service is running
sudo systemctl status proxy-data-server

# Test locally first
curl http://localhost:8080/bulk-data/

# Check firewall (shouldn't be needed with Tailscale)
sudo ufw status
```

### Pagolin tunnel not working

```bash
# Check Pagolin status
sudo systemctl status pagolin-tunnel

# Restart tunnel
sudo systemctl restart pagolin-tunnel

# Check logs
sudo journalctl -u pagolin-tunnel -n 50
```

### Friend can't connect

```bash
# On friend's machine, check Tailscale
tailscale status

# Ping your server
ping $(tailscale ip -4 your-server-hostname)

# Test HTTP connection
curl http://$(tailscale ip -4 your-server-hostname):8080/bulk-data/
```

### Slow downloads

```bash
# Use Tailscale direct connection (faster than Pagolin)
PM_BULK_DATA_URL=http://$(tailscale ip -4 your-server-hostname):8080

# Check Tailscale connection type
tailscale status --json | jq '.Peer[] | {name: .HostName, relay: .Relay}'

# If using relay, try to establish direct connection
tailscale ping your-server-hostname
```

## Security Considerations

### Tailscale Network
- Only approved devices can join
- End-to-end encrypted
- No public internet exposure
- Audit access via Tailscale admin console

### Access Control
```bash
# List connected devices
tailscale status

# Remove a device (from admin console)
# Visit: https://login.tailscale.com/admin/machines

# Enable key expiry for temporary access
tailscale up --auth-key=<key> --timeout=24h
```

### Data Privacy
- Bulk data is public Scryfall data (no privacy concerns)
- No user data or credentials stored
- All traffic encrypted via Tailscale/Pagolin

## Cost Analysis

### Your Costs
- Tailscale: FREE (up to 100 devices)
- Pagolin: FREE tier or ~$5/month for custom domain
- Server: $5-10/month (same as before)
- Total: $5-15/month for unlimited friends

### Friend Costs
- Tailscale: FREE
- No bandwidth costs (uses your server)
- Total: $0/month

### Bandwidth Savings
- 10 friends × 2.5GB initial = 25GB saved from Scryfall
- Weekly updates: ~5GB/week saved
- Scryfall stays happy, your friends get faster downloads

## Advanced: Custom Domain with Pagolin

```bash
# Use your own domain
pagolin http 8080 --custom-domain proxy.yourdomain.com

# Update DNS (CNAME record)
# proxy.yourdomain.com -> your-app.pagolin.com

# Friends use:
PM_BULK_DATA_URL=https://proxy.yourdomain.com
```

## Comparison: Tailscale vs Public Server

| Feature | Tailscale + Pagolin | Public Nginx |
|---------|---------------------|--------------|
| Setup time | 10 minutes | 30+ minutes |
| Port forwarding | Not needed | Required |
| HTTPS setup | Automatic | Manual (certbot) |
| Firewall config | Not needed | Required |
| Access control | Built-in | Manual (htpasswd) |
| Security | Excellent | Good (if configured) |
| Works behind NAT | Yes | No |
| Friend setup | 2 minutes | 5+ minutes |
| Maintenance | Minimal | Regular updates |

## Next Steps

1. Set up Tailscale on your server
2. Start the Python file server
3. Set up Pagolin tunnel (optional, for non-Tailscale access)
4. Invite friends to Tailscale network
5. Share the Pagolin URL or Tailscale IP
6. Friends configure `PM_BULK_DATA_URL` and start using

## Support Resources

- Tailscale docs: https://tailscale.com/kb
- Pagolin docs: https://pagolin.com/docs
- This project: See `UBUNTU_DEPLOYMENT.md` for server setup
