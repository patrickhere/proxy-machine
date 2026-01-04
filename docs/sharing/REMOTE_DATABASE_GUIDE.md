# Remote Database Guide: Zero-Storage Client Model

This guide explains how friends can use your Proxy Machine database **without downloading it**.

## Concept

**Traditional approach:** Each friend downloads 3.5GB of data
**Remote approach:** Friends query YOUR database, only download images they need

### Storage Comparison

| Approach | Friend's Storage | Your Storage |
|----------|------------------|--------------|
| Traditional | 3.5GB database + images | 3.5GB |
| Remote | ~10MB (just images) | 3.5GB |

**Result:** Friends save 3.5GB each!

## Architecture

```
Your Server (Tailscale)
├── remote_db_server.py (Flask API)
├── bulk.db (1GB - SQLite database)
└── Card images

Friend's Machine
├── remote_db_client.py (queries your API)
├── Downloaded images only (~10MB for a deck)
└── No database needed!
```

## Setup

### On Your Server

1. **Install Flask:**
   ```bash
   uv pip install flask
   ```

2. **Start the remote database server:**
   ```bash
   cd ~/the-proxy-printer/proxy-machine
   uv run python remote_db_server.py
   ```

3. **Get your Tailscale IP:**
   ```bash
   tailscale ip -4
   # Example: 100.64.1.5
   ```

4. **Create systemd service (optional):**
   ```bash
   sudo nano /etc/systemd/system/proxy-remote-db.service
   ```

   ```ini
   [Unit]
   Description=Proxy Machine Remote Database API
   After=network.target tailscaled.service

   [Service]
   Type=simple
   User=patrick
   WorkingDirectory=/home/patrick/the-proxy-printer/proxy-machine
   Environment="PATH=/home/patrick/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
   ExecStart=/home/patrick/.cargo/bin/uv run python remote_db_server.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable proxy-remote-db
   sudo systemctl start proxy-remote-db
   ```

### For Friends

1. **Set environment variable:**
   ```bash
   export PM_REMOTE_DB_URL=http://100.64.1.5:8080
   ```

2. **Test connection:**
   ```bash
   uv run python remote_db_client.py health
   ```

3. **Search for cards:**
   ```bash
   uv run python remote_db_client.py search "Lightning Bolt"
   ```

## API Endpoints

Your server exposes these endpoints:

### GET /health
Health check
```bash
curl http://100.64.1.5:8080/health
```

### GET /api/search
Search for cards
```bash
curl "http://100.64.1.5:8080/api/search?name=Lightning%20Bolt&lang=en&limit=10"
```

Parameters:
- `name` - Card name (partial match)
- `set_code` - Set code (exact)
- `type_line` - Type line (partial)
- `rarity` - Rarity (exact)
- `lang` - Language (default: en)
- `limit` - Max results (default: 100)

### GET /api/card/<id>
Get specific card by ID
```bash
curl http://100.64.1.5:8080/api/card/abc123
```

### GET /api/sets
List all sets
```bash
curl http://100.64.1.5:8080/api/sets
```

### POST /api/deck/parse
Parse a deck list
```bash
curl -X POST http://100.64.1.5:8080/api/deck/parse \
  -H "Content-Type: application/json" \
  -d '{"decklist": "4 Lightning Bolt\n4 Counterspell", "lang": "en"}'
```

### GET /api/stats
Database statistics
```bash
curl http://100.64.1.5:8080/api/stats
```

## Client Usage

### Search for Cards

```bash
# Basic search
uv run python remote_db_client.py search "Lightning Bolt"

# Search in specific set
uv run python remote_db_client.py search "Lightning Bolt" --set lea

# Search by type
uv run python remote_db_client.py search "Dragon" --type creature --limit 50
```

### Parse Deck List

```bash
# Create deck file
cat > my-deck.txt << EOF
4 Lightning Bolt
4 Counterspell
20 Island
EOF

# Parse it
uv run python remote_db_client.py deck my-deck.txt

# Prefer specific set
uv run python remote_db_client.py deck my-deck.txt --set lea
```

### View Statistics

```bash
# Database stats
uv run python remote_db_client.py stats

# List all sets
uv run python remote_db_client.py sets
```

## Integration with create_pdf.py

To make `create_pdf.py` use the remote database, you need to modify it to query the API instead of the local database.

### Option 1: Hybrid Approach (Recommended)

Friends download ONLY the cards they need:

