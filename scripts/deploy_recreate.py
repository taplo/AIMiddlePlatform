#!/usr/bin/env python3
"""Recreate containers and smoke test."""
import sys
import time
sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

print("=== recreate API ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-api --force-recreate", 60)
time.sleep(15)

print("=== health ===")
_, out, _ = run(hk, "curl -s http://localhost:8000/api/v1/health", 10)
print(out)

print("=== recreate worker ===")
run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-worker --force-recreate", 30)
time.sleep(5)

print("=== login ===")
_, out, _ = run(hk, """curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'""", 10)
print(out)

print("=== compose ps ===")
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose ps", 10)
print(out)
