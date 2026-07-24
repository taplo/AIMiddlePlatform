"""Test all key API endpoints on 123."""
import sys

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

# Get token
_, out, _ = run(hk, """TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])") && echo "$TOKEN" """, 10)
token = out.strip()
print(f"Token: {token[:50]}...")

def test(path, desc=""):
    _, out, _ = run(hk, f'curl -s -w "\\n%{{http_code}}" http://localhost:8000{path} -H "Authorization: Bearer {token}"', 10)
    lines = out.strip().split("\n")
    code = lines[-1] if lines else "?"
    body = "\n".join(lines[:-1]) if len(lines) > 1 else lines[0] if lines else ""
    print(f"  {desc or path:40s} {code}  {body[:120]}")

test("/api/v1/health", "health (no auth)")
test("/api/v1/auth/login", "login (POST test)")
test("/api/v1/models", "list models")
test("/api/v1/models/active", "active models")
test("/api/v1/models/detector/stats", "model stats")
test("/api/v1/system/stats", "dashboard stats")
test("/api/v1/system/stats/history", "stats history")
test("/api/v1/logs", "logs")
test("/api/v1/traces", "traces")
test("/api/v1/agent/config", "agent config")
test("/api/v1/pipelines", "pipelines")
test("/api/v1/admin/rules", "rules")
test("/api/v1/admin/notifications", "notifications")
test("/api/v1/alerts", "alerts")
test("/api/v1/tasks", "tasks")
test("/v1/models/", "v1 models (alt)")

# Analyze with auth
_, out, _ = run(hk, f'curl -s -X POST http://localhost:8000/api/v1/analyze -H "Content-Type: application/json" -H "Authorization: Bearer {token}" -d \'{{"camera_id":"test-cam","scene_type":"office","timestamp":"2026-07-23T12:00:00Z","frame":"/9j/4AAQSkZJRg=="}}\'', 10)
print(f"  {'analyze (POST)':40s} {out[:150]}")
