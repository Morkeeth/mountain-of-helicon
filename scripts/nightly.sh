#!/bin/bash
# The Mount Helicon nightly: reconcile, triage, consolidate, compile the law,
# score. Scheduled by launchd (com.morkeeth.helicon-nightly), NOT cron.
#
# cron drops a job the Mac slept through and never mentions it. That is exactly
# how the Jul 15 consolidation skipped in silence, and why the stack ran all day
# on a law compiled 31 hours earlier. launchd's StartCalendarInterval runs a
# missed job when the machine wakes.
#
# The && chain is load-bearing: data/eval-latest.json is written ONLY if every
# step before it succeeded, which is what makes its mtime an honest liveness
# probe rather than a proxy. stackwatch.nightly_status() reads exactly that, and
# `helicon doctor` prints its age every time you look.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
LOG=data/nightly.log
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

echo "=== nightly start $(date -Iseconds) ===" >> "$LOG"

# Each step logs. The old crontab line redirected only `evolve`, so a failure in
# reconcile or triage went to cron's stdout and nowhere a human would ever read.
# `runs --close --run` cuts and persists the card for the day's run: it refreshes
# the review --terminals verdicts, then scores verified yield / cost - damage. It
# was built (slice 1.8) and wired to nothing, so the run history only grew when
# Oscar remembered to run it by hand — 2 cards in two weeks. On the chain it
# compounds without anyone deciding to.
#
# --run is the whole point. Without it, every test claim an agent makes ("36
# tests green") is filed UNVERIFIED and excluded from the ratio, so the one
# number the thesis rests on — do agent claims survive contact with reality —
# would be measured by not checking. The runner is bounded (150s per repo, and
# only a recognised pytest/npm runner that is already installed), which is a
# trade worth making at 02:47 on an idle machine.
#
# Chained with && like every other step: a step that fails quietly is the exact
# bug this nightly exists to stop being.
$PY -m helicon.cli reconcile --apply >> "$LOG" 2>&1 &&
  $PY -m helicon.cli triage          >> "$LOG" 2>&1 &&
  $PY -m helicon.cli evolve          >> "$LOG" 2>&1 &&
  $PY -m helicon.cli runs --close --run >> "$LOG" 2>&1 &&
  $PY -m helicon.cli policy --inject >> "$LOG" 2>&1 &&
  $PY -m helicon.cli report --llm --json > data/eval-latest.json 2>> "$LOG"
rc=$?

# The run record: written by this script and by nothing else, carrying its own
# UTC timestamp and the real exit code. stackwatch.nightly_status() reads THIS
# rather than a file mtime, because an mtime is a claim the filesystem makes and
# anything can make it — a manual `report > eval-latest.json`, a git checkout, an
# editor save would all have forged 30 hours of fake health. Written on failure
# too: a run that failed is a fact worth keeping, not an absence.
printf '{"ts":"%s","rc":%d,"host":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%S)" "$rc" "$(hostname -s)" > data/nightly-run.json

echo "=== nightly exit $rc $(date -Iseconds) ===" >> "$LOG"
exit $rc
