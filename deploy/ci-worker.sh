#!/bin/bash
set -e
WORK_DIR=/opt/aimiddleplatform
REPO_URL=http://taplo:rake.t.wang@192.168.3.122:3000/taplo/aimiddleplatform.git
STATUS_FILE=/tmp/ci_status.json
VENV_DIR=$WORK_DIR/.venv

cd "$WORK_DIR"
if [ ! -d .git ]; then
  git clone "$REPO_URL" .
fi

LATEST_REMOTE=$(git ls-remote "$REPO_URL" main | awk '{print $1}')
LATEST_LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "none")

if [ "$LATEST_REMOTE" != "$LATEST_LOCAL" ]; then
  echo "[$(date)] New commit detected: $LATEST_REMOTE"
  git fetch "$REPO_URL" main
  git reset --hard FETCH_HEAD

  echo "{\"commit\":\"$LATEST_REMOTE\",\"status\":\"running\",\"started_at\":\"$(date -Iseconds)\"}" > $STATUS_FILE

  python3 -m venv $VENV_DIR
  $VENV_DIR/bin/python -m ensurepip --upgrade
  $VENV_DIR/bin/pip3 install uv -q
  python3 -m uv sync --no-install-project --directory $WORK_DIR
  $VENV_DIR/bin/pip3 install pytest pytest-asyncio httpx -q

  export PYTHONPATH=$WORK_DIR:$PYTHONPATH

  if $VENV_DIR/bin/python -m pytest tests/ -v > /tmp/ci_output.txt 2>&1; then
    echo "{\"commit\":\"$LATEST_REMOTE\",\"status\":\"passed\",\"finished_at\":\"$(date -Iseconds)\"}" > $STATUS_FILE
    echo "Tests PASSED. Deploying..."
    set +e
    cd $WORK_DIR && docker compose up -d --build > /tmp/deploy_output.txt 2>&1
    if [ $? -eq 0 ]; then
      echo "Deploy SUCCESS"
      echo "{\"commit\":\"$LATEST_REMOTE\",\"status\":\"deployed\",\"finished_at\":\"$(date -Iseconds)\"}" > $STATUS_FILE
    else
      echo "Deploy FAILED. See /tmp/deploy_output.txt"
    fi
    set -e
  else
    echo "{\"commit\":\"$LATEST_REMOTE\",\"status\":\"failed\",\"finished_at\":\"$(date -Iseconds)\"}" > $STATUS_FILE
    echo "Tests FAILED. See /tmp/ci_output.txt"
  fi
fi
