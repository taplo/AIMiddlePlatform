#!/usr/bin/env python3
"""Upload and run smoke test against Docker Compose stack on 123."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import close_all, put_bytes, run

REMOTE_SCRIPT = """
import urllib.request, json

BASE = "http://localhost:8000"

# Login
req = urllib.request.Request(
    BASE + "/api/v1/auth/login",
    data=b'{"username":"admin","password":"change-me-in-production"}',
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
token = json.loads(resp.read())["access_token"]
print("TOKEN:", token[:40] + "...")

AUTH = {"Authorization": "Bearer " + token}

# Models
try:
    resp = urllib.request.urlopen(urllib.request.Request(BASE + "/api/v1/models/", headers=AUTH))
    print("MODELS:", json.dumps(json.loads(resp.read()), indent=2)[:600])
except urllib.error.HTTPError as e:
    print("MODELS ERR:", e.code, e.read().decode()[:300])

# Submit frame
try:
    frame_data = b'{"camera_id":"test-cam","scene_type":"office","timestamp":"2026-07-23T12:00:00Z","frame":"/9j/4AAQSkZJRg=="}'
    req = urllib.request.Request(
        BASE + "/api/v1/analyze/frame",
        data=frame_data,
        headers={"Content-Type": "application/json", **AUTH}
    )
    resp = urllib.request.urlopen(req)
    print("FRAME:", resp.read().decode()[:300])
except urllib.error.HTTPError as e:
    body = e.read().decode()[:300]
    print("FRAME ERR:", e.code, body)

# Ping
try:
    resp = urllib.request.urlopen(BASE + "/api/v1/analyze/ping")
    print("PING:", resp.read().decode()[:200])
except Exception as e:
    print("PING ERR:", e)

# Health
try:
    resp = urllib.request.urlopen(BASE + "/api/v1/health")
    print("HEALTH:", resp.read().decode()[:200])
except Exception as e:
    print("HEALTH ERR:", e)

print("SMOKE TEST DONE")
"""

put_bytes("123", REMOTE_SCRIPT.encode(), "/home/taplo/smoke_test_final.py")
code, out, err = run("123", "/home/taplo/AIMiddlePlatform/venv/bin/python3 /home/taplo/smoke_test_final.py", timeout=30)
print(out)
if err:
    print("STDERR:", err[:1000])
print("Exit:", code)
close_all()
