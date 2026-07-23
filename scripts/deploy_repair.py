#!/usr/bin/env python3
"""Fix deployment issues on 123 and run full smoke test."""
import sys

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"

def step(label, cmd, timeout=120):
    print(f"\n=== {label} ===")
    ec, out, err = run(hk, cmd, timeout)
    if out:
        print(out[:2000])
    if err:
        print("STDERR:", err[:1000])
    return ec, out, err

# Check what went wrong with the build
step("check previous build fail", "cd /home/taplo/AIMiddlePlatform && docker build -t taplo/aimiddleplatform:latest --network=host --build-arg http_proxy=http://192.168.3.208:8787 --build-arg https_proxy=http://192.168.3.208:8787 . 2>&1 | tail -30", 600)

# If build still fails, try without proxy
step("try build without proxy", "cd /home/taplo/AIMiddlePlatform && docker build -t taplo/aimiddleplatform:latest . 2>&1 | tail -30", 600)
