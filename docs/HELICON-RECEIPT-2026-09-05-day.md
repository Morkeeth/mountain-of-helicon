# HELICON-RECEIPT-2026-09-05-day · land env-pointer onto today's main

**Repo:** Morkeeth/mountain-of-helicon · **branch:** `cursor/env-pointer-land-cb81` · **base:** `main` @ `8714be6`

**Source overnight:** `origin/cursor/env-pointer-lie-grade-9d89` (4 commits, merge-base identical to today's main — cherry-pick clean, 0 conflicts).

**Day job:** Re-prove the overnight env-pointer lie-grade + R1b on a fresh branch from current `main`, with before/after grades from commands run **today** (not carried from the overnight receipt).

## Before (control went RED — bare `main` @ `8714be6`)

Author's `~/.helicon/config.json` absent on this VM (`ls` exit 2). Empty HOME forced so the grade cannot leak a present host file:

```
$ git rev-parse HEAD
8714be648beda7c707d045af824359e59b8a0779
$ EMPTY=$HOME/pytmp/empty-home-2026-09-05-day
$ mkdir -p "$EMPTY"
$ HOME="$EMPTY" PYTHONPATH=/workspace python3 -m helicon.review /workspace
  ✗ Your setup lies to its agent in 1 place.
    ✗ AGENTS.md:63  points at ~/.helicon/config.json  — not in this repo
  GRADE B   ·   11 references checked, 1 broken
$ echo $?
1
```

(Note: real HOME on this VM also lacks `~/.helicon/`, so bare-main review is GRADE B either way. Empty HOME is still the control object — same doctrine as overnight.)

## After (land branch — empty HOME)

```
$ git checkout cursor/env-pointer-land-cb81
$ git log --oneline origin/main..HEAD
0411d2d docs(receipt): note anyio env limits and stop after slice 2
92761e4 docs(receipt): record full-suite counts and anyio env failures
2162ee0 feat(review): R1b same-source use-rule conflicts in one file
b172b83 fix(pointers): missing ~/ paths are machine gaps, not repo lies
$ HOME="$EMPTY" PYTHONPATH=/workspace python3 -m helicon.review /workspace
  ✓ This setup tells its agent the truth.
    · 1 machine-local path absent on this host  — not counted as a repo lie
      AGENTS.md:63  `~/.helicon/config.json`
  GRADE A   ·   10 references checked, 0 broken
$ echo $?
0
```

## R1b still fires (planted same-file conflict)

```
$ TMP=$(mktemp -d)
$ printf '%s\n' 'Always use v1 of the API.' 'Always use v2 of the API.' > "$TMP/CLAUDE.md"
$ HOME="$EMPTY" PYTHONPATH=/workspace python3 -m helicon.review "$TMP"
  ✗ Your setup lies to its agent in 1 place.
    ✗ CLAUDE.md:1/2  rules conflict v1 vs v2  — …
  GRADE D   ·   2 references checked, 1 broken
$ echo $?
1
```

## Commands run today (exit codes) — re-derived, not carried

| Command | Exit | Object result |
|---------|------|---------------|
| `ls ~/.helicon/config.json` | 2 | absent |
| `HOME=$EMPTY … python3 -m helicon.review /workspace` on bare `main` | **1** | **GRADE B**, 11 checked, 1 broken |
| same on `cursor/env-pointer-land-cb81` | **0** | **GRADE A**, 10 checked, 0 broken, 1 machine_gap |
| planted v1/v2 `… helicon.review $TMP` | **1** | **GRADE D**, 1 broken |
| `HOME=$EMPTY … python3 scripts/pointer_env_baseline.py /workspace` | 0 | 4 cases, **2 DISAGREE** |
| `TMPDIR=$HOME/pytmp python3 -m pytest -q tests/test_pointers.py tests/test_pointers_precision.py tests/test_review.py tests/test_review2.py tests/test_commands.py tests/test_rules_r1b.py` | 0 | **51 passed** |

## Baseline arm (naive vs env-aware) — today

Same script as overnight. Re-run on land branch:

| Case | Result |
|------|--------|
| missing-host-config | **DISAGREE** — naive broken=1, env broken=0 + machine_gaps=1 |
| intra-repo-dead | agree — both convict |
| clean-repo | agree |
| live:/workspace (empty HOME) | **DISAGREE** — naive 4 home hits; env machine_gaps=1 |

## What landed (cherry-pick SHAs on this branch)

- `b172b83` ← `4cd9079` fix(pointers): missing ~/ paths are machine gaps, not repo lies
- `2162ee0` ← `160ab07` feat(review): R1b same-source use-rule conflicts
- `92761e4` ← `e72c1c2` docs(receipt): full-suite counts
- `0411d2d` ← `ed4cb5f` docs(receipt): anyio env limits

Plus this day receipt + day `hack.md` contract (separate commit).

## WRONG / limits (mandatory — day)

1. **Overnight receipt said GRADE B exited 0 on main; today's bare-main run exited 1.** Carrying that exit code would have been a lie. Re-derived: exit **1** on GRADE B at `8714be6`. Possible causes: review exit policy already treated B as fail on this tip, or overnight mis-logged; object today is exit 1.
2. **Checked-count drift:** bare main empty-HOME = **11** checked; overnight receipt said **12**; land after = **10**. Do not reconcile by reading — these are three different runs/objects. Day claims use today's numbers only.
3. **Did not re-run full pytest suite today for the land claim** — targeted 51 passed is the Slice-1 done-when. Full-suite anyio/launch_contract status left to overnight receipt + optional later probe.
4. **`HOME=` empty still cannot use the `helicon` console script** (user-site under `~/.local`) — probe uses `PYTHONPATH=/workspace python3 -m helicon.review`.
5. **Slice 3 README ≤400 not started** — Oscar gate per day brief.
6. **No merge to main** — PR-ready only.
