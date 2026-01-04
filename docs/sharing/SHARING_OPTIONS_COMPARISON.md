# Sharing Options Comparison

Complete comparison of all methods for sharing Proxy Machine data with friends.

## Quick Recommendation

**Best option: Samba (SMB) Network Share over Tailscale**

- Friends browse your files in Finder/Explorer
- Zero storage on their machines (unless they copy)
- 2-minute setup for friends
- Works on Mac, Windows, Linux
- Private and secure (Tailscale network)

## All Options

### Option 1: Samba Network Share (RECOMMENDED)

**What it is:** Friends mount your files as a network drive

**Setup:**
- You: Run `./setup-samba-share.sh` (5 minutes)
- Friends: Mount `smb://your-ip/ProxyMachine` (2 minutes)

**Friend's storage:** 0 bytes (browse only) to 3.5GB (copy everything)

**Pros:**
- Browse files in Finder/Explorer (native UI)
- Friends choose what to copy
- Zero to minimal storage
- Works on all platforms
- Read-only (safe)

**Cons:**
- Requires network connection
- Slightly slower than local files

**Best for:** Everyone! Most user-friendly option.

---

### Option 2: Remote Database API

**What it is:** Friends query your database via REST API

**Setup:**
- You: Run `uv run python remote_db_server.py` (instant)
- Friends: Set `PM_REMOTE_DB_URL` and use client script (2 minutes)

**Friend's storage:** ~10MB (just images for their decks)

**Pros:**
- Minimal storage (~10MB vs 3.5GB)
- Always up-to-date
- Programmatic access (good for automation)

**Cons:**
- Requires custom client code
- Not browsable in Finder/Explorer
- Network required

**Best for:** Technical users, automation, minimal storage

---

### Option 3: Simple HTTP File Server

**What it is:** Friends download files via HTTP

**Setup:**
- You: Run `uv run python serve_data.py` (instant)
- Friends: Download via curl or browser (5 minutes)

**Friend's storage:** 3.5GB (full download)

**Pros:**
- Simple setup
- Works with any HTTP client
- Can browse in web browser

**Cons:**
- Friends must download everything
- 3.5GB storage required
- Manual updates

**Best for:** One-time setup, friends want local copies

---

### Option 4: Each Friend Downloads from Scryfall

**What it is:** Traditional approach, everyone downloads independently

**Setup:**
- Friends: Run `uv run python tools/fetch_bulk.py` (30 minutes)

**Friend's storage:** 3.5GB

**Pros:**
- No server needed
- Fully offline
- No dependency on you

**Cons:**
- 3.5GB per friend
- Slow downloads (15-30 minutes)
- Hits Scryfall's servers
- Manual updates

**Best for:** Friends who want full independence

---

## Detailed Comparison

| Feature | Samba Share | Remote API | HTTP Server | Scryfall Direct |
|---------|-------------|------------|-------------|-----------------|
| **Setup time (you)** | 5 min | Instant | Instant | N/A |
| **Setup time (friend)** | 2 min | 2 min | 5 min | 30 min |
| **Friend storage** | 0-3.5GB | ~10MB | 3.5GB | 3.5GB |
| **Initial download** | None | None | 3.5GB | 3.5GB |
| **Browse in Finder** | Yes | No | No | No |
| **Works offline** | No | No | Yes | Yes |
| **Auto-updates** | Yes | Yes | Manual | Manual |
| **Bandwidth (10 friends)** | 0-35GB | ~100MB | 35GB | 35GB |
| **Your bandwidth saved** | 35GB | 34.9GB | 0GB | 0GB |
| **Platform support** | All | All | All | All |
| **Technical skill** | Low | Medium | Low | Low |
| **Network required** | Yes | Yes | No | No |

## Storage Breakdown

### Your Server (All Options)
- Bulk data: 3.5GB
- Database: 1GB
- Total: ~4.5GB

### Friend's Machine

**Samba Share:**
- Browse only: 0 bytes
- Copy database: 1GB
- Copy everything: 3.5GB
- **Typical: 0-1GB**

**Remote API:**
- Client code: <1MB
- Cached images: ~10MB per deck
- **Typical: ~10-50MB**

**HTTP Server:**
- Full download: 3.5GB
- **Fixed: 3.5GB**

**Scryfall Direct:**
- Full download: 3.5GB
- **Fixed: 3.5GB**

## Bandwidth Usage

### Initial Setup (10 friends)

| Option | Your Upload | Friend Download | Scryfall Load |
|--------|-------------|-----------------|---------------|
| Samba (browse only) | ~0GB | ~0GB | 0GB |
| Samba (copy DB) | ~10GB | ~1GB each | 0GB |
| Remote API | ~100MB | ~10MB each | 0GB |
| HTTP Server | ~35GB | ~3.5GB each | 0GB |
| Scryfall Direct | 0GB | ~3.5GB each | 35GB |

