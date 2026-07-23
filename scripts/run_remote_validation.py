#!/usr/bin/env python3
"""Upload and run validation on remote machine. Uses base64 to avoid shell quoting issues."""

import base64
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import put_bytes, run, close_all

HOST = "123"
VENV_PYTHON = "/home/taplo/AIMiddlePlatform/venv/bin/python3"
WORK_DIR = "/home/taplo/AIMiddlePlatform"

# The validation script, base64-encoded to avoid shell escaping issues
VALIDATION_SCRIPT = r"""
import os, sys
os.chdir("/home/taplo/AIMiddlePlatform")
sys.path = ["/home/taplo/AIMiddlePlatform/venv/lib/python3.14/site-packages"] + sys.path
os.environ["PATH"] = "/home/taplo/AIMiddlePlatform/venv/bin:" + os.environ.get("PATH", "")

for k in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY"]:
    os.environ.pop(k, None)

import site
site.addsitedir("/home/taplo/AIMiddlePlatform/venv/lib/python3.14/site-packages")

# === 1. Import check ===
print("=== Step 1: Import check ===")
for mod_name in ["onnxruntime","cv2","numpy","pytest","sqlalchemy","opentelemetry","minio","prometheus_client","jose","fastapi","pydantic"]:
    try:
        m = __import__(mod_name)
        v = getattr(m, "__version__", "ok")
        print(f"  {mod_name:25s} {v}")
    except Exception as e:
        print(f"  {mod_name:25s} MISSING: {e}")

# === 2. Model files ===
print("\n=== Step 2: Model files ===")
import pathlib
for f in sorted(pathlib.Path("models").glob("*.onnx")):
    print(f"  {f.name}: {f.stat().st_size/1e6:.1f} MB")

# === 3. Verify skip condition ===
print("\n=== Step 3: Skip condition check ===")
test_file = pathlib.Path("tests/test_inference_integration.py")
model_path = test_file.resolve().parent.parent / "models" / "object_detection.onnx"
print(f"  Test file resolve: {test_file.resolve()}")
print(f"  Model path (parent.parent / models / object_detection.onnx): {model_path}")
print(f"  Model exists: {model_path.exists()}")

# === 4. Run inference integration test ===
print("\n=== Step 4: test_inference_integration.py ===")
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_inference_integration.py", "-v", "--tb=long", "-s"],
    capture_output=True, text=True, timeout=60
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr[:2000])
print(f"Exit: {result.returncode}")

# === 5. YOLOv8 adapter unit test ===
print("\n=== Step 5: test_yolov8_adapter.py ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_yolov8_adapter.py", "-v", "--tb=long", "-s"],
    capture_output=True, text=True, timeout=60
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr[:2000])
print(f"Exit: {result.returncode}")

# === 6. Run adapter + inference tests ===
print("\n=== Step 6: adapter + inference tests ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-k", "adapter or inference", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=120
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr[:2000])
print(f"Exit: {result.returncode}")

# === 7. E2E pipeline tests ===
print("\n=== Step 7: test_e2e_pipeline.py ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_e2e_pipeline.py", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=60
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr[:2000])
print(f"Exit: {result.returncode}")

# === 8. All tests (excluding benchmarks, external deps) ===
print("\n=== Step 8: Full test suite ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short",
     "--ignore=tests/benchmarks",
     "--ignore=tests/test_metrics_tool.py",
     "--ignore=tests/test_access_control.py",
     "-x"],
    capture_output=True, text=True, timeout=120
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr[:2000])
print(f"Exit: {result.returncode}")

print("\n=== DONE ===")
"""

# Encode, upload, execute
encoded = base64.b64encode(VALIDATION_SCRIPT.encode("utf-8")).decode("ascii")
put_bytes(HOST, encoded.encode("utf-8"), "/home/taplo/validation_b64.txt")

cmd = (
    f"cd {WORK_DIR} && "
    f"python3 -c \"import base64, sys; open('/home/taplo/validate_remote.py','w').write(base64.b64decode(open('/home/taplo/validation_b64.txt').read()).decode())\" && "
    f"chmod +x /home/taplo/validate_remote.py && "
    f"{VENV_PYTHON} /home/taplo/validate_remote.py"
)
code, out, err = run(HOST, cmd, timeout=300)
print(out)
if err:
    print("STDERR:", err[:3000], file=sys.stderr)
print(f"Final exit: {code}", file=sys.stderr)
close_all()
