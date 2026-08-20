#!/usr/bin/env bash
# Manual trigger — POST /run on Cloud Run (Pub/Sub topic created at deploy time).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${REGION:-us-central1}"
SERVICE="${AGENT_SERVICE:-helicon-measurement-bench}"
TOPIC="${PUBSUB_TOPIC:-helicon-measurement-trigger}"

URL="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo "POST ${URL}/run (trigger=manual)"
HTTP_CODE="$(curl -sS -o /tmp/helicon-run-response.json -w '%{http_code}' \
  -X POST "${URL}/run" \
  -H "X-Trigger: manual" \
  -H "Content-Type: application/json")"

echo "HTTP ${HTTP_CODE}"
if [[ "${HTTP_CODE}" -ge 200 && "${HTTP_CODE}" -lt 300 ]]; then
  python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/helicon-run-response.json").read_text())
print("run_id:", d.get("run_id"))
print("unmeasurable_count:", d.get("science", {}).get("unmeasurable_count"))
PY
else
  cat /tmp/helicon-run-response.json
  exit 1
fi

echo ""
echo "Pub/Sub audit tick (optional):"
echo "  gcloud pubsub topics publish ${TOPIC} --project=${PROJECT} --message='manual trigger'"
