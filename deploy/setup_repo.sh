#!/bin/bash
set -e
# Create repository
curl -s -X POST http://localhost:3000/api/v1/user/repos \
  -u taplo:rake.t.wang \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"aimiddleplatform","description":"AI Algorithm Scheduling Platform","private":false,"auto_init":false}'
echo ""
# Generate runner token
curl -s -X POST http://localhost:3000/api/v1/users/taplo/tokens \
  -u taplo:rake.t.wang \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"runner-token","scopes":["write:repository","write:user"]}'
