# Helicon — readable setup review

5 September 2026. Scope: the local Setup experience and its ZUP source checks.
This is not a replacement for the broader product vision or a launch claim.

## Current build

Setup is the default view. It shows a small set of actionable findings, then opens the affected records and evidence on demand. Unrelated global warning counts and review percentages are not part of this view.

The memory explanation separates saved conversations, copied memories, search preparation and recorded use. Each has a source and an explicit limit. These observations do not prove an end-to-end ingestion or benefit pipeline.

Project checks read ZUP's board, immutable state events, action queue and explicit intent records independently. A phase correction is not a submission or accepted outcome. Broken event references remain unverified. Changed or unavailable pinned documents produce their own findings.

The review endpoint is read-only: `GET /api/setup/review`. It does not run ingestion, consolidate memories, rebuild vectors or call a model.

## Verification

The frontend builds. Browser review exercised the default view, memory explanation, source evidence and affected-project disclosure. Deterministic tests cover missing and empty stores, field gaps, wrong-project receipts, independent questions, phase-only evidence, invalid intent and changed documents. The integration was also read against an actual native-written ZUP fixture.

The final full suite passed 1,193 tests, with one skipped and two expected failures. The existing two package-metadata test failures remain separate from this work. No source scan or successful build is presented as proof of memory quality.

## Next evidence to establish

Use a fixed, independently labelled set of real project questions. For each, record the source date, retrieved evidence, whether the answer is correct/current, and whether the agent used it. Keep failures and abstentions in the denominator. Compare actual work outcomes before claiming memory improves results.

This is a suggested next experiment, not a measured result, automatic job or new obligation for the project owner. It requires no extra dashboard. Broader product requirements and older backlogs retain their historical scope; do not turn their old next steps into current actions.
