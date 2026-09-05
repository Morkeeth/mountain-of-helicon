# Helicon — readable setup review

5 September 2026. Scope: the local Setup experience and its ZUP source checks.
This is not a replacement for the broader product vision or a launch claim.

## Current build

Setup is the default view. It shows a small set of actionable findings, then opens the affected records and evidence on demand. Unrelated global warning counts and review percentages are not part of this view.

The memory explanation separates saved conversations, copied memories, search preparation and recorded use. Each has a source and an explicit limit. These observations do not prove an end-to-end ingestion or benefit pipeline.

Project checks read ZUP's board, immutable state events, action queue and explicit intent records independently. A phase correction is not a submission or accepted outcome. Broken event references remain unverified. Changed or unavailable pinned documents produce their own findings.

The review endpoint is read-only: `GET /api/setup/review`. It does not run ingestion, consolidate memories, rebuild vectors or call a model.

## Verification

The following full-suite result predates the overnight source/correction extension below.

The frontend builds. Browser review exercised the default view, memory explanation, source evidence and affected-project disclosure. Deterministic tests cover missing and empty stores, field gaps, wrong-project receipts, independent questions, phase-only evidence, invalid intent and changed documents. The integration was also read against an actual native-written ZUP fixture.

The final full suite passed 1,193 tests, with one skipped and two expected failures. The existing two package-metadata test failures remain separate from this work. No source scan or successful build is presented as proof of memory quality.

## Next evidence to establish

Use a fixed, independently labelled set of real project questions. For each, record the source date, retrieved evidence, whether the answer is correct/current, and whether the agent used it. Keep failures and abstentions in the denominator. Compare actual work outcomes before claiming memory improves results.

This is a suggested next experiment, not a measured result, automatic job or new obligation for the project owner. It requires no extra dashboard. Broader product requirements and older backlogs retain their historical scope; do not turn their old next steps into current actions.

## Overnight source review and correction

The existing Setup screen now has a project instruction review. It reads configured project and harness candidates, preserves exact source versions and quotes, and separates file availability from reported loading. Supported checks are narrow: explicit same-subject phase/version/status declarations, exact local file references, and literal MCP tool declarations. Free-form correctness, runtime tool exposure, and the full effective model context remain unmeasured.

The user can save an immutable review, inspect a finding, propose replacement text with a reason, preview the exact diff, apply against the reviewed source hash, inspect history, and undo. Only files in the selected configured project can be corrected here. Global instructions remain read-only. A later edit blocks apply or undo; the service does not claim a filesystem-wide compare-and-swap guarantee against uncooperative external editors.

Comparisons use an explicit pinned earlier review. A missing finding is resolved only if equivalent successful checks covered its sources. Missing or changed coverage remains unchecked. Proven recurrence requires an intervening clear review; repeated scans do not advance the baseline or refresh a source's modification time.

Selected project sources can be prepared as a minimal local packet for an exact provider/run/project. Preparation is not delivery. The local MCP consume tool returns the reviewed source bytes and records a receipt; comprehension and behavior remain separate. These tools are excluded from remote MCP access. Packet and correction records remain local, outside git.

### Exercised at the first slice boundary

- Real browser: review, save, conflicting exact spans, edit, diff preview, stale-source refusal, apply, pinned comparison, evidence history, and undo.
- The controlled fixture retained different-subject noise without a false conflict. A missed longer read instruction was retained as a failed case and added to parser tests; the UI then displayed its missing path.
- Targeted source/correction/history/packet/API suites passed. Frontend build passed. A full combined suite and real-agent behavior proof are still pending at this boundary.
- No live personal instruction file was corrected. The controlled project is labelled test data; its events do not count as user acceptance or production outcomes.

### Resumed proof, 5 September

A fresh agent consumed the corrected packet through the real local MCP interface,
then calculated the inventory from the requested source. An independent reviewer
read the catalog and verified the exact result: 5,430 EUR cents, excluding the
inactive row. The earlier original-packet agent had stopped at the missing source.
The separate consumption receipt and artifact-bound behavior review persist in
private project state. This proves the controlled correction-to-next-run path,
not general memory benefit, production acceptance, or other provider coverage.

`context_handoff.prepare_handoff` now prepares a private `zup.helicon-origin/1`
reference for one explicit project ID, snapshot and finding. It verifies source
hashes, exact quoted byte spans and evidence revision, publishes an immutable
origin file outside source repositories, and does not create a task or send work.
The consumer must validate again: preparation does not prevent later source drift.

The 91 targeted source, correction, history, packet, handoff and API tests pass.
The frontend builds with the installed Node 22 runtime; the shell's Node 16 does
not meet Vite's documented runtime requirement. Two selected actual instruction
files were also copied byte-for-byte into private temporary storage and reviewed.
That copy check retains unknown loading and absent dependencies; its missing-path
findings are not claims about the original setup. No global source was changed.
