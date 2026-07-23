#!/usr/bin/env bash
# Deploy Docker Compose stack on 192.168.3.123 and smoke test
set -euo pipefail

cd /home/taplo/AIMiddlePlatform

# 1. Ensure .env exists
if [ ! -f .env ]; then
    cp .env.example .env
fi
# Ensure JWT secret is set
if grep -q "change-me" .env 2>/dev/null; then
    sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=deploy-test-key-$(date +%s)/" .env
fi
echo "=== .env ==="
grep -v '^#' .env | grep -v '^$' || echo "(empty)"

# 2. Kill any existing compose stack
docker compose down --remove-orphans 2>/dev/null || true

# 3. Start core services: Redis + API + Worker + Nginx
echo ""
echo "=== Starting core services ==="
docker compose up -d redis 2>&1
echo "Waiting for Redis health..."
for i in $(seq 1 15); do
    if docker compose exec redis redis-cli ping 2>/dev/null; then
        echo "Redis ready"
        break
    fi
    sleep 2
done

echo ""
echo "=== Starting API ==="
docker compose up -d aimp-api 2>&1
echo "Waiting for API health..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/api/v1/health 2>/dev/null | grep -q '"status"'; then
        echo "API ready"
        break
    fi
    sleep 2
done

echo ""
echo "=== Starting Worker + Nginx ==="
docker compose up -d aimp-worker nginx 2>&1

# 4. Smoke test
echo ""
echo "=== Smoke Tests ==="
echo "--- Health ---"
curl -s http://localhost:8000/api/v1/health || echo "FAILED"

echo ""
echo "--- Models ---"
curl -s http://localhost/api/v1/models | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/api/v1/models | python3 -m json.tool 2>/dev/null || echo "FAILED"

echo ""
echo "--- Submit Frame ---"
curl -s -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"camera_id":"test-cam","scene_type":"office","timestamp":"2026-07-23T12:00:00Z","frame":"/9j/4AAQSkZJRg=="}' | python3 -m json.tool 2>/dev/null || echo "(expected: needs auth or returns task_id)"

echo ""
echo "=== Compose Status ==="
docker compose ps

echo ""
echo "=== Logs (last 10 lines each) ==="
docker compose logs --tail=10 aimp-api 2>&1
echo "---"
docker compose logs --tail=10 aimp-worker 2>&1

echo ""
echo "=== Done. Run 'docker compose down' to stop ==="
