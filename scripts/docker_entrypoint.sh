#!/usr/bin/env bash
set -euo pipefail

# Run database migrations
echo "Running database migrations..."
# If the DB already has tables (from create_all in older versions) but no alembic_version,
# stamp first to avoid "table already exists" errors, then apply pending migrations.
alembic upgrade head 2>&1 || {
    echo "Attempting to stamp existing database at head..."
    alembic stamp head 2>&1
    echo "Running pending migrations..."
    alembic upgrade head 2>&1
}
echo "Migrations complete."

# Start the application
exec uvicorn src.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
