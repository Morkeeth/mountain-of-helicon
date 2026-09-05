# HELICON-RECEIPT-2026-09-05-day · land env-pointer onto today's main

**Repo:** Morkeeth/mountain-of-helicon · **branch:** `cursor/env-pointer-land-cb81` · **base:** `main` @ `8714be6`

**Source overnight:** `origin/cursor/env-pointer-lie-grade-9d89` (4 commits, merge-base identical to today's main — cherry-pick clean, 0 conflicts).

**Day job:** Re-prove the overnight env-pointer lie-grade + R1b on a fresh branch from current `main`, then three small truth slices, with before/after grades from commands run **today**.

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

## After land (env-pointer + R1b cherry-pick)

```
$ git log --oneline origin/main..HEAD   # after cherry-pick, before day slices
$ HOME="$EMPTY" PYTHONPATH=/workspace python3 -m helicon.review /workspace
  ✓ This setup tells its agent the truth.
    · 1 machine-local path absent on this host  — not counted as a repo lie
      AGENTS.md:63  `~/.helicon/config.json`
  GRADE A   ·   10 references checked, 0 broken
$ echo $?
0
```

## Slice 2 — R1b don't / do not

Overnight R1b only matched `always|must|only|never`. Softer negation graded as truth:

```
# BEFORE
$ printf '%s\n' "Don't use yarn for installs." "Always use yarn for installs." > "$TMP/CLAUDE.md"
$ PYTHONPATH=/workspace python3 -m helicon.review "$TMP"
  ✓ This setup tells its agent the truth.
  GRADE A   ·   1 reference checked, 0 broken
$ echo $?
0
```

```
# AFTER
$ PYTHONPATH=/workspace python3 -m helicon.review "$TMP"
  ✗ … L1 `never use yarn` conflicts with L2 `always use yarn` on subject 'installs'
  GRADE D   ·   2 references checked, 1 broken
$ echo $?
1
```

Prefer npm/yarn stays GRADE – exit 0 (deferred open question).

## Slice 2b — bare never↔always (no subject)

```
# BEFORE
$ printf '%s\n' 'Never use yarn.' 'Always use yarn.' > "$TMP/CLAUDE.md"
$ PYTHONPATH=/workspace python3 -m helicon.review "$TMP"
  GRADE A · exit 0
# Root cause: empty-subject arm required _same_family with a!=b
```

```
# AFTER
$ PYTHONPATH=/workspace python3 -m helicon.review "$TMP"
  GRADE D · exit 1 · never-vs-always yarn vs yarn
```

## Slice 3 — R14 npm lifecycle + clause negation + cd-web

```
# BEFORE: `npm test` invisible → GRADE – exit 0
# BEFORE: 'missing web/dist; run `npm run build`' → silent UNMEASURED exit 0
# AFTER: both GRADE F exit 1
```

Own-board embarrassment then fix:

```
# After checker fix, before AGENTS.md edit:
$ HOME=$EMPTY … helicon.review /workspace
  ✗ AGENTS.md:73  runs no 'dev' in package.json scripts
  GRADE B · exit 1

# After AGENTS.md:73 → `cd web && npm run dev` + R14 resolves web/package.json:
$ HOME=$EMPTY … helicon.review /workspace
  GRADE A · 12 references checked, 0 broken · exit 0
```

## Commands run today (re-derived)

| Command | Exit | Object result |
|---------|------|---------------|
| `ls ~/.helicon/config.json` | 2 | absent |
| empty-HOME review on bare `main` | **1** | **GRADE B**, 11 checked, 1 broken |
| empty-HOME review after land | **0** | **GRADE A**, 10 checked, 0 broken, 1 machine_gap |
| empty-HOME review after Slice 3 + AGENTS fix | **0** | **GRADE A**, **12** checked, 0 broken |
| Don't yarn plant after Slice 2 | **1** | GRADE D |
| Bare Never/Always yarn after 2b | **1** | GRADE D |
| `npm test` / negation plants after Slice 3 | **1** | GRADE F |
| `pointer_env_baseline.py` | 0 | 4 cases, **2 DISAGREE** |
| `TMPDIR=$HOME/pytmp python3 -m pytest -q` (pointers/review/commands/r1b) | 0 | **62 passed** |

## What landed (commits on this branch)

Cherry-picks: `b172b83` `2162ee0` `92761e4` `0411d2d` ← overnight env-pointer + R1b + receipts.

Day: day receipt · don't-use · bare never/always · R14 npm/clause/cd-web + AGENTS.md:73.

## WRONG / limits (mandatory)

1. **Overnight receipt said GRADE B exited 0; today's bare-main run exited 1.** Object today is exit 1.
2. **Checked-count drift** across runs (11 → 10 → 12) — day claims use today's numbers only.
3. **Full pytest suite not the Slice done-when** — targeted 62 passed. launch_contract / anyio left unclaimed.
4. **`HOME=` empty cannot use `helicon` console script** — probe uses `python3 -m helicon.review`.
5. **README ≤400 Oscar-gated** — not started (not this Slice 3).
6. **No merge to main** — PR-ready only.
7. **`prefer` still unmeasured.**
8. **Don't normalizes to `never` in receipt text.**
9. **`cd DIR && npm run` requires that exact backtick shape.**
10. **Clause-scoped negation is commands-only** — pointers still line-global.
