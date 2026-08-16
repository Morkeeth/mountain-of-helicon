# The weekly review

**Once a week, one page tells you whether your setup is any good, and every line on it is
something you can rule on.**

Every other surface in this repo answers a question about one thing: is this memory stale, does
this rule still hold, did this claim survive a probe. The weekly review asks the question none of
them can, because it is a question about the *week*: given everything the stack did, is the way it
is set up working.

---

## The cadence is the product

| | ZUP | The weekly review |
|---|---|---|
| Frequency | daily | weekly |
| Question | what is next | is my setup any good |
| Unit | a task | a defect in how the stack behaves |
| Success | the queue is clear | you ruled on something and the stack changed |

That table is not a preference. Five separate rebuilds collided over what ZUP was, and every one
of them was really an argument about frequency: a daily surface and a weekly one were being asked
to live in the same tool. Assign the frequencies and the collision stops.

**If the weekly review needs clearing, it has failed.** A queue is the daily tool's shape.

---

## The gate

> A finding earns its place only if **ruling on it would change how the stack behaves.**
> A number that is merely true does not qualify.

This gate took the finding queue from 449 to 6 in one pass. The 443 it removed were not wrong —
they were true observations about May status files containing the word "today", and no ruling
followed from any of them. Meanwhile the six that survived included one that had been sitting under
the pile: on the day five rebuilds were argued about what ZUP is, the stack already knew ZUP was
defined three incompatible ways across three sources. It had computed that and nobody could see it.

**The pile is the failure. Not the miss.**

---

## What a measurement is

> A measurement is a number, **the command that reproduces it**, and **the moment it was read.**

Not "the command that produced it" — that phrasing is incoherent for a derived finding. R11 was
computed during a scan that ended hours ago; no command produces it now. What a reader needs is the
command they can type to see the same number themselves, and when the number on the page was read.

A number without both is a claim with an author.

---

## THE STANDING RISK

**This product's failure mode is not missing a finding. It is rendering one persuasively and
wrongly.**

A review surface that misses a defect leaves you where you started. A review surface that shows you
a defect, cites a source, and gets the attribution wrong moves you backwards — because you rule on
it, and the ruling becomes canon.

The grounding instance is in this repo. R11 correctly found that `zup` was defined three
incompatible ways across three sources. The evidence card that rendered it ran through the pair
renderer, which is pair-shaped: two values, two lines, two scopes. On a three-genus fork it:

- showed two of the three definitions, so the third source was invisible;
- printed the genus `exit` against the Obsidian file that actually says `owned`, because
  `value_b` and `scopes[-1]` are ordered independently and the labels crossed.

A human ruling from that card would have typed a canonical definition against a source that does
not say what the card claimed — and `resolve` writes an approved correction memory, so the wrong
ruling would then be served as the settled answer. The finding was right. The card made a wrong
ruling look sourced.

**Every surface in the weekly review carries this risk, and every one of them is on the same
hook:**

1. Show the whole population, not the first two members of it. A card that renders N of M sides
   without saying so invites a ruling on a fraction of the evidence.
2. Never pair a value with a source by position. Two independently-ordered lists look aligned and
   are not.
3. A placeholder where a number goes (`(? memories)`) is worse than no number.
4. State the population every finding was computed over, and what share of it was unattributable.
   A per-author rate over 70% of the log is a different number from a per-author rate.
5. If a quote cannot be recovered for a source, say so. A blank line under a source path reads as
   "this source is silent", which is a different claim.

### The trap every new detector falls into

**A detector built to replace the pile will rebuild the pile inside itself, and it will look like
it is working while it does.**

This has now happened four times, once per detector, and it was caught each time only by running
the thing against real data and reading the output:

- **The scatter detector** grouped documents by basename and reported `SUBMISSION.md` across seven
  hackathon repos. Every row was true. Seven projects each writing their own submission doc is how
  projects work, and there was no ruling to make on any of it — the 449-finding pile, rebuilt
  inside the detector meant to replace it, on its first run.
- **The scattered-homes detector** reported `fleet` matching eight directories, four of which are
  deliberately separate experiments. True, and a candidate at best, rendered as confidently as a
  near-certain finding.
