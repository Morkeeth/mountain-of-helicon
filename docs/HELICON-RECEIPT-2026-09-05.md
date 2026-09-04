# HELICON-RECEIPT-2026-09-05 · env-pointer lie grade

**Repo:** Morkeeth/mountain-of-helicon · **branch:** `cursor/env-pointer-lie-grade-9d89` · **base:** `main` @ `8714be6`

**Slice:** Machine-local paths (`~/…`, host abs) leave the "setup lies about this repo" grade. Same doctrine as R14 external commands.

## Before (control went RED)

On this VM, author's `~/.helicon/config.json` is absent (`ls` exit 2). Pre-fix `helicon review .`:

```
$ helicon review .
  ✗ Your setup lies to its agent in 1 place.
    ✗ AGENTS.md:63  points at ~/.helicon/config.json  — not in this repo
  GRADE B   ·   12 references checked, 1 broken
$ echo EXIT:0   # review exits 0 on grade B today; the lie text is the defect
```

`docs/HELICON-ON-OUR-OWN-BOARD-2026-09-03.md` claimed mountain-of-helicon **A · 0 broken** after the precision fix — true only when the reviewer's HOME already had that file. Cold clone / empty HOME was never the object.

## After (slice 1 — env pointers)

```
$ EMPTY=$HOME/pytmp/empty-home-2026-09-05
$ mkdir -p "$EMPTY"
$ HOME="$EMPTY" PYTHONPATH=/workspace python3 -m helicon.review /workspace
  ✓ This setup tells its agent the truth.
    · 1 machine-local path absent on this host  — not counted as a repo lie
      AGENTS.md:63  `~/.helicon/config.json`
  GRADE A   ·   10 references checked, 0 broken
$ echo $?
0
```

(Note: `HOME=$EMPTY helicon …` cannot be used — editable install lives under `~/.local`, so empty HOME → `ModuleNotFoundError`. Object probe uses `PYTHONPATH=/workspace python3 -m helicon.review`.)

## Slice 2 — R1b same-source rule contradiction

ROADMAP Camp II plant that returned CLEAN on the 0.1.0 wheel (2026-08-14):

```
$ TMP=$(mktemp -d)
$ printf '%s\n' 'Always use v1 of the API.' 'Always use v2 of the API.' > "$TMP/CLAUDE.md"
$ PYTHONPATH=/workspace python3 -m helicon.review "$TMP"
  ✗ Your setup lies to its agent in 1 place.
    ✗ CLAUDE.md:1/2  rules conflict v1 vs v2  — L1 `always use v1` conflicts with L2 `always use v2` on subject 'api'
  GRADE D   ·   2 references checked, 1 broken
$ PYTHONPATH=/workspace python3 -m helicon.review "$TMP" >/dev/null; echo $?
1
```

Null/baseline arm (existence tier only, no R1b): same plant → 0 findings. Disagreement is the measurement.

Also fixed: CLAUDE.md with no path claims used to print "No agent instruction file found" while listing the file — now says "Found CLAUDE.md but nothing checkable yet."

**Wrong turn during slice 2:** first draft wrote R1b into `helicon/rules.py`, clobbering the prompted-triage compiler. Restored from HEAD; R1b lives in `helicon/same_source.py`. Caught by `tests/test_review2.py` ImportError before commit.

## Commands run (exit codes)

| Command | Exit |
|---------|------|
| `ls ~/.helicon/config.json` | 2 |
| `helicon review .` (before, real HOME) | 0 (GRADE B, 1 broken) |
| `HOME=$EMPTY PYTHONPATH=/workspace python3 -m helicon.review /workspace` | 0 (GRADE A, 0 broken, 1 machine_gap) |
| `TMPDIR=$HOME/pytmp python3 -m pytest -q tests/test_pointers.py tests/test_pointers_precision.py tests/test_review.py tests/test_review2.py tests/test_commands.py tests/test_rules_r1b.py` | 0 · **51 passed** |
| `HOME=$EMPTY PYTHONPATH=/workspace python3 scripts/pointer_env_baseline.py /workspace` | 0 · 4 cases, **2 DISAGREE** (expected) |
| Planted v1/v2 `python3 -m helicon.review $TMP` | **1** |
| `helicon --help` \| head (Verify · truth first) | 0 |
| `TMPDIR=$HOME/pytmp python3 -m pytest -q tests/test_launch_contract.py` | 1 · **2 failed, 6 passed** |
| `python3 scripts/launch_check.py` | 1 · **BLOCKED:** `package-metadata` — "distribution name remains a founder decision" |

## launch_contract — honest BLOCKED

The two `test_launch_contract` failures are **pre-existing on `main` @ 8714be6** (re-proven with this branch's pointer/review edits stashed; same 2 failed). Blocker key: `package-metadata`. Not introduced by this slice. Founder gate; not fixed here (DO NOT invent fleet-wide green).

## Baseline arm (naive vs env-aware)

`scripts/pointer_env_baseline.py` — naive = any missing `~/…` in backticks is a lie (two-hour grader). Env-aware = current `helicon.pointers`.

| Case | Result |
|------|--------|
| missing-host-config | **DISAGREE** — naive broken=1, env broken=0 + machine_gaps=1 |
| intra-repo-dead | agree — both convict `docs/DOES-NOT-EXIST.md` |
| clean-repo | agree — both clean |
| live:/workspace (empty HOME) | **DISAGREE** — naive 4 home hits (`~/CODE`, `~/.local/bin`, `~/.helicon/demo`, `~/.helicon/config.json`); env machine_gaps=1 (only config.json — the other three sit on lines with negation: no/not/never) |

Naive loses on precision against this product's own AGENTS.md. Env-aware does not buy silence on intra-repo dead pointers (fixture + pytest).

## What changed

- `helicon/pointers.py` — `_machine_local`, missing host paths → ungradable + `machine_gaps`; present host paths still resolve
- `helicon/review.py` — print machine gaps as dim, not lies; `--json` includes `machine_gaps`; R1b tier; honest empty-claims copy
- `helicon/same_source.py` — R1b same-file imperative use-rule conflicts
- tests — precision + cold-HOME + review output + R1b plants
- `scripts/pointer_env_baseline.py` — measurement script
- `hack.md` — tonight's contract

## WRONG / limits (mandatory)

1. **launch_contract not green** — blocked on founder `package-metadata`; pre-existing; not this slice.
2. **Negation hides some absent host paths from `machine_gaps`** (`not`/`never` on the `~/.local/bin` and `~/.helicon/demo` lines). Intentional for lie-grade; means the gap list is not a complete inventory of missing host refs.
3. **`HOME=` empty breaks the `helicon` console script** (user-site under `~/.local`). Stranger cold path for the *install* still needs a normal HOME or `python3 -m`; only the *grade* is now HOME-independent for env configs.
4. **R1b is narrow** — only `always/must/only/never use <token>` with subject binders. "Prefer X" / "don't use X" without never / multi-word objects are unmeasured. Precision over recall.
5. **Clobbered `helicon/rules.py` once** during slice 2; restored from HEAD before commit. Named in LOG so it is not forgotten.
6. **Did not re-run the author's six private repos** — not present in this VM.
