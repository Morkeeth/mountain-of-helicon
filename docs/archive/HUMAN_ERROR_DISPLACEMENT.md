# Human-Error Displacement — "should this have required a human?" audit

Every place a user could become the monitoring system for a *deterministic*
failure. Classification: **Prevent** (impossible) · **Preflight** (block with a
reason before mutation) · **Detect** (surface + recovery) · **Recover**
(auto retry/rollback/idempotent) · **Human** (genuine judgment only).

## Findings

| # | User journey → failure a user could observe | Class | Status | Regression test | Severity |
|---|---|---|---|---|---|
| 1 | Apply a batch; the API 500s/network drops → screen freezes, no receipt, no error. User can't tell if it applied. | Detect + Recover | **Automated** — the batch view catches the throw, shows "Not applied: … nothing was written; retry", keeps staged rulings. | `test_apply_never_reports_success_on_a_bad_ruling` + UI error state | blocks trust |
| 2 | Click Undo; it fails silently → user believes the batch was reversed when it wasn't. | Detect | **Automated** — undo error surfaces "Undo failed: … the rulings are still applied", offers Retry undo. | (UI) + `test_double_undo_is_prevented` | blocks trust |
| 3 | Batch partly fails; UI optimistically drops **all** staged findings → queue diverges from server; the *failed* one silently vanishes until a refetch resurfaces it. | Prevent | **Automated** — on Done, only findings the receipt marks `applied` are removed. | `test_apply_never_reports_success_on_a_bad_ruling` (asserts failed≠applied) | painful |
| 4 | Apply an empty batch. | Preflight | **Automated** — Apply disabled when empty; API returns 400. | `test_empty_batch_is_rejected_not_silently_ok` | polish |
| 5 | Double-click Apply / back-button / retry Undo → double application or double reversal. | Prevent | **Automated** — `applying`/`undoing` disable the buttons; undo is idempotent (2nd undo → 400; unknown token → 404). | `test_double_undo_is_prevented` | painful |
| 6 | Receipt says "compiled into GOLDEN_RULES" but nothing persisted. | Detect | **Automated** — the receipt's verify-probe is checked against real post-apply state (`recorded_in_audit_log`, `compiled_into_law`); persistence re-queried over the wire. | `test_apply_persists_what_it_claims` | blocks trust |
| 7 | Queue demands a human ruling on an ungrounded single-source "phantom" that the engine should auto-retire. | Prevent | **Automated** — `provenance` moved to the auto-managed lane; never enters the human queue. | (lane test, demo queue check) | blocks trust |
| 8 | First run opens an **empty** dashboard (0 memories) — looks broken. | Prevent | **Automated** — `helicon demo` seeds a populated store; judge-check asserts non-empty. | `test_demo_seeds_a_populated_store_with_a_ruling_queue` | blocks trust |
| 9 | Demo review queue leaks the host's real skills (`~/.claude/skills`). | Prevent | **Automated** — skill scan gated on the configured connector; demo scans nothing. | `test_skill_findings_do_not_scan_a_real_dir_without_the_connector` | blocks trust |
| 10 | `helicon serve` binds `0.0.0.0` → an unauthenticated mutation API on the network. | Prevent | **Automated** — default bind `127.0.0.1`; `--host` opts in with a warning. | `test_serve_binds_loopback_by_default` | blocks trust |
| 11 | `helicon route` emits "route to X" on coin-flip evidence. | Preflight | **Automated** — withheld below a Wilson-LB quality floor; prints "no model clears the floor". | `test_route_withheld_below_quality_floor` | painful |

## Deliberately still human judgment

- **The ruling itself** — which of two definitions is canonical, whether two live claims genuinely contradict, whether a preference is current. Interpretation, not a deterministic check. This is the product's whole point.

## Known-remaining (honest, not yet automated)

- **Staged batch lost on browser refresh** (client-only state; *nothing is written*, so no corruption — a re-rule, not a data loss). Deferred: persist a draft. Severity: polish.
- **Findings still read like a debugger** in some kinds — a legibility gap, not a deterministic failure. Roadmap: humanize + the meta-review that learns phrasing.
- **Cross-thread SQLite on any *sync* endpoint** would 500 under a threadpool (the govern endpoints are async, so unaffected). Pre-existing, outside this flow; flagged for a follow-up pass.

## The policy (binding)

**Every user-found deterministic error becomes a regression scenario before the fix is closed.** A bug a human caught is a monitor a human was forced to be; closing it without a test that fails on its return just re-hires the human. The test exercises the real boundary the user hit (HTTP/API for persistence and error paths; not only a unit function). If a failure genuinely needs human judgment, it is logged here under "deliberately human," not silently left in the queue.
