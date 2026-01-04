# Network Share Guide: Browse Files in Finder/Explorer

This guide shows how to share your Proxy Machine files so friends can browse them in Finder (Mac) or File Explorer (Windows) like a network drive.

## Best Option: Samba (SMB) Share

Samba works on Mac, Windows, and Linux. Friends can mount your files as a network drive.

### Setup on Your Server

#### 1. Install Samba

```bash
sudo apt update
sudo apt install -y samba samba-common-bin
```

#### 2. Create Samba Configuration

```bash
sudo nano /etc/samba/smb.conf
```

Add this at the end:

```ini
[ProxyMachine]
   comment = Proxy Machine Card Data
   path = /home/patrick/the-proxy-printer/proxy-machine
   browseable = yes
   read only = yes
   guest ok = yes
   create mask = 0644
   directory mask = 0755
   force user = patrick

[ProxyMachineBulkData]
   comment = Proxy Machine Bulk Data (Read-Only)
   path = /home/patrick/the-proxy-printer/proxy-machine/bulk-data
   browseable = yes
   read only = yes
   guest ok = yes
   force user = patrick

[ProxyMachineTokens]
   comment = Proxy Machine Tokens (Read-Only)
   path = /home/patrick/the-proxy-printer/proxy-machine/tokens
   browseable = yes
   read only = yes
   guest ok = yes
   force user = patrick
```

**Note:** `guest ok = yes` means no password needed (safe on Tailscale private network)

#### 3. Set Permissions

```bash
# Make sure directories are readable
chmod -R 755 ~/the-proxy-printer/proxy-machine/bulk-data
chmod -R 755 ~/the-proxy-printer/proxy-machine/tokens
```

#### 4. Restart Samba

```bash
sudo systemctl restart smbd
sudo systemctl enable smbd
```

#### 5. Check Samba Status

```bash
sudo systemctl status smbd
```

#### 6. Get Your Tailscale IP

```bash
tailscale ip -4
# Example: 100.64.1.5
```

### For Friends: Mount the Share

#### On Mac (Finder)

1. **Open Finder**
2. **Press Cmd+K** (or Go → Connect to Server)
3. **Enter server address:**
   ```
   smb://100.64.1.5/ProxyMachine
   ```
4. **Click Connect**
5. **Choose "Guest"** (no password needed)

The share will appear in Finder sidebar under "Locations"

**Alternative (Terminal):**
```bash
# Create mount point
mkdir -p ~/ProxyMachine

# Mount the share
mount_smbfs //guest@100.64.1.5/ProxyMachine ~/ProxyMachine

# Browse files
open ~/ProxyMachine
```

#### On Windows (File Explorer)

1. **Open File Explorer**
2. **Click "This PC"** in sidebar
3. **Click "Map network drive"** (in toolbar)
4. **Choose a drive letter** (e.g., P:)
5. **Enter folder:**
   ```
   \\100.64.1.5\ProxyMachine
   ```
6. **Uncheck "Reconnect at sign-in"** (optional)
7. **Check "Connect using different credentials"**
8. **Click Finish**
9. **Enter credentials:**
   - Username: `guest`
   - Password: (leave blank)

**Alternative (Command Prompt):**
```cmd
net use P: \\100.64.1.5\ProxyMachine /user:guest ""
```

#### On Linux

```bash
# Install cifs-utils
sudo apt install -y cifs-utils

# Create mount point
mkdir -p ~/ProxyMachine

# Mount the share
sudo mount -t cifs //100.64.1.5/ProxyMachine ~/ProxyMachine -o guest,uid=$(id -u),gid=$(id -g)

# Or add to /etc/fstab for automatic mounting
echo "//100.64.1.5/ProxyMachine /home/$USER/ProxyMachine cifs guest,uid=$(id -u),gid=$(id -g),nofail 0 0" | sudo tee -a /etc/fstab
```

### What Friends Can Do

Once mounted, friends can:

1. **Browse files in Finder/Explorer**
   - Navigate to `bulk-data/`
   - See `all-cards.json.gz`, `bulk.db`, etc.
   - View tokens, images, etc.

2. **Copy files they need**
   - Drag and drop to local machine
   - Right-click → Copy

3. **Open files directly**
   - SQLite browser can open `bulk.db` over network
   - View images directly
   - Read JSON files

4. **Use in applications**
   - Point apps to network path
   - Example: `~/ProxyMachine/bulk-data/bulk.db`

