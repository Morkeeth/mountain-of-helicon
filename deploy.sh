#!/usr/bin/env bash
# One-shot deploy to an Alibaba Simple Application Server (SWAS) box.
# Usage: ./deploy.sh root@<public-ip>
# Ships code + prebuilt web/dist + real config.json + seeded glaze.db, then
# builds and runs the container on the server. Requires: web/dist built locally
# (cd web && npx vite build) and a working config.json in this dir.
set -euo pipefail

TARGET="${1:?usage: ./deploy.sh root@<public-ip>}"
REMOTE_DIR="/opt/glaze"

echo "==> Checking local prerequisites"
[ -d web/dist ] || { echo "web/dist missing - run: (cd web && npx vite build)"; exit 1; }
[ -f config.json ] || { echo "config.json missing"; exit 1; }
[ -f data/glaze.db ] || { echo "data/glaze.db missing"; exit 1; }

echo "==> Ensuring Docker on $TARGET"
ssh "$TARGET" 'command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sh)'

echo "==> Syncing project to $TARGET:$REMOTE_DIR (excluding node_modules, .git)"
ssh "$TARGET" "mkdir -p $REMOTE_DIR"
rsync -az --delete \
  --exclude 'web/node_modules' --exclude '.git' --exclude '__pycache__' \
  --exclude 'data/compiled' \
  ./ "$TARGET:$REMOTE_DIR/"

echo "==> Building and starting container"
ssh "$TARGET" "cd $REMOTE_DIR && docker compose -f docker-compose.deploy.yml up -d --build"

echo "==> Waiting for health"
ssh "$TARGET" 'for i in $(seq 1 30); do curl -sf http://localhost/api/score >/dev/null && break || sleep 3; done'

IP="${TARGET#*@}"
echo "==> Deployed. Open: http://$IP/"
echo "    Remember to open port 80 in the SWAS firewall/security rules."
