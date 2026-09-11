# hack.md — astra-helicon-ambitious-2026-09-11

## NORTH STAR

Prove, from this checkout of `main` alone, that a fresh agent after correction still walks **finding → decision (ZUP-bound / future handoff) → returned-result**, and that ruling/undo either still breaks or is cleared — with commands, not narrative.

## PROMISE LINE

**GET:** A dated cloud receipt (`docs/CLOUD-RECEIPT-helicon-handoff-2026-09-11.md`) that a stranger can re-run: path map with file:line, executed correction→decision→result commands + outcomes, and ruling/undo reproduced-or-cleared with expected vs actual.

**CONSTRAINT:** Work on `main` (or short-lived `cursor/astra-helicon-2026-09-11-ee72` if main push blocked). No deploy, no publish, no broad ZUP refresh, no private-corpus merge. A box is truth only when its done-when was RUN.

## OPEN QUESTIONS

- **BLOCKING:** none for this wave's done-when.
- **NON-BLOCKING (Oscar):** live ZUP-inbox probe; whether `/api/queue/undo` should refuse `ok` on `restored:0`; anyio DeprecationWarning breaking `test_govern_api_boundary` collection on this VM.

## CONSTITUTION

1. Run it, do not read it — every checkbox names the command that proved it.
2. Re-derive every number at its object; never carry figures from this prompt or prior docs.
3. Never rank by title/name — open the object (API response, DB row, sandbox file).
4. Do not invent "fixed" without command evidence; reproduce OR explicitly clear.
5. Outward acts are Oscar's click — no post/publish/submit; push is branch push only.
6. Report SHIPPED / VERIFIED / WRONG; WRONG is mandatory.

## PLAN

1. **Slice 1:** Orient + execute the handoff path + ruling/undo probe. *Done — E4/E5 reproduced red.*
2. **Slice 2:** Minimal fix for E4/E5 + UI checks + pytest pins. *Done — re-probe 14/14.*
3. Slice 3: live ZUP-inbox cross-check on Oscar's machine. Oscar gate.

## NOW

**Done-when met.** Receipt written; probe green after Slice 2. Remaining work is Oscar's rulings (see receipt § What Oscar must rule).

**Done when:**
- [x] `docs/CLOUD-RECEIPT-helicon-handoff-2026-09-11.md` exists — command: `test -f docs/CLOUD-RECEIPT-helicon-handoff-2026-09-11.md`
- [x] Receipt includes correction→decision→returned-result commands with outcomes — command: `python3 scripts/probe_handoff_2026_09_11.py` → 14 pass / 0 fail
- [x] Ruling/undo reproduced then cleared — commands: first probe E4/E5 red; after fix `TMPDIR="$HOME/pytmp" python3 -m pytest -q tests/test_govern_batch.py::test_confirm_kill_undo_restores_cube tests/test_govern_batch.py::test_undo_recovers_from_empty_decided_ids_via_receipt` → 2 passed

## LOG

- 2026-09-11: Pulled `origin/main` @ `8714be6` (Already up to date). Prior `hack.md` was HELICON-S2 help-groups — rewritten for this wave before any probe code.
- 2026-09-11: Prior receipt `CLOUD-RECEIPT-helicon-handoff-2026-09-05.md` confirmed MISSING on disk (`find` / `Glob` → 0).
- 2026-09-11: Slice 1 probe reproduced E4 (confirm-kill survives undo) and E5 (vacuous fully_reversed + FocusReview ignore).
- 2026-09-11: Slice 2 fixed `helicon/api/govern.py` kill-restore + receipt_json fallback; FocusReview requires `fully_reversed`; App.tsx refuses `restored:0`. Re-probe 14/14. Pytest pins 4/4 on undo totality.
- 2026-09-11: Baseline arm: naive human_decision-only leaves guard clean; govern rule_truth blocks — govern beats naive.
