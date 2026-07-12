#!/bin/bash
set -e
TOKEN=$1
if [ -z "$TOKEN" ]; then
  echo "Usage: $0 <GITHUB_RUNNER_TOKEN>"
  exit 1
fi

cd /opt
mkdir -p actions-runner && cd actions-runner

curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-linux-x64-2.322.0.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

./config.sh --url https://github.com/taplo/AIMiddlePlatform \
  --token "$TOKEN" \
  --name "vm2-runner" \
  --labels "vm2" \
  --unattended

sudo ./svc.sh install taplo
sudo ./svc.sh start
