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

PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
HELICON_CONFIG="$REPO/config.json" \
exec python3 -m helicon hook userprompt 2>/dev/null
