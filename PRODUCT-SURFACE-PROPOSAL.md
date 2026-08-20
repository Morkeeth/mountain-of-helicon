# Mountain of Helicon — product surface proposal v2

> **v2, 2026-08-20, rewritten to Oscar's direct rulings tonight.** v1 (the Ruling-Queue-as-spine take) is superseded — his words: *"Not sure we need RULING in here actually, only on HARD core drifts, it should be data."* v1 lives in git history (df40c96). Next-Prompt→ZUP was confirmed and stands.

## The rulings this version encodes (his, tonight)

1. **Data over rulings.** The surface is a mirror, not a chore. Ruling is reserved for HARD drifts only (a live contradiction, an identity fork). Everything else is data he looks at.
2. **No TODAY tab.** The palace is not a morning to-do; it is *current setup · history · query old things*.
3. **"It needs to feel like a self improvement tool."** The organizing feeling: you open it to get better, the way you open a training log — not to clear a queue.
4. **The setup review is for strangers too.** "How many skills, routines… how good are you, for users to come in" — the SECOND PRODUCT (PRODUCT.md:117, scoring a stack against a reference) is no longer out of scope; it is the front door.
5. **Back to the tweet** (Sriram, PRODUCT.md:105): the product claim to own is bullet 4 — *"retroactively look at usage and optimize for cost / better results"* — plus memory/context portability.
6. **Frontier check ordered:** a full search on the state of memory/context/knowledge for agents, folded into the project's status docs so progress is shareable. (Running tonight; lands as `docs/memory-context-frontier-2026-08.md`.)

---

## The one-line product (v2)

**The mirror of your agent operation: what your setup is, how good it is, and everything it has ever done — queryable.**

A self-improvement tool. The loop is *look → understand → tweak the stack → watch the number move* — not *review → approve*.

## Three surfaces

### 1 · SETUP — "this is your stack, and this is how good it is"

The review page of the agentic operation, one screen:

- **The census**: N skills (which fired this month, which never fire) · N routines/crons (last run, health) · N memories live / retired · N context files and **where context lives** (CLAUDE.md, rules files, vault, memory dir — with sizes and last-touched) · connectors and what they feed.
- **The score**: how good is this setup, judged against a reference of what good looks like (the frontier doc keeps the reference honest). Subscores: skills hygiene · memory health · context weight · routine liveness. Data first — every subscore expands to the rows behind it.
- **Golden rules relevance**: each GOLDEN_RULES entry with evidence of when it last mattered — *is this still relevant?* shown as data (last-cited date, still-true check), not as a ruling demand.
- **Same page, stranger mode**: a new user runs it on their machine and gets the identical census + score on day one. That is the doorway product; Oscar's own page IS the demo.

### 2 · HISTORY — traces, transcripts, query old things

- **TRACES**: every agent session (Claude Code, Cursor, cloud) as a readable story — what was asked, what it did, what landed (SHA/file), cost. Filterable by project, model, week.
- **TRANSCRIPTS**: full-text search over every transcript from every harness. "What did we decide about X in July?" is a query, not an archaeology dig. (The 166-transcript mine that reconstructed PRODUCT.md, productized — the method that corrects the spec is the product.)
- **Retro-optimize** (the tweet's bullet 4): where the hours and $ went, by model and project; shipped vs discarded; what a cheaper model could have carried. The self-improvement numbers: *your month vs last month.*

### 3 · DRIFT — the rot exam as data, ruling only when it's hard

- The 12/13 classes as rows: FIRED / CLEAN / UNMEASURED, receipts inline, honest states preserved. No queue, no debt counter — data.
- **The only ruling surface in the app**: HARD drifts — a live cross-source contradiction, a forked identity — where only a human can say which is true. Everything softer (staleness, decay, hygiene) is auto-managed and just visible.

## What carries over from v1
- Next-Prompt is ZUP's; a finding can still emit a framed prompt there (a "→ prompt" affordance, not a surface).
- Brand inherited (Fraunces / Bricolage / Plex Mono, `web/src/index.css`); calm default; numbers as heroes; no status theater.
- The existing `:8420` findings-first dashboard is the seed; this reshapes its IA to SETUP · HISTORY · DRIFT.

## Sharing progress (his ask tonight)
The frontier research + this proposal go into the repo's status/context docs so the project's state is shareable with others: `docs/memory-context-frontier-2026-08.md` (landing tonight) + this file. The README stays the stranger's door.

## Open questions for Oscar (queued, one at a time)
1. SETUP score: judged against WHOSE reference — his own past (self-improvement) first, or the "ultimate truth" reference (stranger scoring) first? Sequencing decision, changes build order.
2. Desktop-native shell vs the existing web app at `:8420` — the CLI-vs-suite question (PRODUCT.md:81) still stands and now has two concrete versions to rule between.
