# Deploying Proxy Machine on Unraid

Complete guide for deploying Proxy Machine as a Docker container on Unraid with Tailscale integration.

---

## Prerequisites

- Unraid 6.9 or later
- Community Applications plugin installed
- (Optional) Tailscale plugin for remote access

---

## Quick Setup

### 1. Prepare Directory Structure

On your Unraid server, create the following directories:

```bash
mkdir -p /mnt/user/appdata/proxy-machine/shared
mkdir -p /mnt/user/appdata/proxy-machine/profiles
mkdir -p /mnt/user/appdata/proxy-machine/bulk-data
```

### 2. Copy Project Files

Transfer the `proxy-machine` directory to your Unraid server:

```bash
# From your local machine
rsync -avz /path/to/proxy-machine/ root@unraid-server:/mnt/user/appdata/proxy-machine/app/
```

Or clone directly on Unraid:

```bash
cd /mnt/user/appdata/proxy-machine/
git clone <your-repo-url> app
```

### 3. Configure Environment

Copy the example environment file and customize:

```bash
cd /mnt/user/appdata/proxy-machine/app
cp .env.example .env
nano .env
```

Key settings for Unraid:

```bash
# Web server - allow external access
WEB_HOST=0.0.0.0
WEB_PORT=5001

# Paths - use /data/* which will be mapped by Docker
PROXY_MACHINE_ROOT=/app
SHARED_ROOT=/data/shared
PROFILES_ROOT=/data/profiles
BULK_DATA_DIR=/data/bulk-data
```

### 4. Build Docker Container

```bash
cd /mnt/user/appdata/proxy-machine/app
docker build -t proxy-machine:latest .
```

### 5. Deploy Container

#### Option A: Using docker-compose

```bash
cd /mnt/user/appdata/proxy-machine/app
docker-compose up -d
```

#### Option B: Docker Run Command

```bash
docker run -d \
  --name proxy-machine \
  --restart unless-stopped \
  -p 5001:5001 \
  -v /mnt/user/appdata/proxy-machine/shared:/data/shared \
  -v /mnt/user/appdata/proxy-machine/profiles:/data/profiles \
  -v /mnt/user/appdata/proxy-machine/bulk-data:/data/bulk-data \
  -e WEB_HOST=0.0.0.0 \
  -e WEB_PORT=5001 \
  proxy-machine:latest
```

#### Option C: Unraid Template (Recommended)

Create a custom template in Unraid's Docker tab:

```xml
<?xml version="1.0"?>
<Container version="2">
  <Name>proxy-machine</Name>
  <Repository>proxy-machine:latest</Repository>
  <Registry>local</Registry>
  <Network>bridge</Network>
  <WebUI>http://[IP]:[PORT:5001]</WebUI>
  <ExtraParams>--restart unless-stopped</ExtraParams>
  <Config Name="Web Port" Target="5001" Default="5001" Mode="tcp" Description="Web interface port" Type="Port" Display="always" Required="true" Mask="false">5001</Config>
  <Config Name="Shared Assets" Target="/data/shared" Default="/mnt/user/appdata/proxy-machine/shared" Mode="rw" Description="Shared card assets" Type="Path" Display="always" Required="true" Mask="false">/mnt/user/appdata/proxy-machine/shared</Config>
  <Config Name="User Profiles" Target="/data/profiles" Default="/mnt/user/appdata/proxy-machine/profiles" Mode="rw" Description="User deck profiles" Type="Path" Display="always" Required="true" Mask="false">/mnt/user/appdata/proxy-machine/profiles</Config>
  <Config Name="Bulk Data" Target="/data/bulk-data" Default="/mnt/user/appdata/proxy-machine/bulk-data" Mode="rw" Description="Scryfall database" Type="Path" Display="always" Required="true" Mask="false">/mnt/user/appdata/proxy-machine/bulk-data</Config>
</Container>
```

### 6. Initial Database Setup

SSH into your container and run the initial bulk sync:

```bash
docker exec -it proxy-machine bash
cd /app
uv run python create_pdf.py --bulk_sync
```

This will download ~3GB of Scryfall data and build the database (takes 5-10 minutes).

### 7. Access Web Interface

- Local: `http://your-unraid-ip:5001`
- Tailscale: `http://your-tailscale-hostname:5001` (after Tailscale setup)

---

## Tailscale Integration

