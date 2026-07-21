# Mount Helicon V2 — night-run orientation & queue (2026-07-21)

Durable scratch note (survives context summarization). Worktree: `helicon-v2-night-run-2026-07-21`, branch `night-run/2026-07-21-helicon-v2`, base `0eef89f`. Main = FROZEN, never touch.

## Mission (Oscar, tonight)
The full daily-use product — "the ultimate OS for memory, context, reviewing output." NOT hackathon-scoped. The hero sentence must become materially real on real local data:
> "Five agents ran. I can see exactly what each produced, catch the wrong claim before it spreads, correct it once, and know the next run received the correction."

Loop: ORIENT → INSPECT → COMPARE → RULE → APPLY (staged, receipt, undo) → PROVE continuity → RETURN CALMER.

## What already exists (REUSE — do not rebuild)
- **INSPECT+COMPARE**: `review_terminals.verify()` — real git/route/pytest verification + per-claim receipt. WIRED (`helicon review --terminals [--run]`).
- **RULE+APPLY+receipt+undo**: `POST /api/govern/apply-batch` + `/api/govern/undo-batch` (`api/govern.py`). Atomic, proves each ruling landed (runs guard to prove wrong claim now blocked), real total undo. WIRED.
- **rule_truth captures correction** into governed law (`govern.py:48`). Route "Revise" through this.
- **Context PULL**: `helicon_context` / `guarded_context` splits safe vs flagged-by-ruling. WIRED.
- **Judge bench**: swappable model (`helicon judge-bench`). WIRED.
- **Frontend**: `FocusReview.tsx` already does question→consequence→rule→apply→receipt→undo for FINDINGS. `RunsView` reads `/api/runs`. Tokens/fonts: Fraunces/Bricolage/IBM Plex Mono, paper+ink palette. 390px shell already built (bottom bar `BAR_TABS`).

## Built-but-DEAD (must WIRE, safely)
- `taskrun.py` — full TaskRun/ContextPacket spine (freeze objective+acceptance, content-addressed immutable packet, artifact+verification, receipt). ZERO callers. No delivery step.
- `compiler.inject_into_claude_code` (`compiler.py:213`) — push corrected law into `~/.claude/skills/`. ZERO callers. **SAFETY: must write to a SANDBOX dir, NOT Oscar's live ~/.claude/skills. Real target = human gate.**

## Net-new (small)
- `/api/cockpit` endpoint (ORIENT+COMPARE data from review_terminals, enriched: objective, artifacts, needs_human).
- `Cockpit.tsx` default opening tab.
- **Native artifact renderer** (markdown/diff/test-receipt/claim+source) — the one true net-new piece; nothing renders artifacts today.
- Continuity proof surface (after Apply → next context read contains the correction).

## Queue (build straight down, commit each, keep suite green)
- [ ] S0 groundwork: worktree DB + dogfood `review --terminals` (real data) + baseline pytest green count + npm install
- [ ] S1 backend `/api/cockpit` — real terminals → enriched RunCards (objective, changes, artifacts, claims+verdicts, needs_human)
- [ ] S2 frontend `Cockpit.tsx` default tab — calm ORIENT queue on real data; `npm run build` green
- [ ] S3 INSPECT native artifact renderer — click terminal → rendered md / diff / test-receipt / claim+source
- [ ] S4 COMPARE+RULE+APPLY — wire cockpit rule buttons to govern apply-batch; Revise→rule_truth; staged preview → receipt → undo
- [ ] S5 PROVE continuity — wire inject_into_claude_code to SANDBOX + build/deliver ContextPacket; show correction now in next agent context (include vs obey distinction)
- [ ] S6 RETURN CALMER — ruled items leave queue (never-twice), noise removed
- [ ] S7 adversarial: attack truth (stale branch, missing artifact, deceptive closeout, false propagation) + attack experience (cold start, overload, buried artifact, mobile clip, dead button); fix + re-run
- [ ] S8 verify in Brave desktop + 390px, screenshots to artifacts/v2-night-run-2026-07-21/
- [ ] S9 closeout NIGHTRUN-2026-07-21.md (required sections)

## Guardrails
No push/merge/deploy. No commit on main. No `git add -A` (add named files only). Real non-sensitive local data only (NEVER vault journal/finance/wallet). Synthetic fixtures labeled as fixtures. inject write-back → sandbox, real ~/.claude gated. premise→probe→observed→decision for any causal claim.
