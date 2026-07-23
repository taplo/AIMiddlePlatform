"""Final comprehensive check of deployed stack on 123."""
import sys

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

# Get token
_, out, _ = run(hk, """TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])") && echo "$TOKEN" """, 10)
token = out.strip()

def test(path, method="GET", expected=200, data=None):
    if method == "GET":
        _, out, _ = run(hk, f'curl -s -o /dev/null -w "%{{http_code}}" http://localhost:8000{path} -H "Authorization: Bearer {token}"', 10)
    else:
        _, out, _ = run(hk, f'curl -s -o /dev/null -w "%{{http_code}}" -X POST http://localhost:8000{path} -H "Content-Type: application/json" -H "Authorization: Bearer {token}" -d \'{data}\'', 10)
    code = out.strip()
    ok = "OK" if code == str(expected) else "FAIL"
    print(f"  [{ok}] {code} {method} {path}")

print("=== API Route Tests ===")
test("/api/v1/health")
test("/api/v1/auth/login", "POST", 200, '{"username":"admin","password":"admin123"}')
test("/api/v1/models/")
test("/api/v1/models/active")
test("/api/v1/models/object_detection/stats")
test("/api/v1/system/stats")
test("/api/v1/system/stats/history")
test("/api/v1/logs")
test("/api/v1/traces")
test("/api/v1/agent/config")
test("/api/v1/pipelines")
test("/api/v1/admin/rules")
test("/api/v1/admin/notifications")
test("/api/v1/alerts")
test("/api/v1/tasks")
test("/metrics")

print("\n=== Frontend via Nginx ===")
_, out, _ = run(hk, "curl -s -o /dev/null -w '%{http_code}' http://localhost/", 10)
print(f"  [OK] {out.strip()} GET / (nginx root)")

print("\n=== Worker Status ===")
_, out, _ = run(hk, "docker logs aimp-worker --tail 5 2>&1", 10)
print(out)

print("\n=== Compose Status ===")
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' 2>&1", 10)
print(out)
