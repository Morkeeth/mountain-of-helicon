# Mount Helicon — build plan, next ups (2026-08-17)

**Grounded in Oscar's screenshot, 16:22.** The Review Queue shows items grouped REGRET (4) /
IDENTITY (5): `project-relay-roadmap`, `zup`, `readme`, `cursor`, `relay`, tagged WARNING / HIGH /
READ-ONLY. The selected item is the `nullspace` identity fork (submission vs wrapper). The actions
at the bottom are `A Acted` · `D Not rot·rule`. Oscar: *"I can't review this either, same fault."*

## The fault, named (same disease as ZUP)
Two halves:
1. **The queue mixes real decisions with cryptic memory fragments.** `project-relay-roadmap: RELAY
   roadmap Jun 9 2026: resubmitted to App Store...` tagged READ-ONLY is a memory note, not a thing
   Oscar rules on. The identity forks (nullspace, zup, readme) ARE real decisions — buried among
   fragments.
2. **The actions are jargon.** `A Acted` / `D Not rot·rule` — a human cannot tell what picking does.
   A fork needs: the plain question, the plain options, and what happens when you pick.

Plus a deploy gap: the card still shows `? memories`. The fix for that (read the genera map directly)
was merged to main today, but **the running `helicon-serve` app is the OLD build.**

## The vision (settled 2026-08-16)
Helicon is the WEEKLY review: *is my setup any good.* It opens once a week with the ~6 real
identity/contradiction forks, each one Oscar can rule on in plain words. Not a standing queue of
memory fragments.

## The slices (ordered; S0 is a redeploy, cheap and first)

### S0 — Redeploy the serve app to the merged build.
The rulable-card fix (no more `? memories`, correct source attribution) is on main but not running.
Rebuild and restart `com.morkeeth.helicon-serve`. Zero code.
- Done when: the running app shows real memory counts and correct source-per-claim.

### S1 — Human-legible actions. THE fix for "not for humans."
`A Acted` / `D Not rot·rule` → for an identity fork: **"Which is the real name?"** with the two
definitions as pickable options, and a one-line preview of what ruling does (writes the canonical
definition, retires the other). For a contradiction: **"Which is true?"** with the asserted values.
- Done when: Oscar can rule a fork without knowing what "rot·rule" means.

### S2 — Split the queue: decisions vs log.
Only genuine decisions in the review pane — the identity forks and the one cross-source
contradiction. The READ-ONLY memory fragments (roadmap notes, "Created: status_...") are a LOG, not a
decision; move them out of the human queue. Same rule as ZUP's session-dump.
- Done when: the queue shows ~6 rulable items, not 10 with 4 fragments.

### S3 — Group by what a human recognizes.
Not "REGRET / IDENTITY" (rot-class names). Group as **"Your setup disagrees about what X is"**
(the 5 forks) and **"A decision recorded two ways"** (the contradiction). The label names the
problem in Oscar's terms.
- Done when: a stranger reads the group headers and knows what's being asked.

### S4 — Surface the weekly-review features in the UI.
C (identity coherence) is done; A (overboard) and B (learning ledger) are built and re-pointed at
git/transcripts. Wire their output into the same one-page weekly read. `helicon resolve --list
--cards` is the CLI version; the app is the human version.
- Done when: the weekly page shows forks + overboard + learning-ledger, all rulable.

### S5 — The cadence: make it weekly, not standing.
It should open once a week with that week's real findings, not sit as an ever-present queue Oscar is
supposed to keep clear. A standing queue is the thing that made 449 findings pile up.
- Done when: the app has a "this week" review that closes, not an infinite backlog.

## The through-line (shared with the ZUP plan)
Identical fault, identical fix: **translate machine state into a decision with plain words and a
clear outcome, and show only what is genuinely a human's to decide.** ZUP surfaces sessions as
decisions; Helicon surfaces memory fragments as decisions. Both need the same filter and the same
translation layer. The gate for both: *would ruling on this row change how the system behaves?*
If not, it is a log line, not a decision.

## What NOT to do
- Do not add findings. The purge (449 to 6) was the highest-value act; keep the bar.
- Do not go to mem0. Helicon's product is the rot exam, which nobody else has.
- Do not let rot-class jargon reach the human. It is internal.
