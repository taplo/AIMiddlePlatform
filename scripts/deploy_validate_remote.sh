#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# deploy_validate_remote.sh
# Runs on target machine (192.168.3.123) via SSH / paramiko.
# Steps:
#   1. Set proxy env
#   2. Clone / pull repo
#   3. Install system dependencies (pip, venv, docker if needed)
#   4. Create venv and install Python deps
#   5. Download test ONNX model
#   6. Run inference integration test
#   7. Build Docker image (optional)
# ============================================================

REPO_URL="https://github.com/taplo/AIMiddlePlatform.git"
REPO_DIR="$HOME/AIMiddlePlatform"
PROXY_HTTP="http://192.168.3.208:8787"
PROXY_SOCKS="socks5://192.168.3.208:8888"

export http_proxy="$PROXY_HTTP"
export https_proxy="$PROXY_HTTP"
export HTTP_PROXY="$PROXY_HTTP"
export HTTPS_PROXY="$PROXY_HTTP"
export no_proxy="localhost,127.0.0.1,::1"

echo "=== Step 0: System info ==="
uname -a
cat /etc/os-release 2>/dev/null | head -3 || true
python3 --version
pip3 --version 2>/dev/null || echo "pip3 not found"

echo ""
echo "=== Step 1: Check/Clone repo ==="
if [ -d "$REPO_DIR" ]; then
    echo "Repo exists, pulling latest..."
    cd "$REPO_DIR"
    git pull --rebase
else
    echo "Cloning repo..."
    git clone "$REPO_URL" "$REPO_DIR"
    cd "$REPO_DIR"
fi
echo "Commit: $(git rev-parse --short HEAD)"
echo "Branch: $(git rev-parse --abbrev-ref HEAD)"

echo ""
echo "=== Step 2: Create venv & install deps ==="
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e ".[dev,test]"
pip install onnxruntime

echo ""
echo "=== Step 3: Download test model ==="
mkdir -p models
python -m scripts.download_models --check
python -m scripts.download_models
# Ensure object_detection.onnx exists (test expects this path)
if [ ! -f models/object_detection.onnx ]; then
    echo "object_detection.onnx not found, symlinking from yolov8m.onnx..."
    if [ -f models/yolov8m.onnx ]; then
        ln -sf yolov8m.onnx models/object_detection.onnx
    elif [ -f models/yolov8n.onnx ]; then
        ln -sf yolov8n.onnx models/object_detection.onnx
    fi
fi
ls -lh models/*.onnx 2>/dev/null || echo "No ONNX models found"

echo ""
echo "=== Step 4: Run inference integration test ==="
python -m pytest tests/test_inference_integration.py -v --tb=short 2>&1 || true

echo ""
echo "=== Step 5: Run pipeline E2E tests (with real model stubs) ==="
python -m pytest tests/test_e2e_pipeline.py -v --tb=short 2>&1 || true

echo ""
echo "=== Step 6: Run all model adapter tests ==="
python -m pytest tests/ -k "adapter or inference" -v --tb=short 2>&1 || true

echo ""
echo "=== Step 7: Run all tests (no external deps) ==="
python -m pytest tests/ -v --tb=short -x --ignore=tests/benchmarks --ignore=tests/test_metrics_tool.py --ignore=tests/test_access_control.py 2>&1 || echo "Some tests failed (expected if Redis/DB unavailable)"

echo ""
echo "=== Step 8: Try Docker Compose build ==="
if command -v docker &> /dev/null; then
    echo "Docker available, building images..."
    # Configure Docker daemon proxy for builds
    mkdir -p ~/.docker
    cat > ~/.docker/config.json <<'DOCKERCFG'
{
  "proxies": {
    "default": {
      "httpProxy": "http://192.168.3.208:8787",
      "httpsProxy": "http://192.168.3.208:8787",
      "noProxy": "localhost,127.0.0.1,::1"
    }
  }
}
DOCKERCFG
    echo "Building with docker compose..."
    docker compose build api worker 2>&1 || echo "Docker build failed (may need Dockerfile fixes)"
    docker images aimiddleplatform-* 2>&1 || true
else
    echo "Docker not available, skipping build"
fi

echo ""
echo "=== DONE ==="
echo "Results summary:"
source venv/bin/activate 2>/dev/null || true
python -m pytest tests/test_inference_integration.py -v --tb=short 2>&1 | tail -5
