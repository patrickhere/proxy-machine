# Unraid Deployment Guide - Complete

Complete guide for deploying The Proxy Machine on Unraid with Tailscale support and configurable storage paths.

---

## Quick Start

### Prerequisites
- Unraid 6.9 or later
- Community Applications plugin installed
- Docker enabled on Unraid

### Installation Steps

1. **Create appdata directory**
```bash
mkdir -p /mnt/user/appdata/proxy-machine
cd /mnt/user/appdata/proxy-machine
```

2. **Create docker-compose.yml** (see below)

3. **Start container**
```bash
docker-compose up -d
```

4. **Access dashboard**
```
http://YOUR-UNRAID-IP:5001
```

---

## docker-compose.yml

Create `/mnt/user/appdata/proxy-machine/docker-compose.yml`:

```yaml
version: '3.8'

services:
  proxy-machine:
    image: ghcr.io/patrickhere/proxy-machine:latest
    container_name: proxy-machine
    restart: unless-stopped

    # Required for Tailscale
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    devices:
      - /dev/net/tun:/dev/net/tun

    ports:
      - "5001:5001"

    environment:
      # Web Server
      - WEB_HOST=0.0.0.0
      - WEB_PORT=5001
      - LOG_LEVEL=INFO

      # Performance (tune for your hardware)
      - MAX_DOWNLOAD_WORKERS=16
      - DEFAULT_PPI=1200
      - DB_CACHE_SIZE_MB=500

      # Paths (don't change these)
      - PROXY_MACHINE_ROOT=/app
      - SHARED_ROOT=/data/shared
      - PROFILES_ROOT=/data/profiles
      - BULK_DATA_DIR=/data/bulk-data
      - PDF_OUTPUT_DIR=/data/pdfs

      # Tailscale (optional - see below)
      - TAILSCALE_ENABLED=false
      # - TAILSCALE_AUTHKEY=tskey-auth-xxxx
      # - TAILSCALE_HOSTNAME=proxy-machine

    volumes:
      # Map to Unraid appdata
      - /mnt/user/appdata/proxy-machine/shared:/data/shared
      - /mnt/user/appdata/proxy-machine/profiles:/data/profiles
      - /mnt/user/appdata/proxy-machine/bulk-data:/data/bulk-data
      - /mnt/user/appdata/proxy-machine/pdfs:/data/pdfs
      - /mnt/user/appdata/proxy-machine/logs:/app/logs
      - /mnt/user/appdata/proxy-machine/tailscale:/var/lib/tailscale

networks:
  proxy-machine-net:
    driver: bridge
```

---

## Tailscale Setup (Remote Access)

### 1. Generate Auth Key
1. Go to https://login.tailscale.com/admin/settings/keys
2. Click "Generate auth key"
3. Enable "Reusable" (allows restarts)
4. Copy the key (starts with `tskey-auth-`)

### 2. Update docker-compose.yml
```yaml
environment:
  - TAILSCALE_ENABLED=true
  - TAILSCALE_AUTHKEY=tskey-auth-YOUR-KEY-HERE
  - TAILSCALE_HOSTNAME=proxy-machine
```

### 3. Restart container
```bash
docker-compose down && docker-compose up -d
```

### 4. Verify connection
```bash
docker logs proxy-machine | grep Tailscale
# Should show: "Tailscale connected successfully!"
```

### 5. Access remotely
From any device on your Tailscale network:
```
http://proxy-machine:5001
```

---

## Environment Variables

### Application Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_PORT` | `5001` | Dashboard port |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |

### Performance Tuning
| Variable | Default | Recommended for Unraid |
|----------|---------|------------------------|
| `MAX_DOWNLOAD_WORKERS` | `8` | `16` (more CPU/network) |
| `DEFAULT_PPI` | `600` | `1200` (higher quality) |
| `DB_CACHE_SIZE_MB` | `200` | `500` (more RAM = faster) |

### Tailscale
| Variable | Required | Description |
|----------|----------|-------------|
| `TAILSCALE_ENABLED` | No | `true` to enable VPN |
| `TAILSCALE_AUTHKEY` | Yes* | Auth key from Tailscale |
| `TAILSCALE_HOSTNAME` | No | Custom hostname |

*Required if TAILSCALE_ENABLED=true

---

## Storage Configuration

### Default Paths (Unraid appdata)
```
/mnt/user/appdata/proxy-machine/
├── shared/         # Card library (5-10GB)
├── profiles/       # User profiles
├── bulk-data/      # Scryfall DB (3GB)
├── pdfs/           # Generated PDFs
├── logs/           # Application logs
└── tailscale/      # Tailscale state
```

### Custom Paths (Optional)

To use different storage locations, modify volumes in docker-compose.yml:

```yaml
volumes:
  # Use custom share for card library
  - /mnt/user/mtg-proxies/shared:/data/shared
  - /mnt/user/mtg-proxies/profiles:/data/profiles

  # Keep database on SSD cache
  - /mnt/cache/appdata/proxy-machine/bulk-data:/data/bulk-data

  # Store PDFs on array
  - /mnt/user/documents/proxy-pdfs:/data/pdfs
```

