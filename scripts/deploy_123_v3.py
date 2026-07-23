#!/usr/bin/env python3
"""Redeploy on 123: fresh DB volume, rebuild, compose up, smoke test."""
import sys
import time

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

print("=== 1. git pull ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && git pull origin master", 60)

print("\n=== 2. down + delete volume ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose down --remove-orphans -v", 30)
run(hk, "docker volume rm aimp_data_volume 2>/dev/null; docker volume rm aimpplatform_data_volume 2>/dev/null; docker volume ls | grep data_volume 2>&1", 10)

print("\n=== 3. docker build ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker build -t taplo/aimiddleplatform:latest . 2>&1 | tail -3", 600)

print("\n=== 4. start redis ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d redis", 30)
time.sleep(5)

print("\n=== 5. start API ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-api", 30)
time.sleep(25)

print("\n=== 6. health ===")
_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/health", 10)
print(out)

print("\n=== 7. worker + nginx ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-worker nginx", 30)
time.sleep(5)

print("\n=== 8. smoke ===")
_, out, _ = run(hk, 'curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d \'{"username":"admin","password":"admin123"}\'', 10)
print("login:", out[:200])

_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/models", 10)
print("models:", out[:400])

_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/system/stats", 10)
print("stats:", out[:400])

_, out, _ = run(hk, 'curl -s -X POST http://localhost:8000/api/v1/analyze -H "Content-Type: application/json" -d \'{"camera_id":"test-cam","scene_type":"office","timestamp":"2026-07-23T12:00:00Z","frame":"/9j/4AAQSkZJRg=="}\'', 10)
print("analyze:", out[:200])

print("\n=== 9. ps ===")
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose ps", 10)
print(out)

print("\n=== 10. startup logs ===")
_, out, _ = run(hk, "docker logs aimp-api 2>&1 | head -20", 10)
print(out)
