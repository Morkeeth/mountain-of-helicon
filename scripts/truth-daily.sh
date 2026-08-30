#!/usr/bin/env bash
# Daily cross-check: helicon truth on SLASK, dashboard/registry, Claude memory.
# Human receipt + G6 JSON written by truth-daily-summary.py (single scan pass).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORE="${HELICON_HOME:-$HOME/.helicon}"

python3 "$SCRIPT_DIR/truth-daily-summary.py"
echo "truth-daily: receipt $STORE/truth-daily-latest.txt · summary $STORE/truth-daily-summary.json"
