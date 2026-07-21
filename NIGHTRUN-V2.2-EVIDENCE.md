# V2.2 night run — live evidence note (2026-07-22)

Mission: **Real Run Capture + Acceptance Closure** — one real Claude Code session → a governed Run in the Cockpit (ORIENT→INSPECT→REVIEW ARTIFACT→ACCEPT/REWORK/REJECT→RECEIPT) + close the 4 Codex P0 trust boundaries. Worktree `helicon-v2-night-run-2026-07-21`, branch `night-run/2026-07-21-helicon-v2`, base `728d081`, main frozen `0eef89f`.

## Governed-Run header (this run, captured before execution — manual dogfood of the mission)
- **start_commit:** `728d081799ebc0cd986db2eba6a8e01159ed6974` (`728d081`)
- **start_time:** 2026-07-21T22:27:41Z (00:27 local, Jul 22)
- **model / harness:** `claude-opus-4-8[1m]` · Claude Code CLI
- **branch / worktree:** `night-run/2026-07-21-helicon-v2` @ `~/CODE/helicon-v2-night-run-2026-07-21`
- **prompt (unchanged):** `01 Projects/Helicon/helicon-v2.2-real-run-capture-opus-prompt-2026-07-22.md` lines 16–211, used verbatim.
- **acceptance contract = the prompt's 11-item Definition of Done (frozen now):**
  1. A real safe Claude Code session is discovered dynamically, including its worktree.
  2. Its exact prompt chain, actual timing, model/harness and real token fields appear in a Run.
  3. Historical unknowns are labelled retrospective/unknown rather than reconstructed as facts.
  4. A new governed Run is opened with objective and acceptance captured before its artifact.
  5. The Run receives a frozen ContextPacket and an honest delivery state.
  6. A real artifact is attached, hashed and rendered natively in the Cockpit.
  7. The 390px review flow allows Oscar to accept, request rework or reject.
  8. Acceptance closes the Run and may promote the prompt; rejection cannot promote it.
  9. The receipt survives process restart and can reconstruct the Run without current mutable context.
  10. All four P0 trust boundaries have regression tests and real manual probes.
  11. Personally drive the flow start to finish in Brave and the terminal — an HTTP 200, passing suite, shell screenshot, or seeded fixture alone is insufficient.

## Provisioning gate — PASS
pwd/branch/status/worktree/HEAD all verified. Only `config.night.json` untracked. main = 0eef89f (frozen).

## Plan (risk-first)
- [ ] P0-1 artifact path traversal → canonical containment + server-side safe-root allowlist
- [ ] P0-3 continuity manufactures evidence → read-only, no record_surfaced/retrieval_log mutation; label delivered-to-file vs obeyed
- [ ] P0-4 undo doesn't reverse propagation → regenerate context sandbox from DB on undo; frontend honors server response
- [ ] P0-2 mutations trust browser payload → server re-derives claim+verdict by (terminal,pair_key); never trust client truth-fields
- [ ] Session discovery (dynamic, worktree-aware, privacy default-deny) — replaces hardcoded terminal list
- [ ] Real capture (prompts/model/tokens/timing/artifacts) reusing runs.py — no hand-copy
- [ ] Governed Run lifecycle: open(objective+acceptance) → packet → artifact → verify → human accept/rework/reject → receipt; imported/retrospective label for history
- [ ] Cockpit Runs view + Accept/Rework/Reject + receipt; prompt promotion only on accepted outcome
- [ ] Drive end-to-end in Brave desktop+390px; full suite; restart-persistence proof; closeout

## Evidence log (commands + observed)

### P0 trust boundaries — CLOSED + manually probed on live app (:8493), Jul 22
- **P0-1 traversal:** `GET /api/cockpit/artifact?repo_path=/Users/morkeeth/CODE/helicon&ref=../helicon-v2-night-run-2026-07-21/CODEX-REVIEW-PROMPT.md` → `blocked | path escapes repo` (was: sibling file returned). Fix: `_safe_repo_root` + true containment (`==root or startswith root+os.sep`) + diff-ref `<base>...HEAD` allowlist. Test `test_p0_artifact_no_sibling_traversal`.
- **P0-2 server-authoritative:** forged `pair_key` POST → `ok=False: claim not present in server-verified state`. Fix: `rule_claim` re-derives claim+verdict server-side by (terminal,pair_key); API drops client `claim`/`repo_path`/`verdict`. Test `test_p0_rule_is_server_authoritative`.
- **P0-3 honest delivery + no manufacture:** rule → `retrieval_log` 5→5 (unmutated); continuity `{recorded:true, delivered_to_files:false, delivered_to_live_run:false, obeyed:null}`. Fix: removed the mutating `_proactive_context` self-match; `_delivery_state` is read-only. Tests `test_p0_ruling_does_not_manufacture_retrieval_evidence`, `test_revise_captures...`.
- **P0-4 undo reverses propagation:** propagate `delivered_to_files=True`; feed had correction; undo `ok=True reversed=True absent=True`; feed no longer has it. Fix: `unrule_claim` regenerates the sandbox via `_write_context_sandbox`; frontend honors the undo response. Test `test_p0_undo_reverses_propagation`.
- Suite: **405 passed** (402 + 3 P0 regressions). Commit `0f95726`.

### Real Run Capture + Acceptance Closure — DONE + driven on real data
- Dynamic discovery: `/api/run/sessions` → real safe sessions (all world-relay; wallet/okx/treasury/journal excluded by context_policy + safe-root allowlist).
- Capture (no hand-copy): real session → verbatim prompt "Smoke test: run 'git log…'", model `claude-sonnet-5`, 80,245 real tokens, harness `claude-code 2.1.201`, commit `9fcb9513`, artifact `DailyFavour.tsx` sha256 `218584c9f69cdc15`. provenance=imported; cost=unknown (never 0).
- Governed lifecycle: open(objective+acceptance) → packet → artifact → **human Accept/Rework/Reject** → append-only receipt (`opened→packet→artifact→accepted`). Promotion ONLY on accepted (prompt_library grew on accept, not on rework).
- **Driven in Brave** desktop + 390px: run list, run detail (envelope + verbatim prompt + native code artifact + verdict buttons), Accept → "prompt promoted". Screenshots `artifacts/v2.2-night-run-2026-07-22/01,04,05,06`.
- **Persistence (DoD #9):** after uvicorn restart, the accepted run reconstructs with prompts+artifact+events.
- Commits: `4798e4a` capture backend, `3789ffe` Runs UI. Suite **408 passed**.
- Remaining honest gaps: forward-governed (hook-opened before execution) not wired; delivery-to-live-run unproven; verification human-only; P2 museum debt (header/tabs) untouched. Detail in `NIGHTRUN-2026-07-22.md`.
