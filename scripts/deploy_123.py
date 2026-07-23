#!/usr/bin/env python3
"""Deploy latest code on 123, rebuild Docker image, compose up, smoke test."""
import sys
import time

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

def step(label, cmd, timeout=60):
    print(f"\n=== {label} ===")
    ec, out, err = run(hk, cmd, timeout)
    if out:
        print(out[:1000])
    if err:
        print("STDERR:", err[:500])
    if ec != 0:
        print(f"[WARN] exit code {ec}")
    return ec, out, err

step("git pull", "cd /home/taplo/AIMiddlePlatform && git pull origin master", 60)

step("docker build", (
    "cd /home/taplo/AIMiddlePlatform && "
    "docker build -t taplo/aimiddleplatform:latest --network=host "
    "--build-arg http_proxy=http://192.168.3.208:8787 "
    "--build-arg https_proxy=http://192.168.3.208:8787 ."
), 600)

step(".env", "cd /home/taplo/AIMiddlePlatform && test -f .env || cp .env.example .env")
step("jwt secret",
     'cd /home/taplo/AIMiddlePlatform && '
     'grep -q "change-me" .env && '
     'sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=deploy-$(date +%s)-$(hostname)/" .env || true')

step("models dir", "mkdir -p /home/taplo/AIMiddlePlatform/models")

step("compose down", "cd /home/taplo/AIMiddlePlatform && docker compose down --remove-orphans", 30)
step("start redis", "cd /home/taplo/AIMiddlePlatform && docker compose up -d redis", 30)
print("  waiting 5s for redis...")
time.sleep(5)

step("start API", "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-api", 30)
print("  waiting 25s for API...")
time.sleep(25)

step("health check", "curl -s http://localhost:8000/api/v1/health", 10)

step("start worker + nginx", "cd /home/taplo/AIMiddlePlatform && docker compose up -d aimp-worker nginx", 30)
time.sleep(5)

step("smoke test", "cd /home/taplo/AIMiddlePlatform && python3 scripts/compose_smoke_test.py 2>&1", 30)

print("\n=== compose ps ===")
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose ps", 10)
print(out)

print("\n=== logs (last 15 lines) ===")
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose logs --tail=15 aimp-api", 15)
print("API:", out[:2000])
_, out, _ = run(hk, "cd /home/taplo/AIMiddlePlatform && docker compose logs --tail=10 aimp-worker", 15)
print("Worker:", out[:2000])
