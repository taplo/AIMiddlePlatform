#!/usr/bin/env python3
"""Diagnose and fix deployment issues on 123."""
import sys
import time
sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

def cmd(c, t=30):
    ec, out, err = run(hk, c, t)
    return out, err, ec

print("=== API logs ===")
out, err, _ = cmd("docker logs aimp-api 2>&1", 10)
print(out[:2000])
print("STDERR:", err[:500])

print("\n=== Worker logs ===")
out, err, _ = cmd("docker logs aimp-worker 2>&1", 10)
print(out[:1000])
print("STDERR:", err[:500])

print("\n=== compose config ===")
out, _, _ = cmd("cd /home/taplo/AIMiddlePlatform && docker compose config --services 2>&1", 10)
print(out)

print("\n=== stop all ===")
cmd("cd /home/taplo/AIMiddlePlatform && docker compose down --remove-orphans", 30)
