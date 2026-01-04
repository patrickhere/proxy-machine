# How Friends Access Your Shared Files

## Quick Answer

Friends access files via HTTP URLs over your Tailscale network:

```bash
# Your Tailscale IP (example): 100.64.1.5
# Friends download files with:

curl http://100.64.1.5:8080/bulk-data/all-cards.json.gz -o bulk-data/all-cards.json.gz
curl http://100.64.1.5:8080/bulk-data/oracle-cards.json.gz -o bulk-data/oracle-cards.json.gz
curl http://100.64.1.5:8080/bulk-data/bulk.db -o bulk-data/bulk.db
```

## Automatic Method (Recommended)

Friends set one environment variable and the code handles everything:

```bash
# In .env file
PM_BULK_DATA_URL=http://100.64.1.5:8080

# Load it
export $(cat .env | xargs)

# Use enhanced fetch script
uv run python tools/fetch_bulk_with_server.py --id all-cards
```

The script automatically:
- Tries your server first (fast!)
- Falls back to Scryfall if needed
- Shows download progress

## What You're Sharing

```
Your Server (100.64.1.5:8080)
├── /bulk-data/
│   ├── all-cards.json.gz       (2.5GB)
│   ├── oracle-cards.json.gz    (159MB)
│   ├── unique-artwork.json.gz  (229MB)
│   └── bulk.db                 (1GB)
└── /tokens/ (optional)
```

## Speed Comparison

- Your Tailscale server: 2-5 minutes for 3.5GB
- Scryfall: 15-30 minutes for 3.5GB

Friends save 10-25 minutes on initial setup!

## Files Created

I've created:
1. `tools/fetch_bulk_with_server.py` - Enhanced fetch script with custom server support
2. `serve_data.py` - Simple HTTP server (created by setup script)
3. Setup scripts for you and friends

## Next Steps

1. Run `./setup-tailscale-server.sh` on your server
2. Get your Tailscale IP: `tailscale ip -4`
3. Share IP with friends
4. Friends set `PM_BULK_DATA_URL=http://YOUR_IP:8080`
5. Friends run `./setup-friend-client.sh`

That's it! The HTTP server serves files, Tailscale handles networking, friends download via HTTP.
