#!/bin/bash
# Deploy Proxy Machine to Unraid
#
# Usage:
#   ./scripts/deploy-to-unraid.sh <unraid-ip> [options]
#
# Options:
#   --build-only    Just transfer files and build, don't start container
#   --update        Update existing deployment
#

set -e

UNRAID_IP="${1:-}"
BUILD_ONLY=false
UPDATE=false

# Parse arguments
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --update)
            UPDATE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$UNRAID_IP" ]; then
    echo "Usage: $0 <unraid-ip> [--build-only] [--update]"
    echo ""
    echo "Examples:"
    echo "  $0 192.168.1.100                # Full deployment"
    echo "  $0 192.168.1.100 --build-only   # Just build, don't start"
    echo "  $0 192.168.1.100 --update       # Update existing container"
    exit 1
fi

echo "=================================================="
echo "Proxy Machine - Unraid Deployment"
echo "=================================================="
echo "Target: root@$UNRAID_IP"
echo ""

# Step 1: Create base directory
echo "Step 1/6: Creating base directory on Unraid..."
ssh root@$UNRAID_IP "mkdir -p /mnt/user/appdata/proxy-machine/app"
echo "✓ Directory created"
echo ""

# Step 2: Transfer files
echo "Step 2/6: Transferring files to Unraid..."
rsync -avz --progress \
    --exclude='bulk-data/' \
    --exclude='data/' \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='.env' \
    . root@$UNRAID_IP:/mnt/user/appdata/proxy-machine/app/

echo "✓ Files transferred"
echo ""

# Step 3: Create data directories
echo "Step 3/6: Creating data directories..."
ssh root@$UNRAID_IP << 'EOF'
    mkdir -p /mnt/user/appdata/proxy-machine/shared
    mkdir -p /mnt/user/appdata/proxy-machine/profiles
    mkdir -p /mnt/user/appdata/proxy-machine/bulk-data
    echo "✓ Directories created"
EOF
echo ""

# Step 4: Build Docker image
echo "Step 4/6: Building Docker image on Unraid..."
ssh root@$UNRAID_IP << 'EOF'
    cd /mnt/user/appdata/proxy-machine/app
    docker build -t proxy-machine:latest .
    echo "✓ Docker image built"
EOF
echo ""

if [ "$BUILD_ONLY" = true ]; then
    echo "Build complete! (--build-only flag set)"
    echo ""
    echo "To start the container manually:"
    echo "  ssh root@$UNRAID_IP"
    echo "  cd /mnt/user/appdata/proxy-machine/app"
    echo "  docker-compose up -d"
    exit 0
fi

# Step 5: Stop existing container (if updating)
if [ "$UPDATE" = true ]; then
    echo "Step 5/6: Stopping existing container..."
    ssh root@$UNRAID_IP << 'EOF'
        cd /mnt/user/appdata/proxy-machine/app
        docker-compose down || docker stop proxy-machine || true
        echo "✓ Old container stopped"
EOF
    echo ""
else
    echo "Step 5/6: Skipping (new deployment)"
    echo ""
fi

# Step 6: Start container
echo "Step 6/6: Starting Proxy Machine container..."
ssh root@$UNRAID_IP << 'EOF'
    cd /mnt/user/appdata/proxy-machine/app
    docker-compose up -d
    echo "✓ Container started"
EOF
echo ""

# Get container status
echo "Checking container status..."
ssh root@$UNRAID_IP << 'EOF'
    sleep 2
    docker ps | grep proxy-machine || echo "Warning: Container not running!"
EOF
echo ""

echo "=================================================="
echo "Deployment Complete!"
echo "=================================================="
echo ""
echo "Access the dashboard at:"
echo "  http://$UNRAID_IP:5001"
echo ""
echo "Next steps:"
echo "  1. Access the web interface"
echo "  2. Run initial database sync (if first deployment):"
echo "     ssh root@$UNRAID_IP"
echo "     docker exec -it proxy-machine bash"
echo "     uv run python create_pdf.py --bulk_sync"
echo ""
echo "View logs:"
echo "  ssh root@$UNRAID_IP"
echo "  docker logs -f proxy-machine"
echo ""
