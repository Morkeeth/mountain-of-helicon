#!/usr/bin/env bash
# Daily cross-check: helicon truth on SLASK, dashboard/registry, Claude memory.
# Human receipt + G6 JSON written by truth-daily-summary.py (single scan pass).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORE="${HELICON_HOME:-$HOME/.helicon}"

# cron's python3 is the system one and has no helicon package: run from the repo with the Python that has it.
PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
[ -x "$PY" ] || PY="python3"
cd "$SCRIPT_DIR/.." || exit 1
if PYTHONPATH="$SCRIPT_DIR/..${PYTHONPATH:+:$PYTHONPATH}" "$PY" "$SCRIPT_DIR/truth-daily-summary.py"; then
  echo "truth-daily: receipt $STORE/truth-daily-latest.txt · summary $STORE/truth-daily-summary.json"
else
  echo "truth-daily: FAILED $(date -u +%Y-%m-%dT%H:%M:%SZ), no receipt written" >&2
  exit 1
fi
