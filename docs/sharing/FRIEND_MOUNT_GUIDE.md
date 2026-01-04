# Friend's Guide: Mount Patrick's Files

Super simple guide for connecting to Patrick's Proxy Machine files.

## What You Get

Browse Patrick's files in Finder/Explorer like they're on your computer:
- `bulk-data/` - All card data (3.5GB)
- `tokens/` - Token images
- Other card resources

**Storage on your machine: 0 bytes** (unless you copy files)

## Setup (2 minutes)

### Step 1: Join Tailscale

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start it
sudo tailscale up
```

Wait for Patrick to approve your device.

### Step 2: Connect to Share

#### On Mac

1. Open **Finder**
2. Press **Cmd+K** (or Go → Connect to Server)
3. Enter: `smb://100.x.y.z/ProxyMachine`
   (Patrick will give you the IP)
4. Click **Connect**
5. Choose **Guest** (no password)

**Done!** The share appears in Finder sidebar.

#### On Windows

1. Open **File Explorer**
2. Right-click **This PC** → **Map network drive**
3. Choose drive letter (e.g., **P:**)
4. Enter: `\\100.x.y.z\ProxyMachine`
5. Check **"Connect using different credentials"**
6. Click **Finish**
7. Username: `guest`, Password: (blank)

**Done!** Drive P: appears in File Explorer.

#### On Linux

```bash
# Install CIFS utils
sudo apt install -y cifs-utils

# Create mount point
mkdir -p ~/ProxyMachine

# Mount the share
sudo mount -t cifs //100.x.y.z/ProxyMachine ~/ProxyMachine -o guest,uid=$(id -u),gid=$(id -g)
```

**Done!** Browse `~/ProxyMachine`

## What You Can Do

### Browse Files
- Navigate folders in Finder/Explorer
- See all available files
- Check file sizes, dates, etc.

### Copy Files You Need
- Drag files to your computer
- Right-click → Copy
- Only copies what you select

### Use Files Directly
- Open images from network
- Query database over network
- Read JSON files

### Example: Copy Just the Database

```bash
# Mac/Linux
cp ~/ProxyMachine/bulk-data/bulk.db ~/my-local-copy.db

# Windows (in File Explorer)
# Drag P:\bulk-data\bulk.db to your Desktop
```

Now you have a local copy (1GB) instead of downloading 3.5GB!

## Storage Options

### Option 1: Browse Only (0 bytes)
- Mount the share
- Browse files as needed
- Don't copy anything
- **Storage: 0 bytes**

### Option 2: Copy Database Only (~1GB)
- Mount the share
- Copy `bulk-data/bulk.db` to local disk
- Use local database for speed
- **Storage: ~1GB**

### Option 3: Copy Everything (~3.5GB)
- Mount the share
- Copy entire `bulk-data/` folder
- Fully offline capable
- **Storage: ~3.5GB**

### Option 4: Copy Per-Deck (~10MB per deck)
- Mount the share
- Copy only images for your deck
- Query database over network
- **Storage: ~10MB per deck**

## Speed

### Browsing Directories
- Instant (like local files)

### Opening Small Files (<10MB)
- Fast (1-2 seconds)

### Copying Large Files (>100MB)
- 50-100 MB/s over Tailscale
- 1GB database = ~10-20 seconds

### Querying Database Over Network
- Works, but slower than local
- Recommend copying database for best performance

## Auto-Mount (Optional)

### Mac

After connecting once:
1. **System Preferences → Users & Groups**
2. **Login Items** tab
3. Click **"+"**
4. Add the mounted **ProxyMachine** share

Now it auto-mounts on login!

### Windows

When mapping drive, check:
- **"Reconnect at sign-in"**

Now it auto-mounts on login!

### Linux

Add to `/etc/fstab`:
```bash
sudo nano /etc/fstab
```

Add:
```
//100.x.y.z/ProxyMachine /home/yourname/ProxyMachine cifs guest,uid=1000,gid=1000,nofail,x-systemd.automount 0 0
```

Now it auto-mounts on boot!

## Troubleshooting

### Can't connect

```bash
# Check Tailscale
tailscale status

# Ping Patrick's server
ping 100.x.y.z

# Test SMB port
nc -zv 100.x.y.z 445
```

### Share not showing up

- Make sure you're connected to Tailscale
- Ask Patrick to check if Samba is running
- Try the IP address directly (not hostname)

### Slow performance

```bash
# Check if you're using relay (slower)
tailscale status

# Try to establish direct connection
tailscale ping patrick-server
```

Use Tailscale IP instead of Pagolin for faster speeds.

### "Access Denied"

- Make sure you selected **Guest** (not your username)
- Leave password **blank**
- Ask Patrick to check share permissions

## Comparison

| Method | Storage | Speed | Setup |
|--------|---------|-------|-------|
| **Network share** | 0 bytes | Good | 2 min |
| Download database | 1GB | Excellent | 5 min |
| Download everything | 3.5GB | Excellent | 30 min |

## Questions?

Ask Patrick or check:
- `NETWORK_SHARE_GUIDE.md` - Full documentation
- `TAILSCALE_DEPLOYMENT.md` - Tailscale setup details

Enjoy browsing Patrick's files!
