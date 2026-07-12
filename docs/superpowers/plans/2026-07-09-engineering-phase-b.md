# Engineering Optimization (Option B) Implementation Plan

> **For agentic workers:** Tasks 1 and 3 are independent and can run in parallel. Task 2 (self-hosted runner) depends on the repo existing but is otherwise independent.

**Goal:** Turn the prototype into a continuously-deployed system with frontend-in-Docker, automatic deployment, and Redis-backed async processing.

**Architecture:** Three independent improvements: (1) multi-stage Dockerfile building Vue frontend into the image, (2) self-hosted GitHub Actions runner on VM2 for zero-touch deploy, (3) wire existing `RedisStreamQueue` into the ingest pipeline.

**Tech Stack:** Docker multi-stage build, Node 20, Python 3.12, GitHub Actions self-hosted runner, Redis Streams.

## Global Constraints

- Docker image must be `taplo/aimiddleplatform:*` (Docker Hub)
- Must work with existing `docker-compose.yml` (NGINX serves `/` from `/usr/share/nginx/html`)
- All existing tests must pass
- Self-hosted runner runs as `taplo` user on VM2 (192.168.3.123)
- Frontend build output goes to `frontend/dist/`

---

## File Structure

### Modified files
| File | Change |
|---|---|
| `Dockerfile` | Multi-stage: Node build → Python runtime; copy `frontend/dist` |
| `.github/workflows/ci.yml` | Add `deploy` job that runs on self-hosted runner |
| `src/queue/__init__.py` | Export `RedisStreamQueue` |
| `src/api/app.py` | Init `RedisStreamQueue` in lifespan; wire into ingestion route |
| `docker-compose.yml` | (possibly) Add healthcheck for redis, add network alias |

### New files
| File | Responsibility |
|---|---|
| `deploy/install-runner.sh` | One-time script to register VM2 as self-hosted runner |

### No test changes needed
- Frontend build and Redis wiring don't change existing test behavior

---

### Task 1: Multi-stage Dockerfile with Frontend Build

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Read current Dockerfile**

Current:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=300 -r requirements.txt
COPY config/ config/
COPY src/ src/
ENV PYTHONPATH="/app" APP_ENV="production"
EXPOSE 8000
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Rewrite as multi-stage build**

```dockerfile
# ---- Build frontend ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Python runtime ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=300 -r requirements.txt

COPY config/ config/
COPY src/ src/

COPY --from=frontend-builder /app/dist/ frontend/dist/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/health'); assert r.status==200"

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Verify build locally**

```bash
docker build -t aimp-test:latest .
```
Expected: Build succeeds, image contains `frontend/dist/index.html`

- [ ] **Step 4: Run tests**

```bash
uv run python -m pytest tests/ -q --tb=short
```
Expected: 126 passed

- [ ] **Step 5: Commit**

```bash
git add Dockerfile
git commit -m "build: multi-stage Dockerfile with Vue frontend"
```

---

### Task 2: Self-hosted GitHub Runner on VM2 + Deploy Job

**Files:**
- Create: `deploy/install-runner.sh`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Get runner registration token**

From local machine:
```bash
gh api repos/taplo/AIMiddlePlatform/actions/runners/registration-token --jq '.token'
```

- [ ] **Step 2: Create install script**

```bash
# deploy/install-runner.sh
# Run on VM2: bash deploy/install-runner.sh <TOKEN>
set -e
TOKEN=$1
if [ -z "$TOKEN" ]; then
  echo "Usage: $0 <GITHUB_RUNNER_TOKEN>"
  exit 1
fi

cd /opt
mkdir -p actions-runner && cd actions-runner

# Download latest runner
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-linux-x64-2.322.0.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# Configure (non-interactive)
./config.sh --url https://github.com/taplo/AIMiddlePlatform \
  --token "$TOKEN" \
  --name "vm2-runner" \
  --labels "vm2" \
  --unattended

# Install as service
sudo ./svc.sh install taplo
sudo ./svc.sh start
```

- [ ] **Step 3: SSH to VM2 and run the install script**

```bash
# On local machine:
$token = gh api repos/taplo/AIMiddlePlatform/actions/runners/registration-token --jq '.token'
# Copy script to VM2
scp deploy/install-runner.sh taplo@192.168.3.123:/tmp/
# Run on VM2
ssh taplo@192.168.3.123 "bash /tmp/install-runner.sh $token"
```

- [ ] **Step 4: Verify runner is online**

```bash
gh api repos/taplo/AIMiddlePlatform/actions/runners --jq '.runners[] | select(.status=="online") | .name'
```
Expected: `vm2-runner`

- [ ] **Step 5: Update CI workflow — add deploy job**

```yaml
  deploy:
    needs: build-and-push
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    runs-on: vm2
    steps:
      - name: Pull and restart
        run: |
          cd /opt/aimiddleplatform
          git pull origin master
          docker compose pull
          docker compose up -d
```

- [ ] **Step 6: Commit**

```bash
git add deploy/install-runner.sh .github/workflows/ci.yml
git commit -m "ci: add self-hosted runner deploy job"
```

---

### Task 3: Wire RedisStreamQueue into Ingestion Pipeline

**Files:**
- Modify: `src/queue/__init__.py`, `src/api/app.py`

- [ ] **Step 1: Export RedisStreamQueue from queue package**

```python
# src/queue/__init__.py
from src.queue.redis_streams import RedisStreamQueue

__all__ = ["RedisStreamQueue"]
```

- [ ] **Step 2: Wire into app lifespan**

In `src/api/app.py`:

1. Add import: `from src.queue import RedisStreamQueue`
2. In `_init_components`, at the end:
   ```python
   queue = RedisStreamQueue()
   from src.api.routes.ingest import init_queue
   init_queue(queue)
   ```

3. In `src/api/routes/ingest.py`, add:
   ```python
   _queue: RedisStreamQueue | None = None
   
   def init_queue(q: RedisStreamQueue) -> None:
       global _queue
       _queue = q
   ```

4. Modify the existing `register_stream` endpoint to push frames through the queue:
   ```python
   @router.post("/stream/register")
   async def register_stream(camera_id: str, ...):
       if _queue is None:
           raise HTTPException(500, "Queue not initialized")
       # existing logic...
       return {"ok": True, "queue": "redis_streams"}
   ```

- [ ] **Step 3: Run tests**

```bash
uv run python -m pytest tests/ -q --tb=short
```
Expected: 126 passed (all existing, no new tests needed for wiring)

- [ ] **Step 4: Commit**

```bash
git add src/queue/__init__.py src/api/app.py src/api/routes/ingest.py
git commit -m "feat: wire RedisStreamQueue into ingestion pipeline"
```

---

## Full Verification

```bash
uv run python -m pytest tests/ -q --tb=short
docker build -t aimp-test:latest .
docker run --rm aimp-test python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/health'); print(r.status)"
```

Expected: 126 tests pass, Docker build succeeds, healthcheck returns 200.

## Commit Ordering

1. `build: multi-stage Dockerfile with Vue frontend`
2. `ci: add self-hosted runner deploy job`
3. `feat: wire RedisStreamQueue into ingestion pipeline`
