# ---- Build frontend ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Python runtime ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Sync exact dependencies (no dev deps)
RUN uv sync --no-dev --no-install-project

# Copy source code
COPY config/ config/
COPY src/ src/
COPY models/ models/

# Install the project itself
RUN uv sync --no-dev

# Copy frontend build
COPY --from=frontend-builder /app/dist/ frontend/dist/

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/health'); assert r.status==200"

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
