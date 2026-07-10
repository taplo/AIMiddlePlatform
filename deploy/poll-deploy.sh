#!/bin/bash
set -e
WORK_DIR=/opt/aimiddleplatform
STATUS_FILE=/tmp/deploy_status.json
PROXY=http://192.168.3.208:8787

cd "$WORK_DIR"

CURRENT_DIGEST=$(docker inspect --format '{{index .RepoDigests 0}}' taplo/aimiddleplatform:latest 2>/dev/null || echo "none")

LATEST_JSON=$(curl -sL --connect-timeout 15 --max-time 30 -x "$PROXY" \
  "https://hub.docker.com/v2/repositories/taplo/aimiddleplatform/tags/latest" 2>/dev/null)
LATEST_DIGEST=$(echo "$LATEST_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    images = d.get('images', [])
    for img in images:
        if img.get('architecture') == 'amd64':
            print(img['digest'])
            break
    else:
        print('unknown')
except:
    print('unknown')
" 2>/dev/null)

echo "[$(date)] Current: $CURRENT_DIGEST"
echo "[$(date)] Latest:  $LATEST_DIGEST"

if [ "$CURRENT_DIGEST" != "$LATEST_DIGEST" ] && [ "$LATEST_DIGEST" != "unknown" ] && [ -n "$LATEST_DIGEST" ]; then
  echo "[$(date)] New image detected. Deploying..."
  echo "{\"status\":\"deploying\",\"started_at\":\"$(date -Iseconds)\"}" > $STATUS_FILE

  docker compose pull
  docker compose up -d

  echo "{\"status\":\"deployed\",\"finished_at\":\"$(date -Iseconds)\"}" > $STATUS_FILE
  echo "[$(date)] Deploy complete"
else
  echo "[$(date)] No update needed"
fi
