# Sharing Proxy Machine with Friends

Quick start guide for sharing your Proxy Machine data with friends over Tailscale.

## TL;DR - Recommended Setup

**Best option: Samba network share** - Friends browse your files in Finder/Explorer

```bash
# On your server (5 minutes)
./setup-samba-share.sh

# Friends connect (2 minutes)
# Mac: Cmd+K → smb://your-tailscale-ip/ProxyMachine
# Windows: Map drive → \\your-tailscale-ip\ProxyMachine
```

**Storage on friend's machine: 0 bytes** (unless they copy files)

## Why This is Better

### Traditional Approach
- Each friend downloads 3.5GB from Scryfall
- 15-30 minutes setup time
- 3.5GB storage per friend
- Manual updates

### Network Share Approach
- Friends browse YOUR files in Finder/Explorer
- 2 minutes setup time
- 0 bytes storage (browse only)
- Automatic updates (you update once, everyone sees it)

**10 friends = 35GB bandwidth saved from Scryfall!**

## What You've Created

I've set up three sharing methods for you:

### 1. Samba Network Share (RECOMMENDED)
**Files:** `setup-samba-share.sh`, `NETWORK_SHARE_GUIDE.md`, `FRIEND_MOUNT_GUIDE.md`

Friends mount your files as a network drive and browse in Finder/Explorer.

**Pros:**
- Most user-friendly (native file browser)
- Zero storage (unless they copy)
- Works on Mac, Windows, Linux
- Read-only (safe)

**Setup:**
```bash
./scripts/setup-samba-share.sh
# Share your Tailscale IP with friends
```

### 2. Remote Database API
**Files:** `remote_db_server.py`, `remote_db_client.py`, `REMOTE_DATABASE_GUIDE.md`

Friends query your database via REST API without downloading it.

**Pros:**
- Minimal storage (~10MB)
- Programmatic access
- Always up-to-date

**Setup:**
```bash
uv pip install flask
uv run python scripts/remote_db_server.py
```

### 3. Simple HTTP File Server
**Files:** `serve_data.py`, `fetch_bulk_with_server.py`

Friends download files via HTTP (faster than Scryfall).

**Pros:**
- Simple setup
- Friends get local copies
- Works offline after download

**Setup:**
```bash
uv run python serve_data.py
```

## Quick Start

### For You (Server Setup)

1. **Install Tailscale:**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

2. **Set up Samba share:**
   ```bash
   cd the-proxy-printer/proxy-machine
   ./scripts/setup-samba-share.sh
   ```

3. **Get your Tailscale IP:**
   ```bash
   tailscale ip -4
   # Example: 100.64.x.y
   ```

4. **Share with friends:**
   - Mac: `smb://YOUR_TAILSCALE_IP/ProxyMachine`
   - Windows: `\\YOUR_TAILSCALE_IP\ProxyMachine`

### For Friends

1. **Join Tailscale:**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
   (You approve them in Tailscale admin)

2. **Mount the share:**
   - **Mac:** Finder → Cmd+K → `smb://100.64.1.5/ProxyMachine`
   - **Windows:** Map drive → `\\100.64.1.5\ProxyMachine`
   - **Linux:** `sudo mount -t cifs //100.64.1.5/ProxyMachine ~/ProxyMachine -o guest`

3. **Browse files:**
   - Navigate to `bulk-data/`
   - Copy files as needed
   - Or use directly over network

## What Friends Can Do

### Browse Only (0 bytes storage)
- Mount the share
- Browse files in Finder/Explorer
- View what's available
- No copying

### Copy Database Only (~1GB storage)
- Mount the share
- Copy `bulk-data/bulk.db` to local disk
- Fast local queries
- Still much smaller than 3.5GB

### Copy Everything (~3.5GB storage)
- Mount the share
- Copy entire `bulk-data/` folder
- Fully offline capable
- Same as traditional approach

### Hybrid (~100MB storage)
- Mount the share
- Copy only images for specific decks
- Query database over network
- Best of both worlds

## Documentation

All guides are in the `proxy-machine/` directory:

- **`SHARING_OPTIONS_COMPARISON.md`** - Compare all methods
- **`NETWORK_SHARE_GUIDE.md`** - Complete Samba setup guide
- **`FRIEND_MOUNT_GUIDE.md`** - Simple guide for friends
- **`REMOTE_DATABASE_GUIDE.md`** - Remote API documentation
- **`TAILSCALE_DEPLOYMENT.md`** - Tailscale setup details

## Storage Comparison

| Method | Friend Storage | Your Storage |
|--------|----------------|--------------|
| **Samba (browse only)** | 0 bytes | 3.5GB |
| **Samba (copy DB)** | 1GB | 3.5GB |
| **Remote API** | ~10MB | 3.5GB |
| **HTTP download** | 3.5GB | 3.5GB |
| **Scryfall direct** | 3.5GB | 0GB |

## Bandwidth Savings (10 Friends)

| Method | Scryfall Load | Your Upload |
|--------|---------------|-------------|
| **Samba** | 0GB | 0-10GB |
| **Remote API** | 0GB | ~100MB |
| **HTTP** | 0GB | ~35GB |
| **Scryfall** | 35GB | 0GB |

**Samba saves Scryfall 35GB of bandwidth!**

## Security

All methods use Tailscale:
- Private network (not public internet)
- End-to-end encrypted
- Device approval required
- No passwords needed (network-level auth)

Samba shares are read-only - friends can view and copy, but not modify your files.

## Monitoring

### Check Samba connections
```bash
sudo smbstatus
```

### Check Tailscale network
```bash
tailscale status
```

### View logs
```bash
sudo journalctl -u smbd -f
```

## Troubleshooting

### Friend can't connect

```bash
# Check Tailscale
tailscale status

# Ping your server
ping 100.64.1.5

# Test SMB port
nc -zv 100.64.1.5 445
```

### Samba not running

```bash
# Check status
sudo systemctl status smbd

# Restart
sudo systemctl restart smbd

# View logs
sudo journalctl -u smbd -n 50
```

### Slow performance

```bash
# Check if using relay (slower)
tailscale status

# Establish direct connection
tailscale ping friend-hostname
```

## Cost

### Your Costs
- Tailscale: FREE (up to 100 devices)
- Server: $5-10/month (same as before)
- Bandwidth: Minimal (Tailscale handles it)
- **Total: $5-10/month**

### Friend Costs
- Tailscale: FREE
- Storage: 0 bytes to 3.5GB (their choice)
- **Total: $0/month**

## Next Steps

1. Run `./scripts/setup-samba-share.sh` on your server
2. Get your Tailscale IP
3. Invite friends to Tailscale network
4. Share connection instructions from `FRIEND_MOUNT_GUIDE.md`
5. Friends mount and browse your files

That's it! Friends can now browse your Proxy Machine files in Finder/Explorer with zero storage on their machines.

## Questions?

See the detailed guides:
- `SHARING_OPTIONS_COMPARISON.md` - Which method to choose
- `NETWORK_SHARE_GUIDE.md` - Complete Samba documentation
- `FRIEND_MOUNT_GUIDE.md` - Simple friend instructions