```python
# In create_pdf.py, add remote query function
def query_remote_db(card_name, server_url):
    """Query remote database for card."""
    import requests
    response = requests.get(
        f"{server_url}/api/search",
        params={"name": card_name, "limit": 1}
    )
    return response.json()['results'][0] if response.ok else None

# Use it when PM_REMOTE_DB_URL is set
if os.environ.get('PM_REMOTE_DB_URL'):
    card_data = query_remote_db(card_name, os.environ['PM_REMOTE_DB_URL'])
else:
    # Fall back to local database
    card_data = query_local_db(card_name)
```

### Option 2: Cache-on-Demand

Download and cache cards as needed:

```python
# Download card data on first use, cache locally
local_cache = Path("~/.proxy-machine-cache")
if not (local_cache / f"{card_id}.json").exists():
    # Download from remote
    card_data = query_remote_db(card_name, server_url)
    # Cache it
    (local_cache / f"{card_id}.json").write_text(json.dumps(card_data))
```

## Performance

### Query Speed

- Local database: <1ms per query
- Remote database (Tailscale): 5-20ms per query
- Remote database (Pagolin): 50-100ms per query

### Bandwidth Usage

| Operation | Data Transfer |
|-----------|---------------|
| Search query | ~1-10 KB |
| Deck parse (60 cards) | ~100 KB |
| Download card image | ~200 KB |
| Full deck images | ~10-20 MB |

### Comparison

**Traditional (download everything):**
- Initial: 3.5GB download
- Time: 15-30 minutes
- Storage: 3.5GB

**Remote (query as needed):**
- Initial: 0 bytes
- Time: Instant
- Storage: ~10MB per deck

## Advantages

### For Friends
- **Zero initial download** - Start using immediately
- **Minimal storage** - Only ~10MB per deck
- **Always up-to-date** - You maintain the database
- **Fast queries** - 5-20ms over Tailscale
- **No maintenance** - No database to rebuild

### For You
- **Centralized updates** - Update once, everyone benefits
- **Bandwidth savings** - Friends don't hit Scryfall
- **Control** - You manage the data source
- **Monitoring** - See what friends are searching for

## Limitations

### Network Required
Friends need network access to your server. Offline mode requires local database.

**Solution:** Hybrid mode - cache frequently used cards locally

### Query Latency
Slightly slower than local database (5-20ms vs <1ms)

**Impact:** Negligible for typical use (parsing a 60-card deck = ~1 second)

### Server Load
All friends query your server

**Capacity:** Flask can handle 100+ requests/second easily
**10 friends:** ~10 requests/second peak = no problem

## Monitoring

### Server-Side

```bash
# View logs
sudo journalctl -u proxy-remote-db -f

# Check connections
netstat -an | grep :8080

# Monitor Tailscale traffic
tailscale status
```

### Client-Side

```bash
# Test connection
uv run python remote_db_client.py health

# Check response time
time uv run python remote_db_client.py search "Lightning Bolt"
```

## Security

### Access Control
- **Tailscale network only** - No public internet exposure
- **Encrypted traffic** - Tailscale handles encryption
- **Device approval** - You approve each friend's device

### No Authentication Needed
Tailscale provides network-level authentication. No need for API keys or passwords.

### Data Privacy
- All data is public Scryfall data
- No user data or credentials stored
- Query logs are local to your server

## Troubleshooting

### Friend can't connect

```bash
# Check Tailscale
tailscale status

# Ping your server
ping 100.64.1.5

# Test API
curl http://100.64.1.5:8080/health
```

### Slow queries

```bash
# Check Tailscale connection type
tailscale status --json | jq '.Peer[] | {name: .HostName, relay: .Relay}'

# If using relay, establish direct connection
tailscale ping your-server-hostname
```

### Server not responding

```bash
# Check if server is running
sudo systemctl status proxy-remote-db

# Check database exists
ls -lh ~/the-proxy-printer/proxy-machine/bulk-data/bulk.db

# Restart server
sudo systemctl restart proxy-remote-db
```

## Cost Analysis

### Your Costs
- Server: $5-10/month (same as before)
- Bandwidth: Minimal (~1GB/month for 10 friends)
- Storage: 3.5GB (same as before)

### Friend Costs
- Storage: ~10MB per deck (vs 3.5GB)
- Bandwidth: ~10MB per deck (vs 3.5GB initial)
- **Savings: 3.4GB per friend!**

### Total Savings (10 friends)
- Storage saved: 34GB
- Bandwidth saved: 34GB initial + 5GB/week updates
- Time saved: 10 friends × 20 minutes = 200 minutes

## Next Steps

1. Start remote database server on your machine
2. Share Tailscale IP with friends
3. Friends set `PM_REMOTE_DB_URL` environment variable
4. Friends use `remote_db_client.py` to query your database
5. Optionally integrate with `create_pdf.py` for seamless experience

This is the **most efficient** approach for sharing with friends!
