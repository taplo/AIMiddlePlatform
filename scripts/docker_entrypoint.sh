#!/usr/bin/env bash
set -euo pipefail

# Run database migrations
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

# Start the application
exec uvicorn src.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
