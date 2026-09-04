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

## After

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

## Commands run (exit codes)

| Command | Exit |
|---------|------|
| `ls ~/.helicon/config.json` | 2 |
| `helicon review .` (before, real HOME) | 0 (GRADE B, 1 broken) |
| `HOME=$EMPTY PYTHONPATH=/workspace python3 -m helicon.review /workspace` | 0 (GRADE A, 0 broken, 1 machine_gap) |
| `TMPDIR=$HOME/pytmp python3 -m pytest -q tests/test_pointers.py tests/test_pointers_precision.py tests/test_review.py tests/test_review2.py tests/test_commands.py` | 0 · **44 passed** |
| `HOME=$EMPTY PYTHONPATH=/workspace python3 scripts/pointer_env_baseline.py /workspace` | 0 · 4 cases, **2 DISAGREE** (expected) |
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
- `helicon/review.py` — print machine gaps as dim, not lies; `--json` includes `machine_gaps`
- tests — precision + cold-HOME control + review output
- `scripts/pointer_env_baseline.py` — measurement script
- `hack.md` — tonight's contract

## WRONG / limits (mandatory)

1. **launch_contract not green** — blocked on founder `package-metadata`; pre-existing; not this slice.
2. **Negation hides some absent host paths from `machine_gaps`** (`not`/`never` on the `~/.local/bin` and `~/.helicon/demo` lines). Intentional for lie-grade; means the gap list is not a complete inventory of missing host refs.
3. **`HOME=` empty breaks the `helicon` console script** (user-site under `~/.local`). Stranger cold path for the *install* still needs a normal HOME or `python3 -m`; only the *grade* is now HOME-independent for env configs.
4. **Did not ship R1b** (same-source contradiction) in the first commit of this receipt — may follow on the same branch if headroom remains.
5. **Did not re-run the author's six private repos** — not present in this VM.
