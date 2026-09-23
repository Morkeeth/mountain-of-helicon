# Pre-registration amendment 1, 22 Sep 2026

Committed before the grid2 run. `PREREG.md` stays as committed in `bb9a923`.

## What went wrong

The runs tagged `smoke` (3 runs) and `grid` (27 runs) are invalid as a test of the stock agent.

- Cause: the run root was `~/.local/state/day-run/2026-09-22/helicon-adversarial-eval/runs`, which is under `$HOME`. Claude Code walks up the parent directories for project memory. At `$HOME` it found `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` and loaded them, even with `--setting-sources project`.
- What leaked: Oscar's global CLAUDE.md, `EVIDENCE.md`, `OUTWARD.md` and `SESSION.md`. `EVIDENCE.md` says "Probe the object, not the document about the object." That is a direct instruction to distrust a CLAUDE.md.
- How it was found: after the grid, run `grid/c1_renamed_function/original/r3` wrote "Per EVIDENCE.md I checked the actual source". A probe at that run root then listed the four leaked files.
- Why the pre-run check missed it: harness probe 1 in `PREREG.md` ran in the session scratchpad under `/private/tmp`, where no ancestor has a `.claude` directory. It was correct about the wrong object. The parent check looked for `CLAUDE.md` and `AGENTS.md`, not for `.claude/CLAUDE.md`.

## Change

- Run root moves to `/private/tmp/helicon-adversarial-eval-2026-09-22` through the existing `EVAL_OUT` variable. No fixture, grader, runner, flag or prediction changes. `FIXTURES.sha256` still holds.
- Isolation probe at the new root, with the c1 original CLAUDE.md and `git init`, same flags as the grid: the child listed only the fixture CLAUDE.md and answered NO for EVIDENCE.md, Oscar, em dashes and "verify before asserting". Saved as `probe-isolation/probe.json` under the run root. Cost $0.0292.
- Grader selfcheck rerun at the new root: `SELFCHECK OK`.
- New tag: `grid2`, n = 3, 27 runs. Predictions H1, H2, B and the stop rules are unchanged. The smoke is not repeated; the probe covers the harness.

## Spend to date

$2.7874 list: probes $0.0547, invalid smoke $0.2681, invalid grid $2.3578, leak probes $0.0776, isolation probe $0.0292. The $15.00 cap includes all of it. grid2 runs with `--spent 2.7874`.

## What the invalid grid still shows

With Oscar's rules loaded, 27 of 27 passed and stale_followed was 0 of 9. That is a result about Oscar's own setup, not about a stock agent.
