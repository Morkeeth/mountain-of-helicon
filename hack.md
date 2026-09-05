# hack.md — DAY 2026-09-05 · land env-pointer + next truth slice

## NORTH STAR

A cold clone / empty-HOME review of this product must not convict `AGENTS.md` for a missing host config that lives outside the repo — and that fix must live on a fresh branch from today's `main`, re-proven at the object.

## PROMISE LINE

**GET:** Overnight `cursor/env-pointer-lie-grade-9d89` (env-local missing pointers → `machine_gaps`, not lies; R1b same-source conflicts) replayed onto a new day branch from current `main`, with a day receipt that shows before/after review grades from commands run today.

**CONSTRAINT:** No merge to `main` without Oscar. No PyPI publish. No private flip. No force-push. Outward acts are Oscar's click (draft PR only). Slice 3 README ≤400 stays Oscar-gated unless trivial.

## OPEN QUESTIONS

- **BLOCKING:** none — overnight commits cherry-picked clean onto `main` @ `8714be6`.
- **NON-BLOCKING:** What is the smallest next truth slice after land+reprove that is not the Oscar-gated README rewrite? Decide only after Slice 1 green.
- **NON-BLOCKING:** Full-suite anyio/launch_contract reds — re-derive if probing; do not invent fleet-wide green.

## CONSTITUTION

1. Run it, do not read it — every checkbox names the command that proved it.
2. Re-derive numbers at the object; never carry figures from the overnight receipt or this prompt.
3. A control that has not been watched going RED is not a control — empty-HOME review must fail on bare `main` before the land and pass after.
4. Never rank by title; open the object (clean HOME, this checkout, planted fixtures).
5. Do not tick a box whose done-when was not executed.
6. Report SHIPPED / VERIFIED / WRONG; WRONG is mandatory.

## PLAN

1. **Slice 1 (land / riskiest):** Cherry-pick overnight onto `cursor/env-pointer-land-cb81`; empty-HOME RED→GREEN; day receipt. *Risk: clean cherry-pick without object re-proof.*
2. Slice 2: One small next truth slice — only if Slice 1 green. Not README ≤400 (Oscar gate).
3. Slice 3: README ≤400 / PyPI lead — Oscar gate, skip unless trivial.

## NOW

**Slice 1 done — moving to Slice 2 selection after commit.** Land verified; day receipt written.

**Done when (Slice 1):**
- [x] Branch from today's main contains overnight commits — `git log --oneline origin/main..HEAD` → 4 cherry-picks (`b172b83`…`0411d2d`)
- [x] Empty-HOME review on bare main goes RED — `HOME=$EMPTY PYTHONPATH=/workspace python3 -m helicon.review /workspace` → exit **1**, GRADE B, 11 checked, 1 broken
- [x] Empty-HOME review on land branch goes GREEN — same command → exit **0**, GRADE A, 10 checked, 0 broken, 1 machine_gap
- [x] `docs/HELICON-RECEIPT-2026-09-05-day.md` exists with before/after from today's runs
- [x] Targeted pytest — `TMPDIR=$HOME/pytmp python3 -m pytest -q tests/test_pointers.py tests/test_pointers_precision.py tests/test_review.py tests/test_review2.py tests/test_commands.py tests/test_rules_r1b.py` → **51 passed**

## LOG

- 2026-09-05: Read contract — previous `hack.md` was HELICON-S2 help groups (stale). Overnight branch exists: 4 commits on `cursor/env-pointer-lie-grade-9d89`, merge-base = `main` @ `8714be6`, 0 behind / 4 ahead. Wrote day contract before any land code.
- 2026-09-05: Fetched `origin/main` + `origin/cursor/env-pointer-lie-grade-9d89`. Local main matches remote @ `8714be6`.
- 2026-09-05: **Control RED on bare main** — empty HOME review exit 1, GRADE B, AGENTS.md:63 `~/.helicon/config.json` broken. (Overnight receipt claimed exit 0 for GRADE B — **wrong to carry**; today exit 1.)
- 2026-09-05: Branch `cursor/env-pointer-land-cb81`; cherry-pick `4cd9079 160ab07 e72c1c2 ed4cb5f` → `b172b83 2162ee0 92761e4 0411d2d`, 0 conflicts.
- 2026-09-05: **Control GREEN after land** — exit 0, GRADE A, 1 machine_gap. R1b plant exit 1 GRADE D. Baseline 2 DISAGREE. Pytest 51 passed. Day receipt written.
