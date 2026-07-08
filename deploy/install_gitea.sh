#!/bin/bash
set -e
cd /tmp
curl -s -c gitea_ck http://localhost:3000/ > install.html
CSRF_TOKEN=$(grep -oP '_csrf" value="[^"]+' install.html | head -1 | sed 's/_csrf" value="//')
curl -s -X POST http://localhost:3000/ \
  -b gitea_ck \
  --data-urlencode "_csrf=$CSRF_TOKEN" \
  --data-urlencode "db_type=PostgreSQL" \
  --data-urlencode "db_host=db:5432" \
  --data-urlencode "db_user=gitea" \
  --data-urlencode "db_passwd=gitea" \
  --data-urlencode "db_name=gitea" \
  --data-urlencode "ssl_mode=disable" \
  --data-urlencode "app_name=AIMiddlePlatform" \
  --data-urlencode "repo_root_path=/data/git/repositories" \
  --data-urlencode "run_user=git" \
  --data-urlencode "domain=192.168.3.122" \
  --data-urlencode "ssh_port=2222" \
  --data-urlencode "http_port=3000" \
  --data-urlencode "app_url=http://192.168.3.122:3000" \
  --data-urlencode "admin_name=taplo" \
  --data-urlencode "admin_passwd=rake.t.wang" \
  --data-urlencode "admin_email=taplo@local.host" \
  --data-urlencode "offline_mode=0" \
  --data-urlencode "disable_self_registration=1" \
  --data-urlencode "enable_captcha=0" | head -5
