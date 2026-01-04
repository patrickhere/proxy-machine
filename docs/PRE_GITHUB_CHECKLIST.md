# Pre-GitHub Upload Checklist

Complete this checklist before pushing to GitHub.

## Files and Structure

- [x] README.md created with professional content
- [x] CONTRIBUTING.md added with contribution guidelines
- [x] Documentation organized into docs/ directory
- [x] Scripts organized into scripts/ directory
- [x] .gitignore comprehensive and up-to-date

## Personal Information Removed

- [x] Hardcoded paths replaced with relative paths
- [x] Specific IP addresses replaced with placeholders (YOUR_TAILSCALE_IP, 100.64.x.y)
- [x] Personal names genericized in examples ("patrick" → "username")
- [x] Webhook URLs and secrets gitignored

## Sensitive Files Excluded

- [x] .env files gitignored
- [x] *.db files gitignored
- [x] bulk-data/ directory gitignored
- [x] config/notifications.json gitignored
- [x] Logs gitignored

## Documentation Quality

- [x] All guides use generic examples
- [x] No broken internal links
- [x] Code examples are complete and runnable
- [x] Setup instructions are clear
- [x] Deployment guides are comprehensive

## Code Quality

- [x] No hardcoded personal paths in Python files
- [x] All scripts use relative paths
- [x] Type hints present where appropriate
- [x] Docstrings added to public functions

## Repository Cleanliness

- [x] No .DS_Store files
- [x] No __pycache__ directories
- [x] No empty database files
- [x] No test output files

## Final Steps

### 1. Run Sanitization Script

```bash
./scripts/sanitize-for-github.sh
```

Review any warnings or issues flagged.

### 2. Test Clean Clone

```bash
# In a different directory
git clone /path/to/repo test-clone
cd test-clone
./scripts/setup-tailscale-server.sh --help  # Should work
```

### 3. Verify .gitignore

```bash
git status
# Should not show:
# - .env files
# - *.db files
# - bulk-data/
# - __pycache__/
```

### 4. Check for Secrets

```bash
# Search for potential secrets
git grep -i "api.key\|secret\|password\|webhook" -- '*.py' '*.sh' '*.json'
# Review results - should only be variable names, not actual secrets
```

### 5. Review Documentation

- [ ] README.md is clear and professional
- [ ] CONTRIBUTING.md has all necessary info
- [ ] All docs/ guides are complete
- [ ] No personal information in examples

### 6. Test Setup Process

```bash
# Follow README.md setup instructions exactly
# Verify they work on a clean system
```

## GitHub Repository Settings

### Repository Name
Suggested: `mtg-proxy-machine` or `proxy-machine`

### Description
"Create high-quality Magic: The Gathering proxy cards for playtesting. Features automated bulk data management, network sharing, and customizable layouts."

### Topics/Tags
- magic-the-gathering
- mtg
- proxy
- playtesting
- python
- scryfall
- pdf-generation

### README Sections
- [x] Clear project description
- [x] Features list
- [x] Quick start guide
- [x] Installation instructions
- [x] Documentation links
- [x] Contributing guidelines
- [x] License information
- [x] Disclaimer about educational use

### Branch Protection (Optional)
- Require PR reviews
- Require status checks
- Require branches to be up to date

## License

Add a LICENSE file if not present. Suggested: MIT License

```bash
# Create LICENSE file
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2024 [Your Name]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
```

## First Commit Message

Suggested commit message:

```
Initial commit: Proxy Machine

- High-quality MTG proxy card generator
- Support for all card types and layouts
- Plugin system for custom layouts
- Bulk data management from Scryfall
- Network sharing capabilities via Tailscale
- Comprehensive documentation and setup scripts

For educational and playtesting purposes only.
```

## Post-Upload Tasks

After pushing to GitHub:

1. **Add repository description and topics**
2. **Enable Issues** for bug reports and feature requests
3. **Create initial release** (v1.0.0)
4. **Add GitHub Actions** (optional) for CI/CD
5. **Create project board** (optional) for task tracking
6. **Add wiki pages** (optional) for extended documentation

## Common Issues to Avoid

### Don't Commit
- API keys or secrets
- Personal configuration files
- Large binary files (>100MB)
- Generated PDFs or images
- Database files
- Bulk data files

### Do Commit
- Source code
- Documentation
- Configuration templates
- Example files
- Setup scripts
- Tests

## Final Verification

Before pushing:

```bash
# Check what will be committed
git status
git diff --cached

# Verify no secrets
git diff --cached | grep -i "api.key\|secret\|password"

# Check file sizes
git ls-files | xargs du -h | sort -h | tail -20

# Verify .gitignore works
git check-ignore -v bulk-data/
git check-ignore -v .env
```

## Ready to Push!

Once all items are checked:

```bash
# Add all files
git add -A

# Commit
git commit -m "Initial commit: Proxy Machine"

# Create GitHub repo, then:
git remote add origin git@github.com:yourusername/mtg-proxy-machine.git
git branch -M main
git push -u origin main
```

## Post-Push Checklist

- [ ] Repository is accessible
- [ ] README displays correctly
- [ ] All documentation links work
- [ ] No sensitive information visible
- [ ] Issues and Discussions enabled
- [ ] Repository description and topics added
- [ ] License file present

Congratulations! Your repository is now public and professional!




#!/bin/bash
# Determine protonvpn port via gluetun and update qbittorrent
#
# Add the following to sudo crontab -e to run every 5 minutes
# */5 * * * * /bin/sh /path/to/update_qbit_port.sh
# For synology users, run the script as root via the task scheduler every 5 minutes.

QBITTORRENT_USER=admin            # qbittorrent username
QBITTORRENT_PASS=4b0*ZKVZ47bYstf3FX5U            # qbittorrent password
QBITTORRENT_PORT=8081
QBITTORRENT_SERVER=localhost # usually localhost if running all containers on the same machine

GLUETUN_SERVER=localhost     # usually localhost if running all containers on the same machine
GLUETUN_PORT=8003

VPN_CT_NAME=gluetun

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

findconfiguredport() {
    curl -s -i --header "Referer: http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}" --cookie "$1" "http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}/api/v2/app/preferences" | grep -oP '(?<=\"listen_port\"\:)(\d{1,5})'
}

findactiveport() {
    curl -s -i "http://${GLUETUN_SERVER}:${GLUETUN_PORT}/v1/openvpn/portforwarded" | grep -oP '(?<=\"port\"\:)(\d{1,5})'
}

getpublicip() {
    curl -s -i "http://${GLUETUN_SERVER}:${GLUETUN_PORT}/v1/publicip/ip" | grep -oP '(?<="public_ip":.)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
}

qbt_login() {
    qbt_sid=$(curl -s -i --header "Referer: http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}" --data "username=${QBITTORRENT_USER}" --data-urlencode "password=${QBITTORRENT_PASS}" "http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}/api/v2/auth/login" | grep -oP '(?!set-cookie:.)SID=.*(?=\;.HttpOnly\;)')
    return $?
}

qbt_changeport() {
    curl -s -i --header "Referer: http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}" --cookie "$1" --data-urlencode "json={\"listen_port\":$2,\"random_port\":false,\"upnp\":false}" "http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}/api/v2/app/setPreferences" >/dev/null 2>&1
    return $?
}

qbt_checksid() {
    if curl -s --header "Referer: http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}" --cookie "${qbt_sid}" "http://${QBITTORRENT_SERVER}:${QBITTORRENT_PORT}/api/v2/app/version" | grep -qi forbidden; then
        return 1
    else
        return 0
    fi
}

qbt_isreachable() {
    nc -4 -vw 5 ${QBITTORRENT_SERVER} ${QBITTORRENT_PORT} &>/dev/null 2>&1
}

check_vpn_ct_health() {
    while true;
    do
        if ! docker inspect "${VPN_CT_NAME}" --format='{{json .State.Health.Status}}' | grep -q '"healthy"'; then
            echo "$(timestamp) | Waiting for ${VPN_CT_NAME} healthy state.."
            sleep 3
        else
            echo "$(timestamp) | VPN container ${VPN_CT_NAME} in healthy state!"
            break
        fi
    done
}

get_portmap() {
    res=0
    public_ip=$(getpublicip)
    if ! qbt_checksid; then
        echo "$(timestamp) | qBittorrent Cookie invalid, getting new SessionID"
        if ! qbt_login; then
            echo "$(timestamp) | Failed getting new SessionID from qBittorrent"
              return 1
        fi
    else
        echo "$(timestamp) | qBittorrent SessionID Ok!"
    fi

    configured_port=$(findconfiguredport "${qbt_sid}")
    active_port=$(findactiveport)

    echo "$(timestamp) | Public IP: ${public_ip}"
    echo "$(timestamp) | Configured Port: ${configured_port}"
    echo "$(timestamp) | Active Port: ${active_port}"

    if [ ${configured_port} != ${active_port} ]; then
        if qbt_changeport "${qbt_sid}" ${active_port}; then
            echo "$(timestamp) | Port Changed to: $(findconfiguredport ${qbt_sid})"
        else
            echo "$(timestamp) | Port Change failed."
            res=1
        fi
    else
        echo "$(timestamp) | Port OK (Act: ${active_port} Cfg: ${configured_port})"
    fi

    return $res
}

public_ip=
configured_port=
active_port=
qbt_sid=

# Wait for a healthy state on the VPN container
check_vpn_ct_health

# check and possibly update the port
get_portmap

exit $?