### Read-Only vs Read-Write

**Current setup: Read-only** (recommended)
- Friends can view and copy files
- Cannot modify or delete your files
- Safe for sharing

**To enable read-write** (not recommended):
```ini
[ProxyMachineReadWrite]
   path = /home/patrick/the-proxy-printer/proxy-machine
   read only = no
   writable = yes
   guest ok = yes
```

**Warning:** Only enable read-write if you trust friends completely!

## Alternative: NFS (Linux/Mac Only)

NFS is faster but only works well on Linux/Mac.

### Setup NFS Server

```bash
# Install NFS server
sudo apt install -y nfs-kernel-server

# Configure exports
sudo nano /etc/exports
```

Add:
```
/home/patrick/the-proxy-printer/proxy-machine 100.64.0.0/10(ro,sync,no_subtree_check,all_squash,anonuid=1000,anongid=1000)
```

**Note:** `100.64.0.0/10` is the Tailscale network range

```bash
# Apply changes
sudo exportfs -ra

# Start NFS server
sudo systemctl restart nfs-kernel-server
sudo systemctl enable nfs-kernel-server
```

### Mount NFS Share (Mac)

```bash
# Create mount point
mkdir -p ~/ProxyMachine

# Mount
sudo mount -t nfs -o resvport,rw 100.64.1.5:/home/patrick/the-proxy-printer/proxy-machine ~/ProxyMachine

# Browse
open ~/ProxyMachine
```

### Mount NFS Share (Linux)

```bash
# Install NFS client
sudo apt install -y nfs-common

# Create mount point
mkdir -p ~/ProxyMachine

# Mount
sudo mount -t nfs 100.64.1.5:/home/patrick/the-proxy-printer/proxy-machine ~/ProxyMachine

# Add to /etc/fstab for auto-mount
echo "100.64.1.5:/home/patrick/the-proxy-printer/proxy-machine /home/$USER/ProxyMachine nfs defaults,nofail 0 0" | sudo tee -a /etc/fstab
```

## Comparison: SMB vs NFS

| Feature | SMB (Samba) | NFS |
|---------|-------------|-----|
| **Works on Windows** | Yes | No (requires third-party) |
| **Works on Mac** | Yes | Yes |
| **Works on Linux** | Yes | Yes |
| **Speed** | Good | Excellent |
| **Setup complexity** | Easy | Medium |
| **Recommendation** | **Use this** | Linux/Mac only |

## Performance

### File Browsing
- **Local disk:** Instant
- **SMB over Tailscale:** 10-50ms latency
- **NFS over Tailscale:** 5-20ms latency

### File Copying
- **SMB:** 50-100 MB/s over Tailscale
- **NFS:** 80-150 MB/s over Tailscale

### Opening Files Directly
- **Small files (<10MB):** Works great
- **Large files (>100MB):** Copy to local disk first
- **Databases:** Can query directly (slower than local)

## Use Cases

### Scenario 1: Browse and Copy
Friend wants to see what's available:
1. Mount SMB share
2. Browse in Finder/Explorer
3. Copy files they need to local disk
4. Use locally

**Storage:** Only what they copy

### Scenario 2: Direct Access
Friend wants to query database directly:
1. Mount SMB share
2. Point app to `~/ProxyMachine/bulk-data/bulk.db`
3. App queries over network

**Storage:** Zero (all on your server)

### Scenario 3: Hybrid
Friend uses both:
1. Mount SMB share
2. Copy frequently used files locally
3. Browse others on demand

**Storage:** ~100MB-1GB (their choice)

## Security

### Tailscale Network Only
- SMB/NFS only accessible on Tailscale network
- No public internet exposure
- Encrypted by Tailscale

