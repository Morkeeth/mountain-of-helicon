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

## Queue — ALL DONE (see NIGHTRUN-2026-07-21.md)
- [x] S0 groundwork: worktree DB + dogfood real data + baseline 393 green + npm install
- [x] S1 backend `/api/cockpit` — real terminals, enriched, privacy allowlist
- [x] S2 frontend `Cockpit.tsx` default tab — builds green
- [x] S3 INSPECT native artifact renderer (markdown + diff, dependency-free)
- [x] S4 COMPARE+RULE+APPLY — rule/revise/reject → receipt → undo (resolve_review)
- [x] S5 PROVE continuity — inject_into_claude_code → SANDBOX; contains-proof; include≠obey
- [x] S6 RETURN CALMER — ruled claims leave the queue
- [x] S7 adversarial — mobile-queue fix + honesty-guard test; keep/reject no dead buttons
- [x] S8 Brave desktop + 390px screenshots (01–08), no clipping
- [x] S9 closeout NIGHTRUN-2026-07-21.md
- Final: 401 passed, main frozen 0eef89f, nothing pushed.

## Guardrails
No push/merge/deploy. No commit on main. No `git add -A` (add named files only). Real non-sensitive local data only (NEVER vault journal/finance/wallet). Synthetic fixtures labeled as fixtures. inject write-back → sandbox, real ~/.claude gated. premise→probe→observed→decision for any causal claim.
