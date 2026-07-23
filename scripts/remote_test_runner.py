#!/usr/bin/env python3
"""Run tests on remote machine via SSH. Uploads and executes a test script."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import close_all, put_bytes, run

test_script = r"""
import sys
import os
os.chdir("/home/taplo/AIMiddlePlatform")
os.environ["PATH"] = "/home/taplo/AIMiddlePlatform/venv/bin:" + os.environ.get("PATH", "")
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

# Add venv site-packages to path
import site
site.addsitedir("/home/taplo/AIMiddlePlatform/venv/lib/python3.14/site-packages")

# 1. Verify imports
print("=== Imports ===")
import onnxruntime
import cv2
import numpy as np
import pytest
print(f"onnxruntime: {onnxruntime.__version__}")
print(f"cv2: {cv2.__version__}")
print(f"numpy: {np.__version__}")
print(f"pytest: {pytest.__version__}")

# 2. Verify model files
import pathlib
model_dir = pathlib.Path("models")
onnx_files = list(model_dir.glob("*.onnx"))
print(f"\n=== Models ({len(onnx_files)} found) ===")
for f in onnx_files:
    print(f"  {f.name}: {f.stat().st_size / 1e6:.1f} MB")

# 3. Run inference test
print("\n=== Running test_inference_integration.py ===")
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_inference_integration.py", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=60,
    env={**os.environ}
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:1000])
print(f"Exit code: {result.returncode}")

# 4. Run pipeline e2e tests
print("\n=== Running test_e2e_pipeline.py ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_e2e_pipeline.py", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=60,
    env={**os.environ}
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:1000])
print(f"Exit code: {result.returncode}")

# 5. Run adapter tests
print("\n=== Running adapter tests ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-k", "adapter or inference", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=60,
    env={**os.environ}
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:1000])
print(f"Exit code: {result.returncode}")

# 6. Run full test suite (non-DB, non-Redis)
print("\n=== Running main test suite ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short",
     "--ignore=tests/benchmarks",
     "--ignore=tests/test_metrics_tool.py",
     "--ignore=tests/test_access_control.py",
     "-x"],
    capture_output=True, text=True, timeout=120,
    env={**os.environ}
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:2000])
print(f"Exit code: {result.returncode}")

# 7. Run adapter-specific tests (ascend, cambricon)
print("\n=== Running HW adapter tests ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-k", "ascend or cambricon", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=60,
    env={**os.environ}
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:500])
print(f"Exit code: {result.returncode}")

print("\n=== ALL DONE ===")
"""

host_key = "123"
put_bytes(host_key, test_script.encode("utf-8"), "/home/taplo/run_validation.py")
code, out, err = run(host_key, "cd /home/taplo/AIMiddlePlatform && /home/taplo/AIMiddlePlatform/venv/bin/python3 /home/taplo/run_validation.py", timeout=300)
print(out)
if err:
    print("STDERR:", err[:2000], file=sys.stderr)
print(f"Final exit code: {code}", file=sys.stderr)
close_all()
