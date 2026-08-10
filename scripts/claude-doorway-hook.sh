#!/bin/sh
# Helicon doorway — the Claude Code UserPromptSubmit gate.
#
# Refuses to let a run start against a repo whose loaded docs the running code
# disproves. Reads the hook JSON on stdin, writes hook JSON on stdout.
#
# Why a wrapper and not `helicon hook userprompt` directly: the `helicon` entry
# point on PATH resolves to a console script whose package is not importable
# outside a checkout (`ModuleNotFoundError: No module named 'helicon'` from any
# other directory). A hook wired to it would have failed on every prompt, and
# because hooks fail open it would have failed SILENTLY — a gate that governs
# nothing while appearing installed. This pins the interpreter to this checkout.
#
# Fail-open is deliberate: any non-zero exit or crash here lets the prompt
# through. `gate_blocked` / `gate_override` rows in the store are what prove a
# block happened; the absence of one proves nothing.
#
# To disable: remove the UserPromptSubmit entry from ~/.claude/settings.json.

REPO="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

# No config, no gate — and say nothing rather than half-govern.
[ -f "$REPO/config.json" ] || exit 0

# stderr is not noise here, it is the one channel a block can speak on.
# `2>/dev/null` was silencing both: a crash vanished (fail-open with no trace of
# WHY, for days) and so did the block banner, so Claude Code printed the generic
# "blocked by hook: No stderr output" while the gate held a full explanation it
# had just thrown away. Kept apart now: exit 2 speaks, anything else is filed
# and forgiven.
ERR="${TMPDIR:-/tmp}/helicon-doorway.$$.err"
LAST="${TMPDIR:-/tmp}/helicon-doorway.last.err"

# PYTHONSAFEPATH stops `python3 -m` from prepending the CALLER's cwd to
# sys.path ahead of PYTHONPATH. Without it, a prompt sent from inside the old
# ~/CODE/helicon checkout imported THAT package — which has no `hook` command —
# so argparse exited 2 and the block branch below fired on every prompt.
PYTHONSAFEPATH=1 \
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
HELICON_CONFIG="$REPO/config.json" \
python3 -m helicon hook userprompt 2>"$ERR"
rc=$?

# argparse's usage-error exit code is 2 — the SAME code that means "block".
# A CLI that cannot even parse its arguments has governed nothing, so its 2 is
# a crash to be filed and forgiven, not a verdict to stop the operator with.
if [ "$rc" -eq 2 ] && head -n 1 "$ERR" | grep -q '^usage:'; then
    rc=1
fi

if [ "$rc" -eq 2 ]; then
    cat "$ERR" >&2                     # the banner the operator is stopped by
else
    [ -s "$ERR" ] && cp "$ERR" "$LAST" # a crash is diagnosable, not deleted
    rc=0                               # fail open, explicitly
fi
rm -f "$ERR"
exit "$rc"