### Setup Tailscale Access

1. **Install Tailscale on Unraid**:
   - Install the "Tailscale" plugin from Community Applications
   - Configure and authenticate your Tailscale account

2. **Configure Tailscale Serve** (Optional):

```bash
# On your Unraid server
tailscale serve --bg --https=443 5001
```

This exposes Proxy Machine on your Tailscale network at `https://unraid-hostname:443`

3. **Update Environment** (Optional):

```bash
# In .env file
TAILSCALE_ENABLED=true
TAILSCALE_HOSTNAME=your-unraid-tailscale-name
```

---

## Volume Mappings Reference

| Container Path | Unraid Path | Purpose | Size |
|---------------|-------------|---------|------|
| `/data/shared` | `/mnt/user/appdata/proxy-machine/shared` | Card assets (tokens, lands) | ~5GB+ |
| `/data/profiles` | `/mnt/user/appdata/proxy-machine/profiles` | User decks and PDFs | Variable |
| `/data/bulk-data` | `/mnt/user/appdata/proxy-machine/bulk-data` | Scryfall database | ~3GB |

---

## Port Configuration

| Port | Protocol | Purpose |
|------|----------|---------|
| 5001 | TCP | Web interface |

---

## Updating

### Pull Latest Code

```bash
cd /mnt/user/appdata/proxy-machine/app
git pull
docker stop proxy-machine
docker rm proxy-machine
docker build -t proxy-machine:latest .
docker-compose up -d  # or use docker run command
```

### Update Database

```bash
docker exec -it proxy-machine bash
cd /app
uv run python create_pdf.py --bulk_sync
```

---

## Backup Strategy

### What to Backup

1. **User Data** (Essential):
   - `/mnt/user/appdata/proxy-machine/profiles` - User decks and PDFs
   - `/mnt/user/appdata/proxy-machine/shared` - Downloaded card assets

2. **Database** (Optional - can rebuild):
   - `/mnt/user/appdata/proxy-machine/bulk-data` - Scryfall database

### Automated Backup

Use Unraid's built-in backup plugins:
- **CA Backup / Restore Appdata** - Backs up entire appdata folders
- Schedule weekly backups of `/mnt/user/appdata/proxy-machine/`

---

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs proxy-machine
```

Common issues:
- Volume permissions: Ensure `/mnt/user/appdata/proxy-machine/` is readable/writable
- Port conflict: Make sure port 5001 isn't already in use
- Memory: Ensure Unraid has enough RAM (4GB+ recommended)

### Web Interface Not Accessible

1. Check if container is running: `docker ps`
2. Verify port binding: `docker port proxy-machine`
3. Check firewall rules (if using custom firewall)
4. Verify WEB_HOST=0.0.0.0 in environment

### Database Issues

Rebuild database:
```bash
docker exec -it proxy-machine bash
cd /app
rm -f /data/bulk-data/bulk-index.db
uv run python create_pdf.py --bulk_sync
```

### Performance Issues

- Increase Docker memory limit in Unraid settings
- Move `/data/bulk-data` to SSD cache drive for faster queries
- Reduce concurrent download workers if network is saturated

---

## Security Considerations

### Network Security

- Proxy Machine is designed for private network use
- No authentication is built-in - rely on network-level security
- For internet exposure, use:
  - Tailscale (recommended) - encrypted, zero-trust networking
  - Reverse proxy with authentication (Nginx Proxy Manager, Traefik)
  - VPN access only

### File Access

- Container runs as root (standard for Docker)
- Uses bind mounts - files owned by container user
- Consider using Docker user namespacing for production

---

## Advanced Configuration

### Custom Profiles Path

If you want profiles on a different drive:

```bash
# docker-compose.yml
volumes:
  - /mnt/disk2/mtg-decks:/data/profiles  # Custom location
```

### Resource Limits

Add resource constraints to docker-compose.yml:

```yaml
services:
  proxy-machine:
    # ... other config ...
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          memory: 2G
```

### Environment Variables

See `.env.example` for all available configuration options.

---

## Support

- Check logs: `docker logs proxy-machine`
- GitHub Issues: [Project URL]
- Unraid Forums: [Link to thread if created]

---

## Next Steps

After deployment:
1. Access web interface at `http://unraid-ip:5001`
2. Create a user profile
3. Upload card images or import a deck list
4. Generate your first PDF!
