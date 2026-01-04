# Quick Setup for Friends

Hey! Patrick has set up a shared Proxy Machine server so you don't have to download 2.5GB from Scryfall.

## What You Need

- Ubuntu/Linux machine (or Mac)
- 10 minutes
- Access to Patrick's Tailscale network

## Setup Steps

### 1. Join Tailscale Network (One-time, 2 minutes)

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start Tailscale
sudo tailscale up

# Patrick will approve your device
```

Wait for Patrick to approve your device in the Tailscale admin console.

### 2. Run Setup Script (8 minutes)

```bash
# Download and run the setup script
curl -fsSL https://raw.githubusercontent.com/your-repo/main/proxy-machine/setup-friend-client.sh | bash

# Or if you already have the repo:
cd ~/the-proxy-printer/proxy-machine
./setup-friend-client.sh
```

The script will ask for Patrick's server URL. Use one of these:

- **Tailscale:** `http://100.x.y.z:8080` (Patrick will give you the IP)
- **Pagolin:** `https://proxy-machine.pagolin.com` (if Patrick set this up)

### 3. Done!

That's it! The script will:
- Install dependencies
- Download bulk data from Patrick's server (much faster!)
- Build your local database
- Configure everything

## Using the Proxy Machine

```bash
# Navigate to the project
cd ~/the-proxy-printer/proxy-machine

# Activate environment
source .venv/bin/activate
export $(cat .env | xargs)

# Create a deck file (one card per line)
cat > my-deck.txt << EOF
4 Lightning Bolt
4 Counterspell
20 Island
EOF

# Generate PDF
uv run python create_pdf.py my-deck.txt --output my-deck.pdf

# View the PDF
xdg-open my-deck.pdf
```

## Troubleshooting

### Can't connect to server

```bash
# Check Tailscale connection
tailscale status

# Ping Patrick's server
ping 100.x.y.z

# Test HTTP connection
curl http://100.x.y.z:8080/bulk-data/
```

### Downloads are slow

Use the Tailscale IP instead of Pagolin URL for faster speeds:

```bash
# Edit .env file
nano .env

# Change to:
PM_BULK_DATA_URL=http://100.x.y.z:8080
```

### Need to update data

Patrick updates the server weekly, but if you need to refresh:

```bash
cd ~/the-proxy-printer/proxy-machine
source .venv/bin/activate

# Download latest database
curl -f $PM_BULK_DATA_URL/bulk-data/bulk.db -o bulk-data/bulk.db

# Or re-download everything
uv run python tools/fetch_bulk.py --id all-cards
uv run python tools/fetch_bulk.py --id oracle-cards
```

## What Gets Shared?

Patrick's server shares:
- Bulk card data (~2.5GB) - public Scryfall data
- Card database (SQLite) - for fast searches
- Token images (optional)
- Basic land images (optional)

**Nothing private is shared** - it's all public Magic card data from Scryfall.

## Advantages

- **Faster downloads** - Local network speeds via Tailscale
- **Save bandwidth** - No need to download from Scryfall
- **Always up-to-date** - Patrick updates weekly
- **Secure** - Private Tailscale network, encrypted traffic
- **Easy** - One-time setup, then it just works

## Manual Setup (if script fails)

<details>
<summary>Click to expand manual steps</summary>

```bash
# 1. Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip curl git \
    libjpeg-dev libpng-dev libopencv-dev sqlite3

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# 3. Clone repo
git clone <repo-url> ~/the-proxy-printer
cd ~/the-proxy-printer/proxy-machine

# 4. Setup Python environment
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt

# 5. Configure
cat > .env << EOF
PM_BULK_DATA_URL=http://100.x.y.z:8080
PM_OFFLINE=0
PM_ASK_REFRESH=0
EOF

export $(cat .env | xargs)

# 6. Download data
mkdir -p bulk-data
curl $PM_BULK_DATA_URL/bulk-data/all-cards.json.gz -o bulk-data/all-cards.json.gz
curl $PM_BULK_DATA_URL/bulk-data/oracle-cards.json.gz -o bulk-data/oracle-cards.json.gz
curl $PM_BULK_DATA_URL/bulk-data/unique-artwork.json.gz -o bulk-data/unique-artwork.json.gz

# 7. Build database
uv run python -c "from db.bulk_index import build_db_from_bulk_json, DB_PATH; build_db_from_bulk_json(DB_PATH)"

# 8. Verify
uv run python tools/verify.py
```

</details>

## Questions?

Ask Patrick! Or check the full documentation:
- `WORKFLOW.md` - How to use the proxy machine
- `PROJECT_OVERVIEW.md` - Detailed project docs
- `TAILSCALE_DEPLOYMENT.md` - Server setup details

## Cost

**For you: $0/month**

Patrick is covering the server costs. All you need is:
- Tailscale (free)
- Your own computer
- Internet connection

Enjoy making proxies!
