# Mountain of Helicon — the ambitious roadmap (multi-model deep dive, 2026-08-20)

Synthesized from four independent takes — product-ambition (opus), architecture (sonnet), wedge-market (sonnet), skeptic (opus) — against PRODUCT.md, PRODUCT-SURFACE-PROPOSAL.md v3, and docs/memory-context-frontier-2026-08.md. Conflicts are ruled inline, with the losing take named. UNMEASURED stays UNMEASURED.

## North star (one line)

**Lighthouse for your agent stack: one command, a graded two-axis report on skills, routines, memory content and context files — every check cited, every failure a receipt — and a score you can put in your dotfiles README.** (ambition; the measured empty lane, frontier doc §Part 3: the primitives exist separately and "nobody has composed them"; two lanes — memory-store *content* quality and routines review — have zero entrants.)

**One fact frames everything below (skeptic §0, confirmed by ambition's table):** tonight's Setup page, the v3 proposal, and the frontier doc live only on `hackathon/adk-cloud`; `main` is behind; PyPI 0.1.0 is the pre-fix rot exam (PRODUCT.md:99); no `cmd_setup` exists in the CLI. By Oscar's own *ship-the-default-branch* law, the doorway product is currently reachable by nobody. The first horizon is mostly about ending that.

---

## The three horizons

### Horizon 1 — 2 weeks: the doorway opens (all four takes agree on this scope)

**Goal: a person who is not Oscar runs one command and sees their own stack graded.**

1. **Land it on main.** Merge `db8d1c2` + the unmerged `class-14-inert-rule` branch. *Done when: a clone of `main` at HEAD serves `/api/setup` and returns a census.* (ambition H1.1; skeptic K7 makes this a one-week kill check.)
2. **`helicon setup` — zero-config CLI.** The census + two-axis chips as terminal output, same code path as the API. Must clear the trust bar `helicon ci` already proved strangers cross: no key, no init, no config (wedge finding 3 — the real scorecard is currently web-only behind `helicon serve` + a populated DB; `cmd_stack` at cli.py:3534 is a thin unsourced predecessor, not this). Deterministic parts only, no Qwen key (proposal :30). Optional `--html` export for a screenshot. *Done when: `pip install mountain-of-helicon && helicon setup` prints a graded report on a machine that never ran `helicon init`, with at least one frontier-chip citation, and every unmeasurable cell says why.* (ambition H1.2 + wedge's day-one spec, merged — they specified the same slice independently.)
3. **Cold-start truth.** A stranger's day one must separate *your stack is thin* from *Helicon has not looked yet*. *Done when: a fresh HOME produces a report where no cell reads 0-as-a-grade.* (ambition H1.3.)
4. **Snapshot cadence + the split-brain cron fix.** `weekly_measurements`/`score_history` do not exist in the live repo DBs and neither command is in `nightly.sh` — the PRIMARY axis has zero automated data (arch finding 3). Wire `measure` + `score --record` into nightly **outside the `&&` chain** so a capture hiccup can't skip the week's reading; verify same-week idempotency before depending on it; fix or delete the crontab entry still running the stale `~/CODE/helicon` clone pinned at `35eb087` (arch slice 4). *Done when: two dated snapshot rows exist from unattended runs; `crontab -l` contains no reference to `~/CODE/helicon`; twice-in-a-week = one row per metric.*
5. **Fix the product's own doc rot before a stranger finds it.** Three confirmed self-inflicted instances of the exact failure the product sells detection of: CLAUDE.md claims "all-MiniLM-L6-v2, 384 dims, all memories embedded" — probe says dim=1024 Dashscope and 187 of 4,507 live cubes embedded (skeptic §2); PRODUCT.md:46 claims desktop-native is absent — `mac/Sources/Helicon/` is 4,065 lines of SwiftUI touched 2026-08-18 (arch finding 6); table count drifted 40→47. *Done when: `helicon ci` on this repo passes, or every failure is a filed fix.* A gift for a demo, a liability for a launch — Oscar finds these, not the first stranger.
6. **Publish 0.2.0.** *Done when: `pip install --no-cache-dir` from an empty HOME installs a version whose `helicon setup` runs.* (ambition H1.4.)

**Ships outward:** 0.2.0 on PyPI + **Oscar's own scored report posted where setup-publishers already show and tell** (Show HN / r/ClaudeAI / X) — publish-first, zero outreach, per the killed stunt-PR ban (PRODUCT.md:62; wedge channel ruling). The two honest FAILs (no validity windows, consolidation 46 days stale) are the demo, not the embarrassment (ambition §9).

### Horizon 2 — 6 weeks: the score nobody else can compute

**Goal: the report grades the CONTENT of a stack, not its shape. This is the moat** — every competitor in the frontier doc grades file shape; content quality of a personal store has zero entrants (frontier doc, empty lane #2).

1. **Memory-health subscore.** The rot exam's classes folded into axis 1; UNMEASURED never contributes a pass. *Done when: two users with identical file counts get different subscores, delta traceable to named contradictions and stale rows.* (ambition H2.1.)
2. **Inert rule live** (merged in H1, surfaced here). *Done when: a correct-and-ignored rule is reported and a correct-and-followed one is not.* (PRODUCT.md:83.)
3. **Transcript ingest — as probe substrate, not a viewer.** Arch slice 1 survives; arch slices 2–3 (HistoryView UI, traces) **lose to the skeptic** — five shipped tools already show usage (`/insights`, vibe-log, claude-view, Claudoscope, vibe-replay; frontier doc §7) and the frontier doc's own defense is "none feeds a stack score," which means the value is the score and the viewer is deferred cost. Build the sidecar `transcripts.db` (FTS5 external-content, incremental ledger, `author_kind` column — 46% of `type: user` turns are not Oscar, per the standing transcript-authorship gate) because two probes need it. *Done when: double-run does zero re-parse; a term in exactly one July session returns that session only.*
4. **Dead skills.** Join skill dirs against transcripts: fired vs never-fired, dates behind each. *Done when: the never-fired list is checkable by grep.* (ambition H2.3; needs slice 3.)
5. **Routines as data.** Wire `stackwatch.routine_findings` into the census: last run, silent-past-threshold. *Done when: a cron silent three intervals appears as a named finding.* (ambition H2.4 + arch; empty lane #3, zero entrants.)
6. **Validity windows.** `valid_until` column on `helicon_cubes` — the `superseded` enum half already exists (arch finding 5); stamp on the existing supersede call sites; `as_of` point-in-time queries. *Done when: a cube superseded today, queried as-of yesterday, returns the old value.* (Zep pattern, frontier steal #1; also clears one of tonight's own two FAILs.)
7. **Tense-rewriting as proposal, never mutation.** Regex pass over dates; a passed future date writes a *proposed edit* row for approval — `UNIQUE(content_hash)` makes in-place rewrite the wrong shape, and Cursor's killed unapproved-writes feature is the trust lesson (arch slice 6; frontier steal #2). *Done when: fixture "Aug 15" (past) yields one proposal; "Sept 15" (future) yields none.*
8. **The Goodhart gate on axis 1** (skeptic Risk 1, converted from objection to slice). The only recorded `score_history` is 7.5→60.9 in three days, both jumps the tool grading its own automated triage. Also: human-vs-auto in `reviews` is a string convention on `session_id` with no constraint. *Done when: every subscore has a written answer to "which of the tool's own actions can move this number," and reviewer provenance is a typed column, before axis 1 is shown to any stranger.*

**Ships outward:** the first named strangers (PRODUCT.md:89's done-when, reused verbatim): people who run `helicon setup` on their own machines and report what it said (K3 feeds on this).

### Horizon 3 — 90 days: the number leaves the machine

**Goal: the score becomes a social object** (empty lane #4: sharing culture thriving, entirely unscored).

1. **`helicon setup --card`** — self-contained SVG/markdown score card: two axes, census, chip verdicts with citations, run hash. Lands in the user's own dotfiles README — the sharing surface people already use, and the only one that respects the Vercel/artifact bans (ambition H3.1).
2. **Verifiable, not vanity.** *Done when: two same-day cards are byte-identical, and a card with 3 FAILs shows 3 FAILs on its face.* Benchmark theater is endemic (frontier doc §5); the receipt is the differentiator.
3. **GitHub Action, listed.** `action.yml` has sat unlisted since 10 Aug. *Done when: a repo Oscar does not own adds three lines and gets a PR annotation.* (PRODUCT.md:87.)
4. **Opt-in percentile corpus** — card fields only, never the store; last slice, not first. (ambition H3.4.)
5. **Ten strangers.** *Done when: ten cards exist not produced on Oscar's machine.* (ambition H3.5.)
6. **Desktop shell, Option B** — see Decisions. HISTORY UI ships **only if** K4's second-run pull is proven to exist by then (skeptic's condition, adopted).

---

## The score as a social object (the shareable moment)

The moment is: **a setup-publisher pastes their card into their dotfiles README and the card argues for itself** — verdicts, citations, and its FAILs visible. The audience is not "Claude Code users"; it is the named population who already publish their setups (dotfiles repos, "my setup" posts — wedge's archetype, frontier doc §3) and are missing exactly one thing: a comparable number. A scorecard is a screenshot; a FAIL log is not — the card leads, the rot exam is depth behind the door (wedge, resolving lead-artifact in favor of the census+score; PRODUCT.md:140-146 concedes cold `ci` is honestly ~4-5 classes). Two leaderboards exist and both rank *activity*; nobody ranks setup *quality* (frontier doc §3).

## Second / paying use case

**The team reference corpus** (ambition + wedge converge independently): a lead defines the org's reference — required skills, rules-file ceiling, consolidation cadence, sanctioned MCP servers — and every engineer's `helicon setup` grades against it; scores roll up. Paid precedent inside our own frontier doc: AIQ Rank sells private company leaderboards for teams/candidates — but measures activity and cannot see the setup. The buyer's number exists: arXiv 2601.20404 measured −28.6% runtime / −16.6% tokens from a rules file; twelve engineers with twelve unmeasured rules files is an invisible line item. Secondary: the one-off setup audit as a deliverable report (ambition case B).

**The general surface features grow from (the build-plan law's demand, stated once):** *a census with a pluggable reference.* Every roadmap item is a new **probe** (deterministic check + citation + verdict) or a new **census cell** (countable thing + how counted). Team mode = same engine, reference swapped. Leaderboard = reference set to a distribution. Action = output set to an annotation. Rows in a probe registry, not new pages.

## Decisions Oscar must make

| Decision | Recommendation | Cost of deciding late |
|---|---|---|
| **`helicon ci`: Option A (persistent store) vs B (honest ~5-class cold exam)** (PRODUCT.md:148 — all four takes cite the 1-of-13 structural fact; none ruled) | **B.** The history classes belong to the suite surface where a store accumulates; `ci` stays the honest cold exam. | Every new class worsens the honest cold count; PRODUCT.md:152 already bans expansion until answered. Blocks H2.1's framing. |
| **Desktop shell** (proposal's one open question) | **Arch's Option B wins over ambition's "defer":** `WKWebView` on `:8420` inside the existing Swift app (~1 day, zero duplication) — because the app already exists (4,065 lines, touched 08-18) and PRODUCT.md:46 currently states a falsehood the repo contradicts; correct the doc in the same pass. Ambition's sequencing survives: this binds at H3; the stranger path is CLI regardless (wedge agrees). | The Swift app drifts further behind and the doc rot compounds — the product's own named failure mode, standing in its own spec. |
| **Layer 2: feed or delete.** "Learns how the human reviews" has a training set of 4 human rulings, 3 from one day five weeks ago (skeptic §2). | Tie to K2: if <10 human rulings by 17 Sept, delete the learning layer rather than ship decoration. | Every week of "wired but dormant" is maintenance-mode debt on the differentiator claim in CLAUDE.md line 2. |
| **Axis-1 exposure gate.** Show the trend to strangers before or after the Goodhart answer (H2.8)? | After. The only recorded history is a self-awarded 53-point jump; shipping that pattern to strangers reproduces the exact failure arXiv 2606.01435 warns about, in the tool that cites it. | A stranger's first trend line is gameable by the tool's own cron — and a debunked score kills the card's credibility permanently. |
| **The n=1 dot.** Skeptic: "a trend with n=1 is a dot," build nothing on axis 1 yet. | **Skeptic loses as a blocker:** Oscar already ruled axis 2 works day one while axis 1 accrues (proposal :56), and the UI states "trend begins with the second reading" honestly. H1.4 makes the dots accumulate unattended. | None — resolved; recorded so it is not re-litigated. |

## The skeptic's surviving objections (not resolved away)

1. **Demand may simply be absent.** cc-health-check archived at 0 stars; Excellence Audit at 5 stars, 0 forks — two people shipped this idea free and nobody came. The counter (both were shape-checkers with no receipts, no citations, no trend; the sharing culture is real and unscored) is a *bet*, testable only by K3/K4, not by launch-post upvotes. (skeptic §2; wedge's own honest read — kept unsoftened.)
2. **The maximally motivated user does not use it.** Ingestion is on a cron and healthy; every human-in-the-loop surface is cold — 4 human rulings, 1 snapshot, 28 retrieval-log rows, consolidation dead since 05 Jul. A self-improvement tool whose author supplied less engagement than it asks of strangers has its premise falsified on the only installation in existence. H1.4 automates the snapshots — which *masks* this objection rather than answering it; only K2/K5 (acts automation cannot fake) answer it.
3. **The window is not infinite.** agnix (387 stars, 448 rules, seven harnesses) can compose a score in a weekend; `/insights` already produces the analysis and needs only a number — first-party, zero-install, universal distribution (skeptic §3). What survives all three competitor scenarios: the receipts-based rot probe and personal-store content quality — which is why H2 is the moat horizon and must not slip.
4. **Migration risk is unhandled.** 47 tables (live DB; repo DBs show 32 — the takes probed different DBs, both correct), ad-hoc imperative migrations, no `schema_version`, no test on the upgrade path a real 0.1→0.2 user takes (skeptic Risk 2). Unscheduled in all three horizons; it fires the first time a stranger upgrades.

## Kill criteria

Adopted from the skeptic near-verbatim — each is a number a stranger can check with `sqlite3`:

| # | Check | Kill threshold | Date |
|---|---|---|---|
| K1 | `count(*) from setup_snapshots` | < 4 | 2026-09-17 |
| K2 | human rulings (`session_id like 'cli-human%'`) | < 10 (now 3) | 2026-09-17 |
| K3 | named strangers who ran it and reported output | 0 | 2026-09-30 |
| K4 | strangers who ran it a **second** time, ≥7 days later, unprompted | 0 | 2026-10-31 |
| K5 | `max(created_at) from consolidations` | still 2026-07-05 | 2026-09-17 |
| K6 | `/insights` ships a setup grade, or agnix ships a score | shipped | any |
| K7 | Setup surface on `main` + post-fix version on PyPI | still false | 2026-08-27 |

**Caveat on K1** (synthesis, not in any take alone): H1.4 automates snapshots, so K1 can pass by cron — it remains a data-existence check only. **K4 is the demand kill automation cannot game**; it is the number that separates this from the two dead repos. K6 narrows the roadmap to the two survivors (receipt-based rot probe; personal-store content), never kills them. **Composite kill:** K1+K2+K5 all failing on 17 Sept means zero users including the owner — then cut to the one thing that ever produced an external artifact (the `openai/codex` finding, precision 1-of-1) and ship it as the listed GitHub Action, the only board item whose done-when involves a human who is not Oscar (skeptic §5 — kept as the kill *outcome*, not a plan branch).