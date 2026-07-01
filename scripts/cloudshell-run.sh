#!/usr/bin/env bash
# Run GLAZE inside Alibaba Cloud Shell as proof the backend runs on Alibaba Cloud.
# Slim mode: skips torch/sentence-transformers (~2GB) so it fits Cloud Shell disk.
# The dashboard, scores, cubes, consolidations, reviews all work from the DB;
# only semantic query-search degrades to keyword (fine for a proof/demo).
#
# Prereqs in Cloud Shell (once the shell opens for your account):
#   1. Get the code:   git clone <your-public-repo-url> glaze && cd glaze
#   2. Provide the DB: upload data/glaze.db (Cloud Shell "Upload File"), or run a scan
#   3. Provide the key: export QWEN_API_KEY='sk-...'   (do NOT hardcode)
#   4. Run this:        bash scripts/cloudshell-run.sh
# Then use Cloud Shell "Web Preview" on port 8420 to view + screenshot + record.
set -euo pipefail

PORT="${PORT:-8420}"

echo "==> Installing slim deps (no torch)"
pip install --quiet --user openai fastapi uvicorn pyyaml gitpython numpy

echo "==> Staging web UI (app serves from ./static)"
mkdir -p static && cp -r web/dist/. static/ 2>/dev/null || echo "  (no web/dist found; API will work, UI limited)"

if [ ! -f config.json ]; then
  echo "==> No config.json; generating one from \$QWEN_API_KEY (connectors off - serve only)"
  : "${QWEN_API_KEY:?set QWEN_API_KEY first: export QWEN_API_KEY='sk-...'}"
  cat > config.json <<JSON
{
  "db_path": "data/glaze.db",
  "qwen_api_key": "${QWEN_API_KEY}",
  "qwen_model": "qwen-plus",
  "qwen_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
  "connectors": {},
  "server": {"host": "0.0.0.0", "port": ${PORT}, "password": ""}
}
JSON
fi

if [ ! -f data/glaze.db ]; then
  echo "!! data/glaze.db missing. Upload it (Cloud Shell Upload File) or run: python3 -m glaze.cli scan"
  exit 1
fi

echo "==> Starting GLAZE on 0.0.0.0:${PORT}"
echo "    Open Cloud Shell 'Web Preview' -> port ${PORT} to view, then screenshot + record."
exec python3 -m uvicorn glaze.api.app:app --host 0.0.0.0 --port "${PORT}"
