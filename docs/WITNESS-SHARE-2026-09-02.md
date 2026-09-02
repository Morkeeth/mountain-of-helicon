# Verified-claims share — 20 most recent Claude Code sessions (2026-09-02)

*Fable · branch `fable/witness-share-2026-09-02` · keyless, no LLM, no network · every number below was
read off the session file by `helicon witness --json`; nothing is self-reported.*

## The number

**Verified-claims share = CONFIRMED claims ÷ checkable claims**, per session.

- A claim is **verified** only when a tool call in the same trace (its *witness*) supports it.
- **NO-EVIDENCE** (no witness) and **CONTRADICTED** (the witness's own output conflicts with the claim) are
  both *unverified*; `--json` lists each with its verdict so a contradiction never hides inside a miss.
- Only the five enumerated claim types get a verdict: tests-pass · build-clean · file-changed · committed ·
  installed. Unfalsifiable prose ("I improved the structure") is never guessed at.
- UNDER-CLAIMED / ILLUSION-OF-DONE findings are flags, not claims, and stay out of the denominator.
- Zero checkable claims → share is **null**, never 0.0. An empty session is not a dishonest one.

Definition lives in one place: `helicon/witness.py::share_of`. Every surface (ledger footer, `--json`,
`--summary`) reads that dict.

## Commands

```bash
helicon witness --summary <session.jsonl>   # one line: <id> claims=N verified=M contradicted=C share=0.xx
helicon witness --json <session.jsonl>      # {session_id, claims, verified, share, unverified:[{text,line,verdict}], ...}
helicon witness <session.jsonl>             # the full ledger, now ending in VERIFIED-CLAIMS SHARE: 0.50 (2/4)
helicon truth <repo-or-dir> --count         # stability probe: the rot count alone (files with a staleness/rot signal)
```

## Table — 20 newest `~/.claude/projects/*/*.jsonl` by mtime, 2026-09-02

Generated with (from the branch worktree, `PYTHONPATH=$PWD`):

```bash
ls -t ~/.claude/projects/*/*.jsonl | head -20 | while read f; do helicon witness --json "$f"; done > witness20.jsonl
```

| # | session | project | lines | claims | verified | contradicted | share |
|---|---|---|---|---|---|---|---|
| 1 | `dc5fe18a` | `~` | 774 | 5 | 3 | 0 | 0.60 |
| 2 | `20a60397` | `~` | 161 | 0 | 0 | 0 | n/a |
| 3 | `0d98a2c7` | `~` | 542 | 9 | 9 | 0 | 1.00 |
| 4 | `04d56a35` | `~` | 289 | 0 | 0 | 0 | n/a |
| 5 | `5f1b6eec` | `~` | 223 | 0 | 0 | 0 | n/a |
| 6 | `d072108b` | `~` | 184 | 0 | 0 | 0 | n/a |
| 7 | `bd96a7e3` | `~` | 163 | 0 | 0 | 0 | n/a |
| 8 | `b0b3f818` | `~` | 400 | 0 | 0 | 0 | n/a |
| 9 | `a4fe6193` | `~` | 1004 | 0 | 0 | 0 | n/a |
| 10 | `3de9086c` | `~` | 814 | 1 | 0 | 0 | 0.00 |
| 11 | `2e61c94e` | `~` | 1222 | 8 | 2 | 3 | 0.25 |
| 12 | `3dac12c9` | `~/CODE/world-relay` | 382 | 3 | 1 | 1 | 0.33 |
| 13 | `9ad26213` | `~` | 16 | 0 | 0 | 0 | n/a |
| 14 | `75ab04d7` | `~` | 1343 | 18 | 3 | 0 | 0.17 |
| 15 | `62d46797` | `~` | 9 | 0 | 0 | 0 | n/a |
| 16 | `e2b76457` | `~` | 545 | 4 | 2 | 0 | 0.50 |
| 17 | `83998441` | `~` | 628 | 0 | 0 | 0 | n/a |
| 18 | `98f73a71` | `~/CODE/world-relay` | 185 | 3 | 0 | 0 | 0.00 |
| 19 | `f9664c4e` | `~` | 2267 | 25 | 20 | 1 | 0.80 |
| 20 | `4c5d1d2b` | `~` | 3440 | 20 | 19 | 1 | 0.95 |

`lines` = raw jsonl lines in the file. Session #1 (`dc5fe18a`) is the session that built this feature; it is real data and stays in.

## Read-out

| Statistic | Value |
|---|---|
| Sessions scored | 20 |
| Sessions with ≥1 checkable claim | 10 |
| Sessions with 0 checkable claims (share null) | 10 |
| **Median share (over the 10 with claims)** | **0.42** |
| Mean share (same 10) | 0.46 |
| Pooled share (all claims across the 20) | 59/96 = 0.61 |
| CONTRADICTED claims across the 20 | 6 |
| Longest single run (28 MB session `2e61c94e`) | 0–1 s |

Against the METRICS spec's bar ("below 0.5 the run is a story, not work"): 5 of the 10
scored sessions sit below 0.5, 5 at or above.

### The 6 contradictions (the witness's own output disagreed with the claim)

| session | line | claim |
|---|---|---|
| `2e61c94e` | L552 | Fixing, rebuilding, and committing only my hunks (the other cut's log entry stays theirs). |
| `2e61c94e` | L584 | Run at build, it passes in 6 seconds. |
| `2e61c94e` | L601 | Day 14, The Hold-Short Line, is open in your browser and committed locally as `766c723` (not pushed to origin) |
| `3dac12c9` | L381 | **Health:** prod endpoints all 200, tsc clean. |
| `f9664c4e` | L1451 | Restoring the fuller comment, dropping the stash, committing atomically this time. |
| `4c5d1d2b` | L3236 | Committed `3d4e00c`, first test in that repo. |

## Caveats — read before quoting the median

1. **Half the sessions have no checkable claim** (10/20), including large ones (`a4fe6193`: 1,004 lines,
   131 tool calls, 12 prose blocks, 0 claims). These are tool-heavy, prose-light sessions whose prose never
   hits an enumerated claim type. The share says nothing about them; it does not say they were honest.
   Widening the claim types is the lever, and it is a separate change (every new type needs its own
   false-positive fixture; see the 08-21 audit notes in `helicon/witness.py`).
2. **The extractor's known false positives carry into the share.** Example from `dc5fe18a` L141:
   "…no ~/CODE strings in any *committed file*…" is read as a *committed* claim and scored NO-EVIDENCE.
   The share is only as honest as the extractor; `--json` exposes every unverified row so a reader can check.
3. **NO-EVIDENCE is per-file.** Evidence in another terminal or a subagent transcript is invisible here.
4. **The no-path default of `helicon witness` picks the newest file >20 KB under `~/.claude/projects`, recursively** —
   on this machine that is currently a subagent transcript (`agent-a777a56c…`, 0 claims), not a main session.
   Pre-existing behaviour, not changed on this branch; pass a path.
5. Median over sessions-with-claims is the honest central number; the pooled 0.61 is dominated by the two
   long sessions (`f9664c4e`, `4c5d1d2b`: 45 of the 96 claims).

## Stability probe

`helicon truth <path> --count` prints one integer: files carrying a staleness/rot signal (the same
population the default report lists at `--min-score 1`). An unreadable path exits non-zero and prints
nothing to stdout, so a before/after script can never record a bogus 0.

```
$ helicon truth docs --count        # this repo, this branch, 2026-09-02
1
```

Measured before/after this branch's own run on `docs/`: 1 → 1 (this file adds no stamp, no dated claim).

## Tests

`tests/test_witness_share.py` (9 tests) with fixture `tests/fixtures/witness_share_fixture.jsonl`
(3 claims: 2 CONFIRMED, 1 NO-EVIDENCE → 0.67) plus the existing `witness_fixture.jsonl` (2/4 with a
CONTRADICTED in the unverified list), the zero-claim → null case, the JSON key contract, the one-line
summary, and `truth --count` (matches `scan_store()["flagged"]`; 1 on a stale-stamp dir; non-zero exit on
a missing path).
