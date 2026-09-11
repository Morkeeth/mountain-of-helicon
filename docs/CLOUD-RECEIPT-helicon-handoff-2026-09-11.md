# CLOUD-RECEIPT — helicon handoff · 2026-09-11

**Run:** `astra-helicon-ambitious-2026-09-11`  
**Repo:** `Morkeeth/mountain-of-helicon`  
**Base at start:** `main` @ `8714be6`  
**Branch:** `cursor/astra-helicon-2026-09-11-ee72`  
**Ambition restated:** Prove a fresh agent after correction still reaches **finding → ZUP-bound decision → returned-result**; reproduce or clear ruling/undo inconsistencies against current code — commands only, no deploy.

Prior done-when receipt `CLOUD-RECEIPT-helicon-handoff-2026-09-05.md` was **MISSING** on disk at wave start (`Glob` / `find` → 0). This file is that wave's dated replacement.

---

## Path map (opened at the object)

Helicon = PAST; ZUP = FUTURE (`docs/HARNESS.md:40–44`). The in-repo FUTURE egress is Focus route, not a ZUP binary in this checkout.

| Step | What | File:line |
|------|------|-----------|
| Finding (decision lane) | `GET /api/findings?lane=decision` | `helicon/api/findings.py:371` `list_findings` |
| Decision (human ruling) | `POST /api/govern/apply-batch` → `_rule_truth` / `_confirm` | `helicon/api/govern.py:219` `apply_batch`; `:48` `_rule_truth`; `:94` `_confirm` |
| Returned-result | Receipt `verify.guard_blocks_the_wrong_claim` + independent `guard_output` | `helicon/api/govern.py` `_build_receipt` (called from `apply_batch`) |
| ZUP-bound handoff | `POST /api/focus/route` → paste-ready prompt or vault/local next-moves file | `helicon/api/focus.py:97` `focus_route` |
| Correction (output-review) | Cockpit `rule` → `propagate` → next-agent files | `helicon/cockpit.py:320` `rule_claim`; `:414` `propagate_correction`; API `helicon/api/cockpit.py:51,68` |
| Undo (govern) | `POST /api/govern/undo-batch` | `helicon/api/govern.py:255` |
| Undo (cockpit) | `POST /api/cockpit/undo` | `helicon/cockpit.py:371` `unrule_claim`; API `:61` |

---

## Commands run (fresh-agent minimal path)

All keyless. Demo seed only. No `config.json`, no Qwen, no live connectors.

```bash
git pull --rebase origin main   # → Already up to date @ 8714be6
export TMPDIR="$HOME/pytmp"
python3 scripts/probe_handoff_2026_09_11.py
# artifact: /opt/cursor/artifacts/probe-handoff-2026-09-11.jsonl

TMPDIR="$HOME/pytmp" python3 -m pytest -q \
  tests/test_govern_batch.py::test_confirm_kill_undo_restores_cube \
  tests/test_govern_batch.py::test_undo_recovers_from_empty_decided_ids_via_receipt \
  tests/test_govern_batch.py::test_undo_is_total \
  tests/test_govern_batch.py::test_rule_truth_makes_the_guard_enforce_it
# → 4 passed in 0.75s
# artifact: /opt/cursor/artifacts/pytest-undo-totality.txt

TMPDIR="$HOME/pytmp" python3 -m pytest -q \
  tests/test_govern_batch.py tests/test_cockpit.py
# → 19 passed in ~31s
```

---

## Pass/fail per probe step

Re-derived from the latest probe JSONL (14 steps, 14 pass, 0 fail). Do not carry these — re-run the script.