### Weekly Updates (10 friends)

| Option | Your Upload | Friend Download |
|--------|-------------|-----------------|
| Samba | ~5GB | ~500MB each |
| Remote API | ~50MB | ~5MB each |
| HTTP Server | ~35GB | ~3.5GB each |
| Scryfall Direct | 0GB | ~3.5GB each |

## Speed Comparison

### Initial Setup Time

| Option | Time |
|--------|------|
| Samba (browse only) | 2 minutes |
| Samba (copy DB) | 5 minutes |
| Remote API | 2 minutes |
| HTTP Server | 15-30 minutes |
| Scryfall Direct | 15-30 minutes |

### Query Performance

| Option | Query Speed |
|--------|-------------|
| Local database | <1ms |
| Samba (remote DB) | 10-50ms |
| Remote API | 5-20ms |
| HTTP (local DB) | <1ms |

## Use Case Recommendations

### Casual User (Makes proxies occasionally)
**Recommendation: Samba Share (browse only)**
- Mount the share
- Browse files as needed
- Copy images for specific decks
- Storage: ~10-100MB

### Power User (Makes many decks)
**Recommendation: Samba Share (copy database)**
- Mount the share
- Copy database to local disk
- Query locally for speed
- Storage: ~1GB

### Technical User (Automation, scripts)
**Recommendation: Remote API**
- Use API for programmatic access
- Cache frequently used data
- Minimal storage
- Storage: ~10-50MB

### Offline User (No reliable network)
**Recommendation: HTTP Server or Scryfall Direct**
- Download everything once
- Fully offline capable
- Storage: 3.5GB

### Independent User (Doesn't want to rely on you)
**Recommendation: Scryfall Direct**
- Download from Scryfall
- No dependency on your server
- Storage: 3.5GB

## Security Comparison

| Option | Network | Authentication | Encryption | Exposure |
|--------|---------|----------------|------------|----------|
| Samba | Tailscale | Guest (none) | Yes (Tailscale) | Private |
| Remote API | Tailscale | None | Yes (Tailscale) | Private |
| HTTP Server | Tailscale | None | Yes (Tailscale) | Private |
| Scryfall | Internet | None | Yes (HTTPS) | Public |

All Tailscale options are equally secure - private network, encrypted, device approval required.

## Cost Analysis (10 Friends)

### Your Costs

| Option | Server | Bandwidth | Total/Month |
|--------|--------|-----------|-------------|
| Samba | $5-10 | ~$0 | $5-10 |
| Remote API | $5-10 | ~$0 | $5-10 |
| HTTP Server | $5-10 | ~$0 | $5-10 |
| Scryfall | $0 | $0 | $0 |

**Note:** Tailscale is free (up to 100 devices)

### Friend Costs

All options: $0/month (Tailscale is free)

### Bandwidth Savings (vs Scryfall)

| Option | Initial | Weekly | Annual |
|--------|---------|--------|--------|
| Samba | 35GB | 5GB | 295GB |
| Remote API | 34.9GB | 5GB | 294.9GB |
| HTTP Server | 0GB | 0GB | 0GB |

**Scryfall appreciates not getting hit with 35GB × 10 friends!**

## Setup Scripts

All options have automated setup scripts:

- `setup-samba-share.sh` - Samba network share
- `remote_db_server.py` - Remote API server
- `serve_data.py` - Simple HTTP server
- `setup-tailscale-server.sh` - All-in-one Tailscale setup

## Final Recommendation

**For most users: Samba Network Share**

Reasons:
1. **User-friendly** - Browse in Finder/Explorer (familiar UI)
2. **Flexible** - Friends choose what to copy (0 bytes to 3.5GB)
3. **Fast setup** - 2 minutes for friends
4. **Cross-platform** - Works on Mac, Windows, Linux
5. **Secure** - Tailscale private network, read-only access
6. **Low maintenance** - You update once, everyone sees changes

**Alternative for technical users: Remote API**
- Minimal storage (~10MB)
- Programmatic access
- Good for automation

**Alternative for offline users: HTTP Server + Full Download**
- Fully offline capable
- No network dependency
- Traditional approach

## Next Steps

### To Set Up Samba Share

```bash
# On your server
cd ~/the-proxy-printer/proxy-machine
./setup-samba-share.sh

# Get your Tailscale IP
tailscale ip -4

# Share with friends:
# Mac: smb://your-ip/ProxyMachine
# Windows: \\your-ip\ProxyMachine
```

### To Set Up Remote API

```bash
# On your server
uv pip install flask
uv run python remote_db_server.py

# Friends set:
export PM_REMOTE_DB_URL=http://your-ip:8080
```

### To Set Up HTTP Server

```bash
# On your server
uv run python serve_data.py

# Friends download:
curl http://your-ip:8080/bulk-data/bulk.db -o bulk.db
```

Choose the option that best fits your friends' needs!
