# Mountain of Helicon — product surface proposal (Take 1 of 2)

**What this is.** The human-facing surface for the suite described in PRODUCT.md — written so Oscar can rule on the CLI-vs-suite question (PRODUCT.md:81, "his call, not made") with something concrete in front of him. This renders the SUITE answer. PRD only; no code exists for this yet.

**Premise corrections carried in** (flagged to coordinator before writing):
- **Next-Prompt is not a tab.** PRODUCT.md:134 (the later ruling, 14 Aug): "NEXT PROMPT belongs to ZUP, not Helicon." Here it is a *handoff*, not a surface — see §3.
- **Brand exists and wins** (design law): Fraunces + Bricolage Grotesque + IBM Plex Mono are the shipped Helicon faces (`web/src/index.css`, self-hosted Jul 15). The desktop app inherits them. No new direction hunt.

---

## The one-line product

**The palace is where his agent operation learns about itself — and it learns from his keypresses.**

Every morning it answers: *what did my agents do while I wasn't looking, and what do I rule on now?*

## THE ONE SIGNATURE DEVICE — the Ruling Queue

One spine through the whole app. Every surface — output, rules, memory, skills — emits findings as **cards into a single serial-binary ruling queue**. Keyboard-first: one card at a time, one keypress rules it (his RULING review mode — never a grid, never a multi-option menu). And the device's teeth: **every keypress is stored as a human ruling and feeds the Q-value learner that already exists in the stack** (learns from human rulings only, so it can't reinforce its own echo). The palace literally gets smarter every time he rules.

Everything else stays quiet so this can be seen. No dashboards-of-dashboards, no status theater, no composite scores in the hero position (rejected, PRODUCT.md:61).

---

## 1 · TABS — five, in morning-read order

| # | Tab | Question it answers | State |
|---|---|---|---|
| 1 | **TODAY** | What did my agents do, what do they owe me | new — the default tab |
| 2 | **OUTPUT** | What was produced, is it any good | new — the accepted home of what fleetboard tried to be |
| 3 | **RULES** | Is what we wrote down still true | BUILT (the 13-class rot exam = 0.1.0) |
| 4 | **MEMORY** | Did the rule change what we did | new — his 14 Aug idea, the strongest expansion |
| 5 | **SKILLS** | Is my skill library any good | new — "we've long looked at skill reviewal" |

TODAY is the default because the full board is his default (architectural overview, not single-focus). Next-Prompt's slot goes to TODAY — the human-use overview the metrics steer asks for.

## 2 · PER-TAB CONTENT — what a human sees

### TODAY (default)
The morning read, one screen, no scrolling on a laptop:
- **The day strip** — a horizontal timeline of every agent session since he last looked: which harness (Claude Code, Cursor, cloud), duration, cost, and what each *claims* it produced. Each session is a block he can click into (→ its trace).
- **The owed number** — the single hero number, Fraunces, biggest thing on the page: **cards awaiting ruling**. The calm state is the design: "0 owed" on a quiet ground is a good morning; the number only gains color as debt ages.
- **The week in agents** — hours run, $ by model, artifacts shipped vs discarded, rulings made. Delta vs last week, stated in words not sparkline confetti.
- **What changed because you ruled** — the closing loop line: "you killed 6 memories Tue; retrieval stopped surfacing them; 2 rules you marked stale were rewritten." The palace showing it learned.

### OUTPUT
The produced-but-unreviewed inbox. Every artifact any agent produced (file, PR, doc, deploy) lands as a card: *what it is · which agent/session made it · the claim made about it · verified or not*. Cards enter the Ruling Queue like everything else. Sort is age-of-debt, not recency — the thing rotting longest is on top. This is fleetboard's job done in the place he said it belongs.

### RULES
The rot exam, presented honestly: each of the 13 classes as a row — FIRED / CLEAN / **UNMEASURED** (never a green tick for a class that could not fire; that lie is already fixed in the CLI and the surface must keep it fixed). A fired class expands to the receipt: the rule, the evidence, the SHA. One click → card in the queue: *still true / stale / rewrite*.

### MEMORY
Three lanes, all feeding the queue:
- **Inert rules** — TRUE, CURRENT, and ignored: the class that doesn't exist anywhere else (his 14 Aug idea). Shows the rule and the receipt that nothing acted on it.
- **Contradictions** — two stored rules that disagree, side by side, one keypress picks the survivor.
- **Store health** — live count, growth, retired, last scan age. Numbers, not meters.