### Guest Access
- No password required (safe on private network)
- Read-only access (can't modify your files)
- You control who joins Tailscale network

### Monitoring Access
```bash
# View Samba connections
sudo smbstatus

# View NFS connections
sudo showmount -a
```

## Troubleshooting

### Can't connect to share

**Mac:**
```bash
# Test if server is reachable
ping 100.64.1.5

# Test if SMB port is open
nc -zv 100.64.1.5 445

# Check Tailscale
tailscale status
```

**Windows:**
```cmd
ping 100.64.1.5
telnet 100.64.1.5 445
```

### "Access Denied" error

```bash
# On your server, check permissions
ls -la ~/the-proxy-printer/proxy-machine/bulk-data

# Fix permissions
chmod -R 755 ~/the-proxy-printer/proxy-machine/bulk-data

# Restart Samba
sudo systemctl restart smbd
```

### Slow performance

```bash
# Check Tailscale connection type
tailscale status --json | jq '.Peer[] | {name: .HostName, relay: .Relay}'

# If using relay, establish direct connection
tailscale ping friend-hostname
```

### Share not visible

```bash
# On your server, check Samba status
sudo systemctl status smbd

# Check Samba configuration
testparm -s

# View available shares
smbclient -L localhost -N
```

## Automatic Mounting

### Mac (Auto-mount on login)

1. Mount the share once manually
2. **System Preferences → Users & Groups**
3. **Login Items** tab
4. **Click "+"** and add the mounted share

Or use AppleScript:
```applescript
tell application "Finder"
    mount volume "smb://100.64.1.5/ProxyMachine"
end tell
```

Save as Application, add to Login Items.

### Windows (Auto-mount)

When mapping drive, check **"Reconnect at sign-in"**

Or use startup script:
```batch
@echo off
net use P: \\100.64.1.5\ProxyMachine /user:guest "" /persistent:yes
```

### Linux (Auto-mount via fstab)

```bash
# Add to /etc/fstab
sudo nano /etc/fstab
```

Add:
```
//100.64.1.5/ProxyMachine /home/patrick/ProxyMachine cifs guest,uid=1000,gid=1000,nofail,x-systemd.automount 0 0
```

## Storage Savings

### Traditional Approach
Each friend: 3.5GB local storage

### Network Share Approach
Each friend: 0 bytes (browse your files)

**10 friends = 35GB saved!**

### Hybrid Approach
Each friend: Copy only what they need (~100MB-1GB)

**10 friends = 25-34GB saved!**

## Bandwidth Usage

### Initial Setup
- Mount share: <1 KB
- Browse directories: ~10 KB
- View file list: ~1 KB per directory

### Copying Files
- Copy bulk.db (1GB): 1GB transfer (one-time)
- Copy specific cards: ~1-10 MB per deck

### Direct Access
- Query database over network: ~1-10 KB per query
- Open image over network: ~200 KB per image

## Next Steps

1. **Install Samba** on your server
2. **Configure shares** (read-only recommended)
3. **Share your Tailscale IP** with friends
4. **Friends mount** `smb://your-ip/ProxyMachine`
5. **Friends browse** in Finder/Explorer

This is the **most user-friendly** approach - friends can browse your files just like local folders!

## Quick Setup Script

Save this as `setup-samba-share.sh`:

```bash
#!/bin/bash
# Quick Samba setup for Proxy Machine sharing

set -e

echo "Installing Samba..."
sudo apt update
sudo apt install -y samba

echo "Configuring Samba shares..."
sudo tee -a /etc/samba/smb.conf > /dev/null << 'EOF'

[ProxyMachine]
   comment = Proxy Machine Card Data
   path = /home/patrick/the-proxy-printer/proxy-machine
   browseable = yes
   read only = yes
   guest ok = yes
   force user = patrick

[ProxyMachineBulkData]
   comment = Bulk Data (Read-Only)
   path = /home/patrick/the-proxy-printer/proxy-machine/bulk-data
   browseable = yes
   read only = yes
   guest ok = yes
   force user = patrick
EOF

echo "Setting permissions..."
chmod -R 755 ~/the-proxy-printer/proxy-machine/bulk-data

echo "Restarting Samba..."
sudo systemctl restart smbd
sudo systemctl enable smbd

echo "Getting Tailscale IP..."
TAILSCALE_IP=$(tailscale ip -4)

echo ""
echo "=========================================="
echo "Samba Setup Complete!"
echo "=========================================="
echo ""
echo "Your Tailscale IP: $TAILSCALE_IP"
echo ""
echo "Friends can connect with:"
echo "  Mac:     smb://$TAILSCALE_IP/ProxyMachine"
echo "  Windows: \\\\$TAILSCALE_IP\\ProxyMachine"
echo "  Linux:   smb://$TAILSCALE_IP/ProxyMachine"
echo ""
echo "Available shares:"
sudo smbclient -L localhost -N | grep -A 5 "Sharename"
echo ""
```

Make it executable and run:
```bash
chmod +x setup-samba-share.sh
./setup-samba-share.sh
```