- **The learning ledger** graded fourteen learnings as having an artifact behind them, and nearly
  every hit was one file: the script that *backfilled the catch log*. It contained the checks
  because it had written them down. The log vouching for itself — R9, self-generated evidence,
  reproduced inside the detector built to catch unenacted rules.
- **The rule ledger** graded thirteen rules WIRED on the token `helicon` — the repo's own name,
  which appears in every workflow file. Among them: "~3,800 live memories of ~6,900 total", a
  statistic that no gate could enforce, presented as a governed rule. Fixed with a document-frequency
  filter computed over the corpus being searched, because the hand-written stoplist that would have
  been the obvious fix could never have contained the project's own name in advance.

The pattern is the same each time: **the detector found the thing it was searching for, and the
thing it was searching for was not the defect.** A shared basename is not a shared document. A
shared word is not a shared object. Containing a rule is not enacting it.

So the standing requirement for any detector added here:

- Run it on the real population and READ the output before believing the count. A detector is not
  finished when its tests pass; its tests only encode what its author already thought of.
- Keep a noise fixture next to every signal fixture, and assert both. The precision test is the
  one that earns the detector its place.
- When output is dominated by one source, one name, or one shape, that is the tell. Ask what the
  detector is actually matching on before tuning the threshold.

---

## The five features

Build order is fixed. It runs cheapest-and-already-computing first, and puts the one that needs an
external receipt last.

### C · Identity coherence — BUILT
One entity defined incompatible ways across sources. R11 and R1 already compute it; the work was
surfacing. See `helicon.identity.format_identity_evidence` and `helicon resolve --list --cards`.

*The week's line: "your stack disagrees with itself about what four things are."*

### A · The overboard detector — BUILT
Aggregate-only defects: the ones that are invisible on the day and obvious across a week. Every
reassignment, rename and duplicate was locally defensible when it happened. The defect exists only
in aggregate, which is exactly what a weekly window sees and a daily surface cannot.

**Five detectors, and the split between them is who can run them.**

| Detector | Source | A stranger has it |
|---|---|---|
| Git churn | `git log`, `git branch` across a repo set | **yes, day one, no config** |
| Drifted duplicates | files under the code root | **yes** |
| Scattered homes | directory names under the code root | **yes** |
| Lane churn | `*-lanes.jsonl` | no — one operator's format |
| Self-catch blindness | `catches.jsonl` | no — see below |

Git churn asks the same question as lane churn from a source everyone carries: branches merged into
the default branch and never deleted, unmerged work untouched for two weeks, and repos touched on
exactly one day in the window. Each was defensible when it happened; in aggregate the repo has a set
of addresses that all look live and mostly are not.

**Self-catch blindness stays operator-only, and that is a finding about the data, not a gap in the
build.** It needs a log of errors *with authors*. Git records work, not caught mistakes, so there is
no stranger-side equivalent to re-point it at. Forcing one would mean inventing an error log from
commit messages, which is a number with an author wearing a measurement's clothes.

See `helicon.overboard` and `helicon overboard`.

*The week's line: "you moved every terminal three times and nobody noticed until you did."*

### B · The learning ledger — BUILT
Every learning from the week, and whether anything can act on it. Four tiers: PROSE (no command),
STATED (a command in the log and nowhere else), STAGED (an artifact exists, no live config reaches
it), WIRED (a live config names the artifact — execution still unverified).

Measured on the real log: 37 learnings, 30 carrying a check, **0 WIRED**. The week's single best
learning had a real script *and* a prepared settings diff, and the live config referenced neither.
A diff is a proposal; a proposal is not an installation.

**`helicon ledger --rules <repo>` needs no catch log and no configuration.** It reads the rules a
repo already states (CLAUDE.md / AGENTS.md / .cursorrules) and grades them against the enforcement
surfaces the repo already has: GitHub workflows, installed git hooks, package scripts, pre-commit
configs, Makefiles. Every one of those is a file a stranger has on day one.

