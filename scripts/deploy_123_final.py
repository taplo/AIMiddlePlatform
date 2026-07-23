#!/usr/bin/env python3
"""Full redeploy on 123: git pull, rebuild, compose up, smoke test."""
import sys
import time
sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

print("=== 1. git pull ===")
ec, out, err = run(hk, "cd /home/taplo/AIMiddlePlatform && git pull origin master", 60)
print(out[:500])
print(f"exit={ec}")

print("\n=== 2. docker build ===")
ec, out, err = run(hk, "cd /home/taplo/AIMiddlePlatform && docker build -t taplo/aimiddleplatform:latest . 2>&1", 600)
lines = out.strip().split("\n")
for l in lines[-5:]:
    print(l)
print(f"exit={ec}")

print("\n=== 3. compose down ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose down --remove-orphans", 30)

print("\n=== 4. start redis ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d redis", 30)
time.sleep(5)

print("\n=== 5. start API ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-api", 30)
print("waiting 20s...")
time.sleep(20)

print("\n=== 6. health check ===")
_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/health", 10)
print(out)

print("\n=== 7. start worker + nginx ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-worker nginx", 30)
time.sleep(5)

print("\n=== 8. full smoke test ===")
_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/health", 10)
print("health:", out)

_, out, _ = run(hk, 'curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d \'{"username":"admin","password":"admin123"}\'', 10)
print("login:", out[:200])

_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/models", 10)
print("models:", out[:300])

_, out, _ = run(hk, 'curl -s -X POST http://localhost:8000/api/v1/analyze -H "Content-Type: application/json" -d \'{"camera_id":"test-cam","scene_type":"office","timestamp":"2026-07-23T12:00:00Z","frame":"/9j/4AAQSkZJRg=="}\'', 10)
print("analyze:", out[:200])

_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/system/stats", 10)
print("stats:", out[:300])

print("\n=== 9. compose ps ===")
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose ps", 10)
print(out)

print("\n=== 10. API migration logs ===")
_, out, _ = run(hk, "docker logs aimp-api 2>&1 | head -10", 10)
print(out)
