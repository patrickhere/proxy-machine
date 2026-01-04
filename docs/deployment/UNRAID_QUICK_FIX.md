# Unraid Deployment - Quick Fix Guide

If you're seeing this error:
```
failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
```

This means your docker-compose.yml is trying to build from source, but the files aren't there. Here's how to fix it:

## Option 1: Clone the Repository First (Recommended)

```bash
# SSH into your Unraid server
ssh root@YOUR-UNRAID-IP

# Navigate to appdata
cd /mnt/user/appdata

# Clone the repository
git clone https://github.com/patrickhere/proxy-machine.git
cd proxy-machine

# Now run docker-compose
docker-compose up -d
```

## Option 2: Use Pre-Built Image (Coming Soon)

Update your `docker-compose.yml` to use a pre-built image:

```yaml
version: '3.8'

services:
  proxy-machine:
    image: ghcr.io/patrickhere/proxy-machine:latest  # Use this instead of build
    # Remove the "build: ." line
    container_name: proxy-machine
    restart: unless-stopped

    # ... rest of config stays the same
```

## Option 3: Manual Docker Build

If you've already cloned the repo:

```bash
cd /mnt/user/appdata/proxy-machine

# Build the image
docker build -t proxy-machine:latest .

# Update docker-compose.yml to use local image
# Change "build: ." to "image: proxy-machine:latest"

# Start container
docker-compose up -d
```

## Quick Start (Easiest Method)

```bash
# SSH to Unraid
ssh root@YOUR-UNRAID-IP

# Create directory and clone
mkdir -p /mnt/user/appdata
cd /mnt/user/appdata
git clone https://github.com/patrickhere/proxy-machine.git proxy-machine
cd proxy-machine

# Start it up
docker-compose up -d

# Check logs
docker logs -f proxy-machine
```

## Verify It's Running

```bash
# Check container status
docker ps | grep proxy-machine

# View logs
docker logs proxy-machine

# Access dashboard
# Open browser: http://YOUR-UNRAID-IP:5001
```

## Troubleshooting

**If git isn't installed on Unraid:**
```bash
# Install Nerd Tools plugin from Community Applications
# Or manually download the repo as ZIP and extract
```

**If port 5001 is in use:**
Edit docker-compose.yml and change:
```yaml
ports:
  - "5002:5001"  # Use 5002 instead
```

## Update Container

```bash
cd /mnt/user/appdata/proxy-machine
git pull
docker-compose down
docker-compose up -d --build
```

---

**Need help?** Check the full guide: `docs/deployment/UNRAID_COMPLETE_GUIDE.md`