**On R14 — the boundary as first written was wrong, and re-pointing is what made it wrong.** The
original note here said "different populations, no collision." Once `--rules` reads CLAUDE.md and
AGENTS.md, the population is *identical* to R14's. The honest statement is:

> **Same population, different question.** `helicon.inert` (R14) asks whether anything ever
> *mentioned* this rule — a rule nothing references is dead, and the ruling is to delete it. The
> ledger asks whether anything would *stop the rule being broken*. A rule can be mentioned all over
> a codebase and still have no gate, and then it is alive, obeyed by hand, and one tired afternoon
> from being broken silently.

Because the population is identical, the rule extraction is **imported** from `helicon.inert`, not
rewritten. Two extractors over one population drifting apart is an R11 identity fork with this
module as its author, and shipping one inside the tool that detects them would be the joke writing
itself. A test asserts the import.

Known limit, inherited deliberately: `_rule_lines` treats every stated line in an instruction file
as a rule, so a statistic (`Composite: ~67`) is graded alongside a real rule. Fixing that here would
fork from R14. It belongs in R14 or in neither.

See `helicon.ledger`, `helicon ledger` (catch log) and `helicon ledger --rules` (any repo).

*The week's line: "you wrote three process documents. Zero of them ran."*

### E · The transcript reader — NOT BUILT
What actually happened, read from transcripts, against what the documents claim. This is the
feature that catches the coordinator: a relay of "preflight passed" when it had exited 1 with 7
flagged paragraphs is in no document. Only the transcript holds it.

Overlaps B deliberately: B asks whether words became actions, E asks whether the report matched the
run.

*The week's line: "your coordinator reported three numbers wrong this week. Here they are."*

### F · Restated assertion — THE KNOWN GAP, NOT BUILT
**A number restated away from the object that grounds it.** The third shape of scatter, and the one
the other two detectors cannot see.

A ships as *drifted duplicates* (one document, several homes) and *scattered homes* (one object,
several directories). Neither catches this: the document exists once and the object has one home.
What is duplicated is the **assertion**.

The grounding instance is a false claim made in this project's own brief. It said "six drifted
copies of one prize ledger". The ledger exists exactly once — `helicon overboard` scanned 2124
files and found no duplicate, and that refutation is what exposed the real defect. What existed six
times was the ledger's *numbers, restated*: in `cv-forge/context/bullets.md`, in
`GROKBOT-CV-SOURCE.md`, in `claude/mistral-pm-studio.html`, in the eval run JSONs, and — worst —
in a build-time guard in `paris-portfolio`'s `data.ts` whose error message asserted "canonical team
total is 41.7", a third value, inside code written to prevent exactly this drift.

The measured spread: 8 vs 9 categories, 17 vs 20 vs 22 prizes, 39.05 vs 41 vs 41.7, and $176K in
nine render sites.

**The detector:** a distinctive number appearing in N files where only one is the source. Harder
than the other four and worth more. It is named here rather than built so that the gap is a known
gap, not a silent one.

Note on populations, since this gap was found by disagreeing about one: the scattered-homes
detector scans `code_root` only. On `~/CODE` the SLASK object has 2 homes; across `$HOME` it has 4
(`~/SLASK™️`, `~/SLASK-phone`, `~/CODE/slask-eval`, `~/CODE/cursor-slask`). Both numbers are
correct on their own population and neither is correct without it. **Print the population with the
count.**

### D · Cost per outcome — NOT BUILT, AND BLOCKED ON HONESTY
Tokens against what reached a person. **Blocked on a receipt, not on code.** Every token count
available today is self-reported. A cost-per-outcome number built on self-report is the exact
defect this product exists to catch. Find a real receipt or do not ship the number.

---

## What it is not

- **Not a daily queue.** If it needs clearing, it has failed.
- **Not a memory store.** The product is the rot exam — R1 through R15 — which judges whether a
  setup is any good. That is the part nobody else has.
- **Not a dump.** Five features, one page, read once a week in a few minutes.

## The output shape

One page, once a week, that a human reads and rules on. One item on screen, the count left, rule
it, leave it open. `helicon resolve --list --cards` is that shape for C; `helicon overboard` is it
for A.
