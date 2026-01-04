#!/bin/bash
set -e

# Function to log messages
log() {
    echo "[ENTRYPOINT] $1"
}

log "Starting Proxy Machine container..."

# Start Tailscale if enabled
if [ "$TAILSCALE_ENABLED" = "true" ]; then
    log "Tailscale is enabled, starting daemon..."

    # Start tailscaled in the background
    tailscaled --state=/var/lib/tailscale/tailscale.state --socket=/var/run/tailscale/tailscaled.sock &

    # Wait for tailscaled to start
    sleep 2

    # Authenticate with Tailscale
    if [ -n "$TAILSCALE_AUTHKEY" ]; then
        log "Authenticating with Tailscale..."
        if [ -n "$TAILSCALE_HOSTNAME" ]; then
            tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname="$TAILSCALE_HOSTNAME" --accept-routes
        else
            tailscale up --authkey="$TAILSCALE_AUTHKEY" --accept-routes
        fi
        log "Tailscale connected successfully!"
        tailscale status
    else
        log "WARNING: TAILSCALE_ENABLED is true but TAILSCALE_AUTHKEY is not set"
        log "Skipping Tailscale authentication"
    fi
else
    log "Tailscale is disabled"
fi

# Create necessary directories if they don't exist
log "Creating data directories..."
mkdir -p "$SHARED_ROOT" "$PROFILES_ROOT" "$BULK_DATA_DIR" "$REPORTS_DIR" "$PDF_OUTPUT_DIR"

# Set permissions
chmod -R 755 /data

# Display configuration
log "Configuration:"
log "  - PROXY_MACHINE_ROOT: $PROXY_MACHINE_ROOT"
log "  - SHARED_ROOT: $SHARED_ROOT"
log "  - PROFILES_ROOT: $PROFILES_ROOT"
log "  - BULK_DATA_DIR: $BULK_DATA_DIR"
log "  - REPORTS_DIR: $REPORTS_DIR"
log "  - PDF_OUTPUT_DIR: $PDF_OUTPUT_DIR"
log "  - WEB_HOST: $WEB_HOST"
log "  - WEB_PORT: $WEB_PORT"
log "  - LOG_LEVEL: $LOG_LEVEL"
log "  - Tailscale: $TAILSCALE_ENABLED"

# Execute the main command
log "Starting application: $@"
exec "$@"
