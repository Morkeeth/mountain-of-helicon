#!/usr/bin/env bash
# Daily cross-check: helicon truth on SLASK, dashboard/registry, Claude memory.
# Receipt: ~/.helicon/truth-daily.log (cron appends) + truth-daily-latest.txt
set -uo pipefail

HELICON="${HELICON:-/Library/Frameworks/Python.framework/Versions/3.12/bin/helicon}"
VAULT="${OBSIDIAN_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian LIFE}"
STORE="${HELICON_HOME:-$HOME/.helicon}"
RECEIPT="$STORE/truth-daily-latest.txt"
DAY="$(date -Iseconds)"

SLASK="$VAULT/! ❄SLASK 🧊"
DASH="$VAULT/00 Dashboard"
MEMORY="${CLAUDE_MEMORY:-$HOME/.claude/projects/-Users-morkeeth/memory}"

mkdir -p "$STORE"
{
  echo "=== helicon truth daily · $DAY ==="
  while IFS='|' read -r label path; do
    echo ""
    echo "--- $label · $path ---"
    if [[ -e "$path" ]]; then
      "$HELICON" truth "$path" 2>&1 || echo "[warn] truth failed on $label"
    else
      echo "[skip] path missing: $path"
    fi
  done <<EOF
SLASK|$SLASK
dashboard|$DASH
claude-memory|$MEMORY
EOF
  echo ""
  echo "=== end $DAY ==="
} | tee "$RECEIPT"

FLAGGED=$(grep -E '^[[:space:]]+[0-9]+[[:space:]]+[0-9]+' "$RECEIPT" | wc -l | tr -d ' ')
echo "truth-daily: $FLAGGED flagged row(s) · receipt $RECEIPT"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/truth-daily-summary.py"
