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

exec python3 -m helicon doorway gate 2>/dev/null
