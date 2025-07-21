# Gateway Service Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy gateway service code (simplified version)
COPY gateway/gateway_service_simple.py gateway_service_simple.py
COPY gateway/simple_hash_ring.py simple_hash_ring.py

# Expose ports
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ring/status || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV GATEWAY_ID=""
ENV LISTEN_PORT=8000
ENV PEER_GATEWAYS=""

# Run the gateway service (simplified version)
CMD python gateway_service_simple.py 