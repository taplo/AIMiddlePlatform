# ---- Build frontend ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Python runtime ----
FROM python:3.12-slim

ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY_ARG=$http_proxy
ARG HTTPS_PROXY_ARG=$https_proxy
ARG NO_PROXY

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv (use proxy if provided)
RUN HTTP_PROXY=${HTTP_PROXY_ARG} HTTPS_PROXY=${HTTPS_PROXY_ARG} NO_PROXY=${NO_PROXY} \
    pip install --no-cache-dir uv

# Copy dependency files + source code
COPY pyproject.toml uv.lock* ./
COPY config/ config/
COPY src/ src/
COPY models/ models/

# Sync all dependencies (caches wheels across builds for slow networks)
RUN --mount=type=cache,target=/root/.cache/uv \
    HTTP_PROXY=${HTTP_PROXY_ARG} HTTPS_PROXY=${HTTPS_PROXY_ARG} NO_PROXY=${NO_PROXY} \
    uv sync --no-dev

# Copy frontend build
COPY --from=frontend-builder /app/dist/ frontend/dist/

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/api/v1/health'); assert r.status==200"

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
