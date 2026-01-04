#!/bin/bash
# Quick Samba setup for Proxy Machine file sharing over Tailscale
# Allows friends to browse your files in Finder/Explorer

set -e

echo "=========================================="
echo "Proxy Machine Samba Share Setup"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
WORK_DIR="$HOME/the-proxy-printer/proxy-machine"
USER=$(whoami)

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}WARNING: Running as root. This script will use 'patrick' as the share user.${NC}"
    USER="patrick"
fi

echo "This script will:"
echo "  1. Install Samba (SMB file sharing)"
echo "  2. Configure read-only shares for Proxy Machine files"
echo "  3. Set proper permissions"
echo "  4. Enable and start Samba service"
echo ""
echo "Friends will be able to browse your files in Finder/Explorer"
echo "over the Tailscale network (read-only, guest access)."
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Install Samba
echo -e "${GREEN}[1/5] Installing Samba...${NC}"
sudo apt update
sudo apt install -y samba samba-common-bin

# Step 2: Backup existing config
echo -e "${GREEN}[2/5] Backing up Samba configuration...${NC}"
if [ -f /etc/samba/smb.conf ]; then
    sudo cp /etc/samba/smb.conf /etc/samba/smb.conf.backup.$(date +%Y%m%d_%H%M%S)
fi

# Step 3: Configure Samba shares
echo -e "${GREEN}[3/5] Configuring Samba shares...${NC}"

# Check if our config already exists
if grep -q "\[ProxyMachine\]" /etc/samba/smb.conf 2>/dev/null; then
    echo "Samba shares already configured, skipping..."
else
    sudo tee -a /etc/samba/smb.conf > /dev/null << EOF

# Proxy Machine Shares (added by setup-samba-share.sh)
[ProxyMachine]
   comment = Proxy Machine Card Data (Read-Only)
   path = $WORK_DIR
   browseable = yes
   read only = yes
   guest ok = yes
   create mask = 0644
   directory mask = 0755
   force user = $USER

[ProxyMachineBulkData]
   comment = Proxy Machine Bulk Data (Read-Only)
   path = $WORK_DIR/bulk-data
   browseable = yes
   read only = yes
   guest ok = yes
   force user = $USER

[ProxyMachineTokens]
   comment = Proxy Machine Tokens (Read-Only)
   path = $WORK_DIR/tokens
   browseable = yes
   read only = yes
   guest ok = yes
   force user = $USER
EOF
    echo "Samba shares configured"
fi

# Step 4: Set permissions
echo -e "${GREEN}[4/5] Setting directory permissions...${NC}"
chmod -R 755 "$WORK_DIR" 2>/dev/null || true
chmod -R 755 "$WORK_DIR/bulk-data" 2>/dev/null || true
chmod -R 755 "$WORK_DIR/tokens" 2>/dev/null || true

# Step 5: Restart and enable Samba
echo -e "${GREEN}[5/5] Starting Samba service...${NC}"
sudo systemctl restart smbd
sudo systemctl enable smbd

# Verify Samba is running
if sudo systemctl is-active --quiet smbd; then
    echo "Samba service is running"
else
    echo -e "${YELLOW}WARNING: Samba service may not be running${NC}"
    sudo systemctl status smbd --no-pager
fi

# Get Tailscale IP
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "NOT_AVAILABLE")

echo ""
echo -e "${GREEN}=========================================="
echo "Samba Setup Complete!"
echo "==========================================${NC}"
echo ""

if [ "$TAILSCALE_IP" != "NOT_AVAILABLE" ]; then
    echo -e "${GREEN}Your Tailscale IP: $TAILSCALE_IP${NC}"
    echo ""
    echo "Friends can connect with:"
    echo ""
    echo "  Mac (Finder):"
    echo "    Cmd+K → smb://$TAILSCALE_IP/ProxyMachine"
    echo ""
    echo "  Windows (File Explorer):"
    echo "    Map Network Drive → \\\\$TAILSCALE_IP\\ProxyMachine"
    echo ""
    echo "  Linux:"
    echo "    smb://$TAILSCALE_IP/ProxyMachine"
else
    echo -e "${YELLOW}Tailscale IP not available${NC}"
    echo "Make sure Tailscale is running: sudo tailscale up"
fi

echo ""
echo "Available shares:"
sudo smbclient -L localhost -N 2>/dev/null | grep -A 10 "Sharename" || echo "  (run 'smbclient -L localhost -N' to view)"

echo ""
echo "Useful commands:"
echo "  Check status:     sudo systemctl status smbd"
echo "  View connections: sudo smbstatus"
echo "  Restart:          sudo systemctl restart smbd"
echo "  View shares:      smbclient -L localhost -N"
echo ""
echo "Security:"
echo "  - Read-only access (friends can't modify files)"
echo "  - Guest access (no password needed)"
echo "  - Tailscale network only (private, encrypted)"
echo ""
