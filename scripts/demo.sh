#!/usr/bin/env bash
# Mountain of Helicon — the 3-minute demo.
#
# The story, end to end, on REAL public repos and a live gate:
#   1. REACH   — point the checker at real repos; it finds claims their own
#                code disproves, each with the git command + stdout that proves it.
#   2. CONTROL — install the gate as a Claude Code hook (backup + diff + confirm),
#                then a prompt in a contradicted repo is REFUSED in the terminal.
#   3. OVERRIDE— the one human moment: retype with a reason; it is allowed AND logged.
#   4. SCOPE   — the honest limit: it settles what the filesystem can settle.
#
# Everything is keyless and deterministic (git-only probes). Network is used only
# to clone the public repos in step 1/2. Run it: bash scripts/demo.sh
set -u
export PATH="$HOME/.local/bin:$PATH"
HELICON="python3 -m helicon"
DEMO="${HELICON_DEMO_DIR:-/tmp/helicon-demo}"
export HELICON_HOME="$DEMO/home"          # isolated store; nothing touches your real setup
SETTINGS="$DEMO/settings.json"            # a throwaway settings.json, never your ~/.claude one
rm -rf "$DEMO"; mkdir -p "$DEMO/home"
banner(){ printf '\n\033[1m========== %s ==========\033[0m\n' "$1"; sleep 0.4; }

banner "1) REACH — real public repos whose docs their own code disproves"
$HELICON sweep hoangtruong01/HorseTrack pvieito/CodeSignKit octocat/Hello-World \
  --jobs 3 --timeout 60

banner "2) CONTROL — install the gate as a Claude Code hook (safe: backup + diff + confirm)"
$HELICON doorway install --settings "$SETTINGS" --yes
GATE_CMD=$(python3 -c "import json;print(json.load(open('$SETTINGS'))['hooks']['UserPromptSubmit'][0]['hooks'][0]['command'])")

banner "   a contradicted repo, gated by that exact hook command"
REPO="$DEMO/HorseTrack"
git clone --depth 1 --quiet https://github.com/hoangtruong01/HorseTrack "$REPO" 2>/dev/null
NBAD=$($HELICON sweep "$REPO" --json 2>/dev/null | python3 -c 'import sys,json;print(sum(r["contradicted"] for r in json.load(sys.stdin)["results"]))' 2>/dev/null || echo 0)
if [ "${NBAD:-0}" = "0" ]; then
  # the live repo was fixed since we recorded — fall back to a representative repo so
  # the gate always fires on stage, and say so
  echo "   (live repo no longer contradicted — using a representative repo so the gate fires)"
  REPO="$DEMO/repo"; mkdir -p "$REPO"; ( cd "$REPO"; git init -q; git config user.email d@d; git config user.name d
    printf 'Read `MASTER_GUIDE.md` for the operating model.\n' > CLAUDE.md; echo x=1 > main.py
    git add -A; git commit -qm seed )
fi
echo "   > a prompt arrives in $(basename "$REPO"):"
printf '{"cwd":"%s","session_id":"demo","prompt":"ship the feature"}' "$REPO" \
  | HELICON_HOME="$DEMO/home" $GATE_CMD \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['systemMessage'])"

banner "3) OVERRIDE — the one human moment: a reason, logged against the blockers"
printf '{"cwd":"%s","session_id":"demo","prompt":"helicon-override: MASTER_GUIDE lives in the wiki, proceeding"}' "$REPO" \
  | HELICON_HOME="$DEMO/home" $GATE_CMD \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['systemMessage'])"
echo "   > the gate's own store remembers both:"
CLAUDE_SETTINGS="$SETTINGS" $HELICON doctor 2>/dev/null | grep -i "doorway" || true

banner "4) SCOPE — the honest limit (know it before the stage)"
cat <<'EOF'
   The gate settles what the FILESYSTEM can settle: a named path that is gone, a
   retired-capability kill-switch, a quoted command's output, an on-chain owner.
   A truthfulness claim ("the record doesn't support this") is a DIFFERENT
   mechanism (the contradiction judge), not this checker. Silence here is a
   verdict — it means no executable probe could bind, not that all is well.
EOF
echo
echo "demo store: $HELICON_HOME/doorway.db   (throwaway; your real setup is untouched)"
