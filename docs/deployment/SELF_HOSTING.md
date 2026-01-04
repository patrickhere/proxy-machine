# Self-Hosting Shared Data Guide

This guide covers setting up a self-hosted server to share bulk data, tokens, and card images with friends.

## Overview

Instead of each user downloading ~2.5GB of bulk data from Scryfall, you can:
1. Host a central server with shared data
2. Configure clients to fetch from your server first
3. Fall back to Scryfall if needed
4. Reduce bandwidth and improve download speeds for your group

## Architecture Options

### Option 1: Simple Static File Server (Recommended)
**Best for:** Small groups (2-10 friends), simple setup, low maintenance

- Uses nginx to serve static files
- No authentication needed (or basic auth)
- Clients use HTTP GET requests
- Easy to set up and maintain

### Option 2: Object Storage (MinIO)
**Best for:** Larger groups, need versioning, want S3-compatible API

- Self-hosted S3-compatible storage
- Built-in versioning and replication
- Web UI for management
- More complex setup

### Option 3: Flask/FastAPI Wrapper
**Best for:** Need custom features, search API, authentication

- Python web service wrapping static files
- Can add search, filtering, metadata endpoints
- Custom authentication and rate limiting
- Most flexible but requires maintenance

## Recommended Setup: Nginx Static File Server

### 1. Install Nginx

```bash
sudo apt update
sudo apt install -y nginx
```

### 2. Create Data Directory Structure

```bash
# Create directory for shared data
sudo mkdir -p /var/www/proxy-data
sudo chown -R $USER:$USER /var/www/proxy-data

# Create subdirectories matching project structure
mkdir -p /var/www/proxy-data/{bulk-data,tokens,basic-lands,non-basic-lands,card-backs}
```

### 3. Copy Data to Server

From your local machine (or build on server):

```bash
# Option A: Copy from local machine
rsync -avz --progress \
    ~/Documents/projects/the-proxy-printer/proxy-machine/bulk-data/ \
    user@your-server:/var/www/proxy-data/bulk-data/

rsync -avz --progress \
    ~/Documents/projects/the-proxy-printer/magic-the-gathering/shared/tokens/ \
    user@your-server:/var/www/proxy-data/tokens/

# Option B: Build on server (see UBUNTU_DEPLOYMENT.md)
# Then copy to nginx directory
cp -r ~/the-proxy-printer/proxy-machine/bulk-data/* /var/www/proxy-data/bulk-data/
```

### 4. Configure Nginx

