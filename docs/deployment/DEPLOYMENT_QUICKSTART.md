# Deployment Quick Start

## RECOMMENDED: Tailscale + Pagolin Setup (10 minutes)

**Easiest option for sharing with friends!**

```bash
# 1. Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 2. Run automated setup
cd ~/the-proxy-printer/proxy-machine
./setup-tailscale-server.sh

# 3. Share with friends
# Give them your Tailscale IP: $(tailscale ip -4)
# They run: ./setup-friend-client.sh
```

**Advantages:**
- No port forwarding or firewall config
- Automatic HTTPS with Pagolin
- Private network (Tailscale)
- 2-minute friend setup
- Works behind NAT/CGNAT

**Full guide:** See `TAILSCALE_DEPLOYMENT.md`

---

## Alternative: Ubuntu Server Setup (5 minutes)

```bash
# 1. Install dependencies
sudo apt update && sudo apt install -y python3 python3-pip curl git \
    libjpeg-dev libpng-dev libopencv-dev sqlite3

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# 3. Clone and setup
git clone <repo-url> ~/the-proxy-printer
cd ~/the-proxy-printer/proxy-machine
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt

# 4. Download data and build database
uv run python tools/fetch_bulk.py --id all-cards
uv run python tools/fetch_bulk.py --id oracle-cards
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# 5. Verify
uv run python tools/verify.py
```

**Full guide:** See `UBUNTU_DEPLOYMENT.md`

---

## Self-Hosted Server Setup (10 minutes)

```bash
# 1. Install nginx
sudo apt install -y nginx

# 2. Create data directory
sudo mkdir -p /var/www/proxy-data/bulk-data
sudo chown -R $USER:$USER /var/www/proxy-data

# 3. Copy data
cp -r ~/the-proxy-printer/proxy-machine/bulk-data/* /var/www/proxy-data/bulk-data/

# 4. Configure nginx
sudo tee /etc/nginx/sites-available/proxy-data > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;
    root /var/www/proxy-data;
    autoindex on;

    location / {
        add_header 'Access-Control-Allow-Origin' '*' always;
        expires 7d;
        try_files $uri $uri/ =404;
    }
}
EOF

# 5. Enable and start
sudo ln -s /etc/nginx/sites-available/proxy-data /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# 6. Test
curl http://localhost/bulk-data/
```

**Full guide:** See `SELF_HOSTING.md`

---

## Client Configuration

Friends configure their clients to use your server:

```bash
# Create .env file
cat > .env << EOF
PM_BULK_DATA_URL=http://your-server-ip
PM_OFFLINE=0
EOF

# Load environment
export $(cat .env | xargs)
```

**Example code:** See `examples/custom_server_config.py`

---

## Cost Estimates

### Hosting Options

| Provider | Specs | Cost/month | Best for |
|----------|-------|------------|----------|
| DigitalOcean | 1 CPU, 2GB RAM, 50GB SSD | $12 | Small groups |
| Linode | 1 CPU, 2GB RAM, 50GB SSD | $12 | Small groups |
| Hetzner | 2 CPU, 4GB RAM, 40GB SSD | €4.50 (~$5) | Best value |
| Oracle Free Tier | 1 CPU, 1GB RAM, 50GB | FREE | Testing |

### Bandwidth Usage
- Initial setup: ~2.5GB per friend
- Weekly updates: ~500MB per friend
- 10 friends: ~25GB initial + ~5GB/week

---

## Architecture Diagram

```
┌─────────────────┐
│  Your Server    │
│  (Ubuntu)       │
│                 │
│  ┌───────────┐  │
│  │  Nginx    │  │◄─── HTTP requests
│  │  :80      │  │
│  └─────┬─────┘  │
│        │        │
│  ┌─────▼─────┐  │
│  │ /var/www/ │  │
│  │ proxy-data│  │
│  │           │  │
│  │ ├─bulk-   │  │
│  │ ├─tokens  │  │
│  │ └─lands   │  │
│  └───────────┘  │
└─────────────────┘
        ▲
        │
        │ HTTP GET
        │
┌───────┴────────┐
│  Friend's PC   │
│                │
│  create_pdf.py │
│  ↓             │
│  bulk_paths.py │
│  ↓             │
│  PM_BULK_DATA_ │
│  URL env var   │
└────────────────┘
```

---

## Troubleshooting

### Server not accessible
```bash
# Check nginx status
sudo systemctl status nginx

# Check firewall
sudo ufw status
sudo ufw allow 80/tcp
```

### Permission errors
```bash
sudo chown -R www-data:www-data /var/www/proxy-data
sudo chmod -R 755 /var/www/proxy-data
```

### Database locked
```bash
# Check for processes
lsof ~/the-proxy-printer/proxy-machine/bulk-data/bulk.db

# Enable WAL mode for concurrent access
sqlite3 bulk-data/bulk.db "PRAGMA journal_mode=WAL;"
```

---

## Next Steps

1. **Security:** Add HTTPS with Let's Encrypt
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

2. **Monitoring:** Set up basic monitoring
   ```bash
   sudo apt install vnstat
   vnstat -l  # Monitor bandwidth
   ```

3. **Automation:** Schedule weekly updates
   ```bash
   crontab -e
   # Add: 0 3 * * 0 /path/to/update-script.sh
   ```

4. **Backups:** Backup database daily
   ```bash
   # See SELF_HOSTING.md for backup script
   ```

---

## Support

- **Ubuntu issues:** See `UBUNTU_DEPLOYMENT.md`
- **Server setup:** See `SELF_HOSTING.md`
- **Code integration:** See `examples/custom_server_config.py`
- **Project docs:** See `PROJECT_OVERVIEW.md`
