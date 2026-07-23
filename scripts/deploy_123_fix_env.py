"""Fix .env and restart API on 123."""
import sys
import time

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

# Update .env with known admin password
run(hk, """cd /home/taplo/AIMiddlePlatform && sed -i 's/ADMIN_PASSWORD=change-me-in-production/ADMIN_PASSWORD=admin123/' .env""", 10)

# Verify
_, out, _ = run(hk, "grep ADMIN_PASSWORD /home/taplo/AIMiddlePlatform/.env", 10)
print("ADMIN_PASSWORD:", out)

# Recreate API container to pick up new env
print("=== recreate API ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-api --force-recreate", 30)

time.sleep(15)

# Test login
print("=== test login ===")
_, out, _ = run(hk, """curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'""", 10)
print(out[:300])

# Full smoke test
print("=== models ===")
_, out, _ = run(hk, """TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])") && curl -s http://localhost:8000/api/v1/models -H "Authorization: Bearer $TOKEN" && echo""", 15)
print(out[:500])

print("=== stats ===")
_, out, _ = run(hk, """TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])") && curl -s http://localhost:8000/api/v1/system/stats -H "Authorization: Bearer $TOKEN" && echo""", 15)
print(out[:500])

print("=== health ===")
_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/health", 10)
print(out)
