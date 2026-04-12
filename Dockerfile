# Dockerfile Multi-Stage Build
# Optimized for production deployment

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install dependencies system-wide
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    mv /usr/local/bin/gunicorn /usr/local/bin/gunicorn-real && \
    echo '#!/bin/sh' > /usr/local/bin/gunicorn && \
    echo 'eval exec gunicorn-real $*' >> /usr/local/bin/gunicorn && \
    chmod +x /usr/local/bin/gunicorn

# Copy application code — all directories required at runtime
COPY app ./app
COPY bot_sales ./bot_sales
COPY dashboard ./dashboard
COPY maintenance ./maintenance
COPY website ./website
COPY data ./data
COPY config ./config
COPY migrations ./migrations
COPY static ./static
COPY tenants ./tenants
COPY tenants.yaml ./tenants.yaml
COPY faqs.json ./faqs.json
COPY *.py ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')"

# Expose port
EXPOSE 5000

# Run application with Gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} wsgi:app"]
