# Mountain of Helicon — the user journey, its feature categories, and the build plan

*2026-08-20 late. Complements PRODUCT-SURFACE-PROPOSAL.md (v3) — that doc rules WHAT each surface is; this one structures WHO moves through the product, phase by phase, and what exists vs what's missing at each step. Oscar's ask verbatim: "we're missing the CATEGORIES of feature, of all the phases of the user journey — structure, and compose a build plan that tackles all of them."*

Two-flows ruling holds throughout: **Helicon = PAST** (what happened, how good it is, catches and reversals). Anything FUTURE-shaped hands off to ZUP over the shared data spine; UIs never merge.

---

## The journey — 7 phases, 7 feature categories

| # | Phase | The user's question | Feature category | State today |
|---|---|---|---|---|
| 0 | **DISCOVER** | "What is this?" | README + the shared score artifact | README exists; no shareable artifact yet |
| 1 | **ARRIVE** | "How do I start?" | Onboarding & cold start | `pip install` → `helicon setup` (zero-config, cold-verified) → `helicon init && helicon scan` → `helicon serve`. Works, but the product never *tells* you this path — it lives in docs only |
| 2 | **FIRST LOOK** | "How good is my stack?" | Census & score (SETUP) | ✅ BUILT tonight: census, axis-2 chips with citations, first reading = baseline |
| 3 | **DAILY DROP-IN** | "What needs me today?" | Drift data & rulings | ✅ Findings queue (decision lane), Cockpit (agent-output claims), rot exam. Data-first per ruling; rulings only on hard drifts |
| 4 | **WEEKLY REVIEW** | "What happened this week?" | Retrospective & trend | Partial: This Week tab is the door; `measure` series exists; axis-1 trend built tonight — but the three are **not joined into one weekly read** |
| 5 | **ISSUES** | "What went wrong, and is it fixed?" | **Catches ledger** | ❌ THE GAP. Tonight alone produced 6 real catches (wrong branch, stale cron, false embedding claims, cron miscount, pytest-contaminated config, ci-parser regression) and they live in git messages and chat scrollback, not in the product. Helicon=PAST explicitly includes "catches and reversals" — the category has no surface |
| 6 | **IMPROVE** | "Did acting on it move the number?" | Improvement loop | Partial: chips say what to fix; the trend can show movement; nothing links *this fix* → *that delta*. Next-action generation is ZUP's (spine handoff) |
| 7 | **SHARE** | "Can I show someone?" | Outward artifact | ❌ Nothing. The score is web-only on localhost. H3 of the roadmap; the wedge doc says setup-sharing culture is huge and unscored |

**The reading of the table:** phases 2–3 are strong (built or shipped tonight), phase 1 works but is invisible, phases 4–6 are half-built and unjoined, phases 0 and 7 are empty. The build plan below tackles every non-green row.

---

## The build plan — 6 slices, riskiest first

**1. The Catches Ledger (phase 5 — the missing category).**
A `catches` table + `/api/catches` + a CATCHES tab: one row per caught issue — what was claimed/expected, what was true at the object, who/what caught it, the fix SHA, reversal state (open / fixed / reverted). Seeded with tonight's 6 real catches so it is born with real data, never lorem. CLI: `helicon catch add` / `helicon catch list`.
*Done when: the 6 catches from 2026-08-20 render as rows with their fix SHAs, and a new catch can be added from the CLI in one line.* · size: M · risk: the data model — a catch must reference claim + object + fix without becoming a free-text notes app; mitigate by modeling on the existing cockpit finding shape.

**2. Onboarding made visible in the product (phase 1).**
The product tells you the path instead of the docs: `helicon setup` cold output ends with "next: helicon init && helicon scan"; every empty state in the web app (no store, no snapshots, no findings) names the exact command that fills it; README gets the 4-line quickstart at the very top.
*Done when: a stranger with an empty HOME can go install → setup → init → scan → serve guided only by what the product itself prints.* · size: S · risk: none — mechanical, high leverage.

**3. The Weekly Review joined (phase 4).**
This Week becomes the one-read weekly: the axis-1 setup trend (this week vs last), the week's catches (from slice 1), the week's rulings, and the measure series — one screen, no hunting. This is the "how can I see my weekly review" answer made true.
*Done when: #week shows setup-trend delta + catches count + rulings count for the calendar week, each drilling into its source tab.* · size: M · risk: ThisWeek already has an owner-shape; extending without breaking its one-read discipline.

**4. Fix→delta linking (phase 6).**
When a chip flips FAIL→PASS or a catch closes, the next snapshot records what changed; the trend annotates the point ("validity windows landed here").
*Done when: fixing one chip produces an annotated point on the trend that names the fix.* · size: M · risk: attribution — only annotate what a snapshot can actually see; no inferred causality.

**5. The shareable report (phase 7).**
`helicon setup --html` renders the graded report (census + chips + citations, UNMEASURED preserved) as one self-contained HTML file a person can post; stranger mode = the same file on their machine.
*Done when: one command emits a single file that renders offline and contains zero personal paths beyond what the user chooses to show.* · size: M · risk: privacy — path redaction must be default-on.

**6. DISCOVER polish (phase 0).**
README restructured around the journey: quickstart → what you get at each phase → the score. The flipbook (real screens) embedded.
*Done when: the README's first screen is the 4-line quickstart + one image, and `helicon ci` R2 stays CLEAN after the edit.* · size: S · risk: none — deliberately last, polish after substance.

---

**Sequencing note:** slice 1 first because it is the missing *category* (everything else improves an existing one), it is Oscar's live pain ("we had a lot of issues that should be tracked"), and its data model is the one real unknown. Slices 2–3 make the product self-explaining; 4–5 close the loop and open the door; 6 is polish. After slice 1 ships: re-read reality, re-plan the rest — this plan is disposable.
