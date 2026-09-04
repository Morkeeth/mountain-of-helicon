# hack.md — OVERNIGHT 2026-09-05 · env-pointer lie grade

## NORTH STAR

A cold clone of this repo must not be graded as lying because the reviewer's machine lacks Oscar's `~/.helicon/config.json`.

## PROMISE LINE

**GET:** Machine-local paths (`~/…`, absolute outside the tree) leave the "setup lies about this repo" grade — same doctrine as external commands (R14): absence outside the repo proves nothing about the repo.

**CONSTRAINT:** Intra-repo dead pointers still fire. No PyPI publish. Outward acts are Oscar's click (no public post/submit; draft PR is delivery only).

## OPEN QUESTIONS

- **BLOCKING:** none — doctrine already shipped for commands (`test_external_commands_are_unmeasured_not_false_alarms`); pointers lagged.
- **NON-BLOCKING:** Should present `~/…` paths stay in the checked denominator (today: yes, as resolved) or also leave it? Keeping them in for now so a resolved home path still counts as evidence the extractor saw it.
- **NON-BLOCKING:** R1b same-source contradiction (ROADMAP) — next slice, not tonight's NOW unless Slice 1 finishes early with headroom.

## CONSTITUTION

1. Run it, do not read it — every checkbox names the command that proved it.
2. Re-derive numbers at the object; never carry figures from this prompt or prior receipts.
3. A control that has not been watched going RED is not a control — the cold-HOME self-review must fail on main before the fix and pass after.
4. Never rank by title; open the object (clean HOME, this checkout, public fixtures).
5. Baseline arm required: naive "missing ~/ = broken" vs env-aware; if naive wins anywhere that matters, that is the finding.
6. Report SHIPPED / VERIFIED / WRONG; WRONG is mandatory.

## PLAN

1. **Slice 1 (NOW / riskiest):** Env-local missing pointers are not repo-lies. Extract skips them from broken/checked (like ungradable slash-commands), optionally surfaces `machine_gaps` for honesty. Cold-HOME control + baseline eval + precision/pointer tests + `docs/HELICON-RECEIPT-2026-09-05.md`. *Risk: buying precision by silencing real agent dead-ends that name `~/CODE/...` — baseline arm must keep a fixture where the naive grader "catches" a missing home path and we state we intentionally exclude it from the lie grade.*
2. Slice 2: R1b same-source contradiction detector (ROADMAP Camp II) — only if Slice 1 is green with headroom.
3. Slice 3: README ≤400 / PyPI lead (SUBTRACTION-MEMO) — Oscar gate, deferred.

## NOW

**Slice 2:** R1b same-source rule contradiction in `helicon review` — plant "always use v1" / "always use v2" in one CLAUDE.md and get a finding (today: silent + false "no instruction file" when the file has no path claims).

**Done when:**
- [x] Planted same-file v1/v2 conflict → review reports broken — `python3 -m helicon.review $TMP` exit **1**, GRADE D
- [x] Null/baseline arm silent on same plant — `find_conflicts` vs `[]` in `test_null_baseline_arm_is_silent_on_plant`
- [x] Clean single-rule file stays clean — `test_single_always_use_is_clean`
- [x] False "No agent instruction file" fixed — empty-claims fixture prints "Found CLAUDE.md but nothing checkable yet."
- [x] pytest green — 51 passed (pointers/review/commands/r1b/review2)
- [x] Slice 1 cold-HOME still GRADE A — re-run exit 0
- [x] Receipt updated

## LOG

- 2026-09-04: Read contract `hack.md` (was S2 help-groups, done). `git log -5` on main → first-screen + witness-share. Ran `helicon review .` → GRADE B, sole finding `AGENTS.md:63 ~/.helicon/config.json` — file absent on this VM (`ls` exit 2). Own-board doc claimed A only because author's HOME had the file. Commands already exclude external providers; pointers did not. Slice 1 chosen.
- 2026-09-04: Branch `cursor/env-pointer-lie-grade-9d89` from `origin/main` @ 8714be6.
- 2026-09-04: Slice 1 implemented. Cold HOME control: GRADE B→A. Pytest pointers/review/commands **44 passed**. Baseline 2 DISAGREE. `launch_check` **BLOCKED** pre-existing `package-metadata` (exit 1). Receipt: `docs/HELICON-RECEIPT-2026-09-05.md`.
- 2026-09-04: Done-when checks — cold HOME review run (`HOME=… PYTHONPATH=… python3 -m helicon.review`); intra-repo dead still fires (pytest); baseline printed; `--help` Verify/truth first.
- 2026-09-04: Slice 1 committed `4cd9079` + pushed. Reproduced ROADMAP R1b gap: planted Always use v1/v2 CLAUDE.md → review says "No agent instruction file found" (checked=0) while `instruction_files=['CLAUDE.md']`. Slice 2 NOW.
- 2026-09-04: **WRONG:** briefly overwrote `helicon/rules.py` (triage compiler); restored from HEAD; R1b in `helicon/same_source.py`. Caught by test_review2 ImportError.
- 2026-09-04: Slice 2 green — planted exit 1; 51 pytest passed; cold HOME still A.
