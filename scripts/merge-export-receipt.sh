#!/usr/bin/env bash
# Merge helicon export receipt into a repo's AGENTS.md (marked block, replaceable).
# Usage: merge-export-receipt.sh [repo-root] [run-id]
set -euo pipefail

REPO_ROOT="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
AGENTS="$REPO_ROOT/AGENTS.md"
DB="${HELICON_DB:-$HOME/.helicon/helicon.db}"
HELICON="${HELICON:-helicon}"
RUN_ID="${2:-}"

if [[ ! -f "$AGENTS" ]]; then
  echo "no AGENTS.md at $AGENTS" >&2
  exit 1
fi

if [[ -z "$RUN_ID" ]]; then
  base="$(basename "$REPO_ROOT")"
  RUN_ID="$(sqlite3 "$DB" \
    "SELECT id FROM task_runs WHERE repo_ref LIKE '%${base}%' ORDER BY opened_at DESC LIMIT 1;" 2>/dev/null || true)"
fi

if [[ -z "$RUN_ID" ]]; then
  echo "no governed run found for $(basename "$REPO_ROOT")" >&2
  exit 1
fi

TMP="$(mktemp -t helicon-export.XXXXXX.json)"
"$HELICON" export "$RUN_ID" -o "$TMP"

export MERGE_AGENTS="$AGENTS" MERGE_TMP="$TMP" MERGE_RUN_ID="$RUN_ID"
python3 <<'PY'
import json, re, pathlib, datetime, os

agents = pathlib.Path(os.environ["MERGE_AGENTS"])
payload = json.loads(pathlib.Path(os.environ["MERGE_TMP"]).read_text())
run = payload.get("run") or {}
receipt = (payload.get("receipt") or "").strip()
run_id = payload.get("task_run_id") or os.environ["MERGE_RUN_ID"]
opened = run.get("opened_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
status = run.get("status") or "unknown"
objective = (run.get("objective") or "").strip().replace("\n", " ")[:200]

block = (
    "## Governed run receipts (helicon export)\n\n"
    "<!-- HELICON-RUN-RECEIPT START -->\n"
    f"### {run_id} · {opened[:10]} · {status}\n\n"
    f"**Objective:** {objective}\n\n"
    "```\n"
    f"{receipt}\n"
    "```\n"
    "<!-- HELICON-RUN-RECEIPT END -->\n"
)

text = agents.read_text(encoding="utf-8")
if "<!-- HELICON-RUN-RECEIPT START -->" in text:
    text = re.sub(
        r"\n?## Governed run receipts.*?<!-- HELICON-RUN-RECEIPT END -->\n?",
        "\n\n" + block + "\n",
        text,
        count=1,
        flags=re.S,
    )
else:
    text = text.rstrip() + "\n\n" + block + "\n"

agents.write_text(text, encoding="utf-8")
print(f"merged {run_id} -> {agents}")
PY

rm -f "$TMP"
