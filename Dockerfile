FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code first (needed for requirements.txt)
COPY . /app/

# Install uv and dependencies in one layer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    export PATH="/root/.cargo/bin:$PATH" && \
    /root/.cargo/bin/uv pip install --system -r requirements.txt

# Add uv to PATH for runtime
ENV PATH="/root/.cargo/bin:$PATH"

# Create data directories
RUN mkdir -p /data/shared /data/profiles /data/bulk-data

# Expose web port
EXPOSE 5001

# Set default environment variables
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=5001
ENV PROXY_MACHINE_ROOT=/app
ENV SHARED_ROOT=/data/shared
ENV PROFILES_ROOT=/data/profiles
ENV BULK_DATA_DIR=/data/bulk-data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/ || exit 1

# Run dashboard
CMD ["python3", "src/dashboard.py", "--host", "0.0.0.0", "--port", "5001"]
