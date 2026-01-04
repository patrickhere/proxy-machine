FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Tailscale
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    gnupg \
    iptables \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y tailscale \
    && rm -rf /var/lib/apt/lists/*

# Copy application code first (needed for requirements.txt)
COPY . /app/

# Install uv and dependencies in one layer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /root/.local/bin/uv pip install --system -r requirements.txt

# Add uv to PATH for runtime
ENV PATH="/root/.local/bin:$PATH"

# Create data directories
RUN mkdir -p /data/shared /data/profiles /data/bulk-data /data/logs

# Expose web port
EXPOSE 5001

# Default environment variables (override these in docker-compose or Unraid)
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=5001
ENV PROXY_MACHINE_ROOT=/app
ENV SHARED_ROOT=/data/shared
ENV PROFILES_ROOT=/data/profiles
ENV BULK_DATA_DIR=/data/bulk-data
ENV REPORTS_DIR=/data/shared/reports
ENV PDF_OUTPUT_DIR=/data/pdfs
ENV LOG_LEVEL=INFO
ENV MAX_DOWNLOAD_WORKERS=8
ENV DEFAULT_PPI=600

# Tailscale environment variables (optional)
ENV TAILSCALE_ENABLED=false
ENV TAILSCALE_AUTHKEY=""
ENV TAILSCALE_HOSTNAME=""

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/ || exit 1

# Copy entrypoint script
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "src/dashboard.py", "--host", "0.0.0.0", "--port", "5001"]