| Step | Result | Expected | Actual (object) |
|------|--------|----------|-----------------|
| A_findings_decision_lane | **PASS** | decision lane non-empty | `decision_count=4`, first `audit-2` factual |
| A_factual_finding_in_db | **PASS** | Stripe factual open | finding_id `2` |
| B_govern_apply_batch | **PASS** | applied=1, receipt.applied | `guard_blocks_the_wrong_claim=true`, compiled into law |
| C_returned_result_guard_blocks | **PASS** | receipt verify true | recorded + compiled + guard blocks |
| C_guard_object_independent | **PASS** | `guard_output` unclean on wrong claim | probe `Stripe is live — real money` → `clean=false` |
| B2_zup_bound_focus_route | **PASS** | routed=prompt containing finding id | HTTP 200, prompt names Stripe ruling |
| B2_zup_bound_vault_file | **PASS** | file written | `data/next-moves/next-moves-2026-09-11.md` exists (gitignored under `data/`) |
| D_baseline_naive_decision_only | **PASS** (finding) | naive arm runs | `human_decision` only → `guard_clean=true`, **0** correction cubes — **govern beats naive on enforcement** |
| E1_govern_undo_total | **PASS** | fully_reversed, decision null, cubes gone | all three |
| E2_double_undo_http | **PASS** | second undo 400 | `batch already undone` |
| E3_cockpit_undo_on_govern_finding_refused | **PASS** | cockpit refuses non-review | `not an output-review finding`; govern still settled |
| E4_confirm_kill_undo_restores_cube | **PASS** (cleared after fix) | kill then restore prior status | before `pending` → after_apply `killed` → after_undo `pending` |
| E5_vacuous_fully_reversed_cleared | **PASS** (cleared after fix) | empty `decided_finding_ids` must not leave ruling | receipt_json recovers ids; `human_decision_still=null`; FocusReview checks `fully_reversed` |
| E6_queue_undo_ui_refuses_zero_restore | **PASS** (UI cleared; API shape kept) | UI must not celebrate `restored:0` | API still `ok:true, restored:0`; App.tsx now errors |

### First-run evidence (before Slice 2 fix) — reproduced, then fixed

Captured in the same probe script before the govern/UI patch:

- **E4 REPRODUCED:** `confirm`+`acted` on temporal killed `demo-stripe-test`; undo set `fully_reversed=true` and cleared `human_decision` while `review_status` stayed `killed`.
- **E5 REPRODUCED:** corrupted `undo_json` to `decided_finding_ids:[]` → HTTP 200 + `fully_reversed:true` while finding stayed `resolved:…`; FocusReview set `undone` on any 200 without reading the flag.

---

## Ruling / undo verdict

| Inconsistency | Status | Evidence |
|---------------|--------|----------|
| Govern undo leaves confirm-kill permanent | **CLEARED** | `killed_cubes` in undo payload + restore; `test_confirm_kill_undo_restores_cube` |
| Vacuous `fully_reversed` on empty decided ids | **CLEARED** | undo unions receipt applied ids; FocusReview requires `fully_reversed` |
| Cockpit undo vs govern finding | **CLEARED** (correct refuse) | E3 |
| Double govern undo | **CLEARED** | E2 → 400 |
| Queue undo `ok:true` / `restored:0` | **API kept; UI cleared** | E6 — API count is honest; App.tsx now errors on zero restore |
| Live ZUP inbox after correction | **UNVERIFIED here** | no `~/.zen/zup-active.json` / ZUP checkout in this VM |

---

## Baseline arm (not built by us)

Naive: `UPDATE audit_log SET human_decision=…` with **no** correction cube.  
Result: guard stays clean on the competing value (`guard_clean=true`).  
Govern `rule_truth`: same class of claim blocked. **Govern wins on enforcement; the naive two-hour arm does not.**

---

## Open gaps

1. Live ZUP process / `zup-active.json` not probed (out of this checkout).
2. Cockpit end-to-end on a real `~/CODE` terminal not run here (no private repos; unit path covered by `tests/test_cockpit.py`).
3. `tests/test_govern_api_boundary.py` **fails to collect** under current env: `DeprecationWarning: anyio.abc.BlockingPortal` promoted to error by `pyproject.toml` `filterwarnings`. Pre-existing packaging/skew relative to this VM's starlette/anyio — not introduced by the undo fix. Bypass observed: `pytest -W 'ignore::DeprecationWarning'`.
4. Receipt field `correction_cube` on the HTTP receipt item is still null even when a cube was written (undo_json tracks it); cosmetic receipt gap, not an enforcement gap.

---

## What Oscar must rule (one glance)

1. **Accept** clearing E4/E5 on this branch (kill-restore + vacuous-undo + FocusReview/`App.tsx` checks), or demand a narrower docs-only receipt without the fix.
2. **Whether** `/api/queue/undo` should stop returning `ok:true` when `restored=0` (UI already refuses; API still green-counts).
3. **Whether** a follow-up must open a live ZUP inbox on his machine (Slice 3) before calling the FUTURE handoff proven end-to-end.
4. **What to do** about `test_govern_api_boundary.py` × anyio DeprecationWarning under `error::DeprecationWarning` on this VM image.
