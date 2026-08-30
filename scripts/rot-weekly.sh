#!/usr/bin/env bash
# Weekly rot pass: registry + checkouts gates (companion to daily truth).
set -uo pipefail

HELICON="${HELICON:-helicon}"
STORE="${HELICON_HOME:-$HOME/.helicon}"
RECEIPT="$STORE/rot-weekly-latest.txt"
DAY="$(date -Iseconds)"

mkdir -p "$STORE"
{
  echo "=== helicon rot-weekly · $DAY ==="
  echo ""
  echo "--- registry ---"
  "$HELICON" registry 2>&1 || echo "[warn] registry failed"
  echo ""
  echo "--- checkouts ---"
  "$HELICON" checkouts 2>&1 || echo "[warn] checkouts failed"
  echo ""
  echo "=== end $DAY ==="
} | tee "$RECEIPT"

echo "rot-weekly: receipt $RECEIPT"
