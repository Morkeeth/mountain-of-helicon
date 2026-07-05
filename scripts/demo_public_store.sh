#!/usr/bin/env bash
# Audit a memory store you don't own.
#
# Points the drift demo + rot exam at a PUBLIC repo's committed agent-rules
# file — by default openai/codex's AGENTS.md, which OpenAI edits weekly. The
# store is a throwaway DB built from that repo's real git history; nothing
# here touches your own memory. Zero fake data: real commits, cited by SHA
# in the output, reproducible by anyone.
#
# Usage: bash scripts/demo_public_store.sh [repo_url] [rules_file] [task]
set -euo pipefail

URL="${1:-https://github.com/openai/codex}"
RULES="${2:-AGENTS.md}"
TASK="${3:-how do I run tests and formatting before committing}"

HERE="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${TMPDIR:-/tmp}/helicon-public-store"
NAME="$(basename "$URL" .git)"
CLONE="$CACHE/$NAME"

mkdir -p "$CACHE"
if [ ! -d "$CLONE/.git" ]; then
  echo "cloning $URL (shallow, then deepened for file history)..."
  git clone --depth 50 --quiet "$URL" "$CLONE"
  git -C "$CLONE" fetch --quiet --deepen=3000 || true
fi

DEMO_REPO="$CLONE" DEMO_RULES_FILE="$RULES" DEMO_TASK="$TASK" \
  python3 "$HERE/scripts/demo_realdrift.py"