### SKILLS
The skill library graded from *use*, not from prose: for each skill — when it last fired, how often it triggers vs how often it should have (missed-trigger detection from transcripts), what it cost, whether its description matches what it does. "Never fired in 30 days" is a card. "Fired and the output was ruled bad" is a card with the receipt attached.

## 3 · INTERACTION — the review flow

- **One queue, serial binary.** `j/k` next/prev · `y/n` the ruling · `space` expand receipt · `u` undo. Never two questions on one card.
- **Dictate-over with ID chips** — his proven phone-review pattern: every card carries a short ID chip; he talks over the queue ("kill H41, keep H42, H44 needs a rewrite") and the palace applies the rulings. Desktop and phone are the same surface at different widths.
- **A finding becomes an action, always one of three exits:**
  1. **RULED** — keep/kill/stale; written to the store; feeds the learner.
  2. **→ PROMPT** — the handoff: the card emits a framed prompt into **ZUP** ("Helicon may tell you your prompting is weak. ZUP hands you the prompt."). One keystroke, card closes, ZUP owns it from there.
  3. **→ FIX** — for rules/skills rot with a mechanical fix: show the diff, he approves, the file is patched. Never auto-applied.
- **Nothing rots in a list.** A card unruled for 7 days surfaces on TODAY as debt. The queue is the only place findings live; there is no second review surface to check.

## 4 · METRICS — traces, transcripts, human use. Not plumbing.

The steer, applied hard: metrics describe **his use of agents**, never agent internals. No token-throughput graphs, no latency percentiles, no composite eval score in a hero position.

- **TRACES** — per-session: what the agent was asked, what it did (tool-call narrative in prose, not a span waterfall), what it claims, what actually landed (SHA/file/URL), cost. Readable top to bottom like a story, mono reserved for IDs and SHAs.
- **TRANSCRIPTS** — every transcript from every harness, full-text searchable, in one place. This is the 166-transcript mining that reconstructed PRODUCT.md itself, shipped as a feature: *"the method that corrects the spec is the product"* (PRODUCT.md:115) — the Sriram bullet-4 claim ("retroactively look at usage and optimize"), which someone who is not Oscar already asked to buy.
- **USE OVERVIEW** — the TODAY week-strip at month scale: where his agent hours went, cost by model and by project, shipped vs discarded ratio, ruling velocity, and the one longitudinal line that matters: *is the stack getting better* — measured as rulings-per-week trending down while shipped-per-week holds. That is the palace's own honest scoreboard, and it is about him, not the agents.

## 5 · OPTIMAL FOR HUMAN EYES

- **Brand inherited**: Fraunces carries every hero number and display line; Bricolage for UI labels; Plex Mono for IDs, SHAs, timestamps only — never the whole voice (kill-list law).
- **Calm by default.** The 95% state is quiet: neutral grounds, one accent used only by meaning. No pulsing dots, no amber/green light-wall, no fake-precision counters. An empty queue *is* the design saying "nothing owed."
- **Numbers are heroes**: one number per screen gets the Fraunces-display treatment; everything else steps down 3× jumps, max 4 sizes.
- **Desktop-native shell**: local-first (SQLite already is), menu-bar presence whose only badge is the owed count; global hotkey opens straight into the queue. The existing React `:8420` dashboard (HEALTH/FINDINGS/LOG) is the seed this subsumes — same brand, same API, new spine.
- **Review is the whole UI.** If a screen doesn't feed the queue or explain a ruling, it doesn't exist.

---

## Out of scope, named so it isn't re-invented
- **The second product** (scoring a stranger's stack against a reference, PRODUCT.md:117) — different artifact, not this surface.
- **Next-Prompt generation** — ZUP's. Only the handoff lives here.
- **Mount Helicon** — frozen; untouched by all of this.

## The decision this doc tees up (his, not ours)
CLI-that-grows vs suite-that-contains-the-CLI (PRODUCT.md:81). This proposal is the suite answer rendered. If he rules CLI, the Ruling Queue still stands — it becomes `helicon review`, the one-card-at-a-time terminal flow, and the tabs collapse to subcommands. The signature device survives either ruling; only the shell changes.
