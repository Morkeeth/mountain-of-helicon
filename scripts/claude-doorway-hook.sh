#!/bin/sh
# Helicon doorway gate — portable Claude Code UserPromptSubmit wrapper.
#
# Refuses to let a run start against a repo whose loaded docs the running code
# disproves. Reads the hook JSON on stdin, writes a block decision on stdout.
#
# Config-free and checkout-free: the gate is deterministic (git-only probes) and
# keeps its own log under ${HELICON_HOME:-~/.helicon}. It does NOT read a
# config.json, so it runs for anyone who has `pip install`ed helicon — the
# earlier version of this wrapper pinned the interpreter to a checkout because a
# bare `helicon` on PATH raised ModuleNotFoundError from other directories; the
# packaging fix (running `python3 -m helicon`) removes that need.
#
# Fail-open is deliberate: any non-zero exit or crash here lets the prompt
# through. `gate_blocked` / `gate_override` rows in the store are what prove a
# block happened; the absence of one proves nothing.
#
# PREFER `helicon doorway install`, which wires the exact interpreter that has
# helicon importable and needs no wrapper on PATH. This script exists for manual
# installs and non-Claude harnesses. To disable: remove the UserPromptSubmit
# entry from ~/.claude/settings.json (or run `helicon doorway install --uninstall`).

# Both halves of this merge were right about different things.
#
# The stranger lane is right that the gate must be config-free and must not
# resolve a checkout root: `doorway gate` replaces `hook userprompt`, and the
# config.json existence check is gone, because requiring one is exactly what
# made this wrapper unrunnable for anyone but the author.
#
# But it wrote `exec … 2>/dev/null`, and that discards the block banner. That
# was a bug here for days: stderr is the ONE channel a block can speak on, so
# silencing it made Claude Code print the generic "blocked by hook: No stderr
# output" while the gate held a full explanation it had just thrown away — and
# made crashes vanish with no trace of WHY. Keeping the two apart is the whole
# fix: exit 2 speaks, anything else is filed and forgiven.
#
# So: lane 2's entrypoint, this branch's stderr discipline. `exec` is dropped
# because the redirect has to be inspected after the run, not replaced by it.
ERR="${TMPDIR:-/tmp}/helicon-doorway.$$.err"
LAST="${TMPDIR:-/tmp}/helicon-doorway.last.err"

python3 -m helicon doorway gate 2>"$ERR"
rc=$?

if [ "$rc" -eq 2 ]; then
    cat "$ERR" >&2                     # the banner the operator is stopped by
else
    [ -s "$ERR" ] && cp "$ERR" "$LAST" # a crash is diagnosable, not deleted
    rc=0                               # fail open, explicitly
fi
rm -f "$ERR"
exit "$rc"