### Network Share Access

To access files from Windows/Mac:

1. Mount to user share:
```yaml
volumes:
  - /mnt/user/mtg-proxies:/data/shared
```

2. Access via network:
```
\\TOWER\mtg-proxies\
```

---

## First-Time Setup

### 1. Start container
```bash
cd /mnt/user/appdata/proxy-machine
docker-compose up -d
```

### 2. Check logs
```bash
docker logs -f proxy-machine
```

### 3. Download Scryfall database
Option A - Web dashboard:
```
http://UNRAID-IP:5001
→ Admin → Download Database
```

Option B - CLI:
```bash
docker exec proxy-machine make bulk-sync
```

Takes 5-10 minutes, downloads ~2.3GB.

### 4. Create your profile
```bash
docker exec -it proxy-machine make menu
# Navigate to: Profiles → Initialize → Enter your name
```

---

## Maintenance

### Update Container
```bash
cd /mnt/user/appdata/proxy-machine
docker-compose pull
docker-compose up -d
```

### Update Database
Run monthly to get new cards:
```bash
docker exec proxy-machine make bulk-sync
```

### View Logs
```bash
# Live logs
docker logs -f proxy-machine

# Log files
tail -f /mnt/user/appdata/proxy-machine/logs/*.log
```

### Backup Important Data
```bash
# Backup these directories
/mnt/user/appdata/proxy-machine/profiles/    # Your decks
/mnt/user/appdata/proxy-machine/shared/      # Card library
/mnt/user/appdata/proxy-machine/bulk-data/   # Database
```

---

## Troubleshooting

### Container won't start

**Check logs:**
```bash
docker logs proxy-machine
```

**Common fixes:**
```bash
# Fix permissions
chmod -R 755 /mnt/user/appdata/proxy-machine

# Check if port is in use
netstat -tulpn | grep 5001

# Verify Docker is running
docker ps
```

### Can't access web dashboard

1. Verify container is running: `docker ps | grep proxy-machine`
2. Check Unraid network settings
3. Try local access: `http://localhost:5001`
4. Check firewall rules

### Tailscale not connecting

**Verify capabilities:**
```bash
docker inspect proxy-machine | grep -A 5 CapAdd
# Should show: NET_ADMIN, SYS_MODULE
```

**Check device:**
```bash
docker exec proxy-machine ls -la /dev/net/tun
# Should exist
```

**View Tailscale status:**
```bash
docker exec proxy-machine tailscale status
```

**Check auth key:**
- Verify key hasn't expired in Tailscale admin
- Ensure "Reusable" was enabled when creating key

### Database errors

**Rebuild database:**
```bash
docker exec proxy-machine make bulk-sync
```

**Check disk space:**
```bash
df -h /mnt/user/appdata/proxy-machine
# Need 3GB+ free
```

---

## Performance Optimization

### For Powerful Servers

```yaml
environment:
  # Max out workers
  - MAX_DOWNLOAD_WORKERS=32

  # Huge cache
  - DB_CACHE_SIZE_MB=1000

  # Highest quality
  - DEFAULT_PPI=1200
```

### Resource Limits

Prevent runaway resource usage:

```yaml
deploy:
  resources:
    limits:
      cpus: '8'
      memory: 8G
    reservations:
      cpus: '2'
      memory: 2G
```

### SSD Cache Optimization

Put database on SSD for faster queries:

```yaml
volumes:
  - /mnt/cache/appdata/proxy-machine/bulk-data:/data/bulk-data
```

---

## Advanced: Reverse Proxy

### Nginx Proxy Manager

1. Install NPM from Community Applications
2. Create proxy host:
   - Domain: `proxies.yourdomain.com`
   - Forward Hostname: `proxy-machine`
   - Forward Port: `5001`
   - Enable SSL

3. Access via HTTPS:
```
https://proxies.yourdomain.com
```

### Traefik Labels

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.proxy-machine.rule=Host(`proxies.local`)"
  - "traefik.http.services.proxy-machine.loadbalancer.server.port=5001"
```

---

## Security Best Practices

1. **Use Tailscale** instead of port forwarding
2. **Don't expose port 5001** to the internet
3. **Use reverse proxy** with SSL for local network access
4. **Regular backups** of profiles and shared library
5. **Keep container updated** for security patches

---

## Support & Resources

- **Documentation**: `/mnt/user/appdata/proxy-machine/docs/`
- **Logs**: `/mnt/user/appdata/proxy-machine/logs/`
- **GitHub Issues**: https://github.com/patrickhere/proxy-machine/issues
- **Unraid Forums**: Search for "Proxy Machine"

---

## Quick Reference Commands

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Restart
docker-compose restart

# Update
docker-compose pull && docker-compose up -d

# Logs
docker logs -f proxy-machine

# Shell access
docker exec -it proxy-machine bash

# Run CLI
docker exec -it proxy-machine make menu

# Download database
docker exec proxy-machine make bulk-sync

# Check Tailscale
docker exec proxy-machine tailscale status
```

---

**Happy proxy printing from Unraid!** 🎴✨
