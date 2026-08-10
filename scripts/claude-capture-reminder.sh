#!/bin/bash
# Claude Code Stop hook for Mount Helicon's local Work Graph capture loop.
#
# It is deliberately a reminder, never a blocker or writer. A coding agent can
# pause for a legitimate human decision; it must not silently leave a captured
# run at "executing" or "artifact_attached" and later call that work measured.
set -uo pipefail

INPUT=$(cat)
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)

# Global Claude settings invoke this hook, but it has no effect outside this
# repository. Fail open on missing jq, payload fields, or a local DB.
[ "$CWD" = "$ROOT" ] || exit 0
DB="${HELICON_CAPTURE_DB:-$ROOT/data/helicon.db}"
[ -f "$DB" ] || exit 0

PENDING=$(python3 - "$DB" <<'PY' 2>/dev/null
import sqlite3, sys
try:
    conn = sqlite3.connect(sys.argv[1])
    rows = conn.execute("""
        SELECT w.id, tr.id, tr.status
        FROM work_wagers w JOIN task_runs tr ON tr.id=w.task_run_id
        WHERE w.status='open' AND tr.task_class='agentic-work'
          AND tr.status IN ('executing', 'artifact_attached')
        ORDER BY tr.execution_started_at ASC
    """).fetchall()
    print("; ".join(f"{w}/{r} ({s})" for w, r, s in rows))
except Exception:
    pass
PY
)

[ -n "$PENDING" ] || exit 0
jq -n --arg pending "$PENDING" '{
  systemMessage: ("⚠ Helicon capture: open recorded run(s) still need closeout — " + $pending + ". " +
    "Before claiming this work measured or verified, call helicon_capture_closeout with real artifact paths and the human verification receipt. " +
    "It is valid to leave it open when the human has not verified it yet.")
}'
