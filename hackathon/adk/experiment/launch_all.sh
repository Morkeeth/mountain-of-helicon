#!/usr/bin/env bash
# Launch hosted Cursor Cloud Agents for hackathon ADK slices.
# Requires: CURSOR_API_KEY + branch pushed to GitHub
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
BRANCH="${1:-hackathon/adk-cloud}"
SLICE="${2:-all}"

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  echo "ERROR: export CURSOR_API_KEY (https://cursor.com/dashboard → Integrations → API Keys)"
  exit 1
fi

chmod +x hackathon/adk/experiment/launch_cloud_agent.py

run_slice() {
  local prompt=$1 name=$2
  python3 hackathon/adk/experiment/launch_cloud_agent.py \
    --ref "$BRANCH" \
    --prompt "$prompt" \
    --name "$name" \
    --auto-pr
}

case "$SLICE" in
  1) run_slice hackathon/adk/experiment/PROMPT.md hackathon-adk-slice1 ;;
  2) run_slice hackathon/adk/experiment/PROMPT-SLICE2.md hackathon-adk-slice2-gcp ;;
  all)
    run_slice hackathon/adk/experiment/PROMPT.md hackathon-adk-slice1
    sleep 3
    run_slice hackathon/adk/experiment/PROMPT-SLICE2.md hackathon-adk-slice2-gcp
    ;;
  *) echo "Usage: CURSOR_API_KEY=... $0 [branch] [1|2|all]"; exit 1 ;;
esac