Create nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/proxy-data
```

```nginx
server {
    listen 80;
    server_name your-domain.com;  # or IP address

    root /var/www/proxy-data;

    # Enable directory listing (optional)
    autoindex on;
    autoindex_exact_size off;
    autoindex_localtime on;

    # Logging
    access_log /var/log/nginx/proxy-data-access.log;
    error_log /var/log/nginx/proxy-data-error.log;

    # Main location
    location / {
        # CORS headers (allow cross-origin requests)
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;

        # Cache headers (1 week for bulk data)
        expires 7d;
        add_header Cache-Control "public, immutable";

        # Enable gzip compression
        gzip on;
        gzip_types application/json application/octet-stream;
        gzip_min_length 1000;

        # Try to serve file, return 404 if not found
        try_files $uri $uri/ =404;
    }

    # Bulk data endpoint
    location /bulk-data/ {
        alias /var/www/proxy-data/bulk-data/;

        # Longer cache for bulk files (they rarely change)
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Tokens endpoint
    location /tokens/ {
        alias /var/www/proxy-data/tokens/;
        expires 30d;
    }

    # Basic lands endpoint
    location /basic-lands/ {
        alias /var/www/proxy-data/basic-lands/;
        expires 30d;
    }

    # Health check endpoint
    location /health {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }
}
```

Enable the site:

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/proxy-data /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

### 5. Optional: Add Basic Authentication

```bash
# Install apache2-utils for htpasswd
sudo apt install -y apache2-utils

# Create password file
sudo htpasswd -c /etc/nginx/.htpasswd friend1
sudo htpasswd /etc/nginx/.htpasswd friend2

# Add to nginx config (inside location block)
auth_basic "Restricted Access";
auth_basic_user_file /etc/nginx/.htpasswd;
```

### 6. Optional: Enable HTTPS with Let's Encrypt

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate (requires domain name)
sudo certbot --nginx -d your-domain.com

# Auto-renewal is set up automatically
sudo certbot renew --dry-run
```

### 7. Create Update Script

Create a script to refresh data from Scryfall:

```bash
nano ~/update-proxy-data.sh
```

```bash
#!/bin/bash
set -e

WORK_DIR=~/the-proxy-printer/proxy-machine
DATA_DIR=/var/www/proxy-data
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

# Copy to nginx directory
echo "Copying to web directory..." | tee -a "$LOG_FILE"
rsync -av --delete bulk-data/ "$DATA_DIR/bulk-data/" 2>&1 | tee -a "$LOG_FILE"

# Update permissions
sudo chown -R www-data:www-data "$DATA_DIR"

echo "[$(date)] Update complete!" | tee -a "$LOG_FILE"
```

Make executable and schedule:

```bash
chmod +x ~/update-proxy-data.sh

# Add to crontab (every Sunday at 3 AM)
crontab -e
# Add: 0 3 * * 0 /home/your-username/update-proxy-data.sh
```

## Client Configuration

### Modify bulk_paths.py to Support Custom Server

Add environment variable support for custom bulk data URL:

```python
# In bulk_paths.py, add after imports:

CUSTOM_BULK_URL = os.environ.get("PM_BULK_DATA_URL")

def get_bulk_data_url(filename: str) -> str:
    """Get URL for bulk data file, preferring custom server."""
    if CUSTOM_BULK_URL:
        return f"{CUSTOM_BULK_URL.rstrip('/')}/{filename}"
    return f"https://api.scryfall.com/bulk-data/{filename}"
```

### Client .env Configuration

Friends configure their clients:

```bash
# .env file
PM_BULK_DATA_URL=http://your-server.com/bulk-data
PM_TOKENS_URL=http://your-server.com/tokens
PM_BASIC_LANDS_URL=http://your-server.com/basic-lands

# Optional: credentials if using basic auth
PM_SERVER_USER=friend1
PM_SERVER_PASS=password123
```

## Monitoring and Maintenance

### Check Server Status

```bash
# Nginx status
sudo systemctl status nginx

# Check logs
sudo tail -f /var/log/nginx/proxy-data-access.log

# Check disk usage
du -sh /var/www/proxy-data/*
```

### Monitor Bandwidth Usage

```bash
# Install vnstat
sudo apt install -y vnstat

# Monitor bandwidth
vnstat -l
vnstat -d  # daily stats
```

### Backup Strategy

```bash
# Create backup script
cat > ~/backup-proxy-data.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/backups/proxy-data
DATE=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"

# Backup database (most important)
cp /var/www/proxy-data/bulk-data/bulk.db "$BACKUP_DIR/bulk-$DATE.db"

# Compress and backup metadata
tar -czf "$BACKUP_DIR/metadata-$DATE.tar.gz" \
    /var/www/proxy-data/bulk-data/*.json \
    /var/www/proxy-data/bulk-data/*.json.gz

# Keep only last 7 days
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete

echo "Backup complete: $DATE"
EOF

chmod +x ~/backup-proxy-data.sh

# Schedule daily backups
crontab -e
# Add: 0 4 * * * /home/your-username/backup-proxy-data.sh
```

## Advanced: Flask API Wrapper (Optional)

For more control, wrap the static files with a Flask API:

```python
# server.py
from flask import Flask, send_from_directory, jsonify
from pathlib import Path
import os

app = Flask(__name__)
DATA_DIR = Path("/var/www/proxy-data")

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/bulk-data/<path:filename>')
def bulk_data(filename):
    return send_from_directory(DATA_DIR / "bulk-data", filename)

@app.route('/tokens/<path:filename>')
def tokens(filename):
    return send_from_directory(DATA_DIR / "tokens", filename)

@app.route('/api/manifest')
def manifest():
    """Return list of available files"""
    files = {
        "bulk_data": list((DATA_DIR / "bulk-data").glob("*")),
        "tokens": list((DATA_DIR / "tokens").glob("*"))
    }
    return jsonify({
        k: [str(f.name) for f in v]
        for k, v in files.items()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

Run with gunicorn:
```bash
uv pip install flask gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 server:app
```

## Cost Estimates

### Bandwidth
- Initial download per friend: ~2.5GB
- Weekly updates: ~500MB (only changed files)
- 10 friends: ~25GB initial + ~5GB/week

### Storage
- Bulk data: ~2.5GB
- Tokens (if hosting): ~500MB - 2GB
- Basic lands: ~100MB
- Total: ~3-5GB

### Server Requirements
- **Minimum:** 1 CPU, 2GB RAM, 10GB disk, 1TB bandwidth/month
- **Recommended:** 2 CPU, 4GB RAM, 20GB disk, 2TB bandwidth/month
- **Cost:** $5-10/month (DigitalOcean, Linode, Hetzner)

## Troubleshooting

### Issue: 403 Forbidden
```bash
# Check permissions
sudo chown -R www-data:www-data /var/www/proxy-data
sudo chmod -R 755 /var/www/proxy-data
```

### Issue: 502 Bad Gateway
```bash
# Check nginx status
sudo systemctl status nginx

# Check error logs
sudo tail -f /var/log/nginx/error.log
```

### Issue: Slow downloads
```bash
# Enable gzip in nginx config
# Increase worker_connections in /etc/nginx/nginx.conf
worker_connections 2048;
```

## Security Best Practices

1. **Use HTTPS** - Always encrypt traffic with Let's Encrypt
2. **Rate Limiting** - Prevent abuse with nginx rate limiting
3. **Firewall** - Only allow ports 80, 443, and SSH
4. **Updates** - Keep nginx and system packages updated
5. **Monitoring** - Set up alerts for disk space and bandwidth
6. **Backups** - Regular backups of database and metadata

## Next Steps

- Configure clients to use your server (modify fetch logic)
- Set up monitoring (Prometheus + Grafana)
- Consider CDN (Cloudflare) for better performance
- Add API for card search and filtering
