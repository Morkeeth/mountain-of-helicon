# The state of agent context — August 2026

**Question.** Of the public repositories that ship an agent-rules file
(`CLAUDE.md` / `AGENTS.md` / `.cursorrules`) at their root, what fraction contain
claims their own code disproves — where "disproves" means *an executed command,
not an opinion*?

This is not a benchmark scored against a model's own conversation (LOCOMO,
LongMemEval, STALE, PersistBench). Every verdict here is produced by a command
that runs against the repository's real tree, and every number below carries the
command and its real stdout. `UNVERIFIABLE` is a verdict, not a gap.

**Accuracy is the headline, not a footnote.** The naive contradiction rate over
this corpus is **26.6%**. Hand-verification shows **~90% of that is false
positives**. This report is mostly the story of measuring that gap honestly,
fixing the two largest false-positive classes at the source, and reporting what
survives — with the sampled precision printed next to every rate.

---

## Headline (all numbers hand-verified)

- **Corpus:** 591 public repos discovered via the GitHub code-search API;
  **576 scored** (11 had no root rules-file once cloned, 4 failed to clone).
- **Naive probe:** 153 / 576 repos flagged = **26.6%**, 651 findings. A random
  sample of 35 was **false-positive-dominated**.
- **After fixing the two dominant false-positive classes** (a filename *mentioned*
  is not a filename *claimed present*; a *negation* is not an existence claim):
  36 / 576 repos flagged = **6.25%**, 100 findings.
- **Path-kind findings, exhaustively hand-verified (all 47):** **16 are genuine
  doc-vs-code contradictions → precision 16/47 = 0.34.** These fall in **10 of
  576 repos = 1.74%**.
- **Kill-switch / HTTP-410 "retired-capability" findings:** sampled precision
  **1/15 = 0.07 — excluded from every rate above** (see *Excluded class*). `410`
  is ubiquitous in normal code (retry-code arrays, coordinates, spec IDs,
  comments), so this kind is currently noise on arbitrary repos.

> **The finding.** Executable doc-vs-code contradiction in public agent-rules
> files is **real but rare** — on the order of **~1.7% of repos** carry a claim a
> single `git` command disproves — and it is **far rarer than a naive probe
> reports**. The gap between 26.6% and 1.7% is itself the result: pointing an
> executable checker at the open world without precision discipline manufactures
> contradictions. A low rate, honestly measured, is still the finding.

---

## How to reproduce

The engine is `helicon sweep`. It clones each repo shallow into a temp dir, runs
the same per-repo gate the doorway uses (`helicon.doorway.verdict`, reused as-is —
there is no second probe path), and throws the clone away. Concurrent, per-repo
timeout, nothing written back to any clone.

```bash
pip install -e .
# the exact corpus this report used (frozen list committed in the repo):
helicon sweep --from bench/corpus/agent-context-2026-08.txt --jobs 16 --timeout 60 --save out.json
```

**The corpus is reproducible by a stranger.** `bench/corpus/agent-context-2026-08.txt`
is the frozen, resolved list of 591 `owner/name` repos. It was built from the
GitHub code-search API on the date recorded in that file's header, with these
queries (results drift as GitHub re-indexes, which is why the resolved list is
committed rather than the query alone):

```bash
gh api -X GET search/code -f q='filename:CLAUDE.md path:/'   --jq '.items[].repository.full_name'
gh api -X GET search/code -f q='filename:AGENTS.md path:/'   --jq '.items[].repository.full_name'
gh api -X GET search/code -f q='filename:.cursorrules path:/' --jq '.items[].repository.full_name'
# then: sort -u
```

---

## Honest denominators

| Repo outcome | Count | Counted in the rate? |
|---|---:|---|
| Scored (cloned, had a root rules-file, probes ran) | 576 | **yes — this is the denominator** |
| No rules-file at root once cloned | 11 | no (nothing to check) |
| Clone failed (renamed / deleted / private since indexing) | 4 | no (unreachable) |
| **Corpus total** | **591** | |

Within the 576 scored repos, the distribution of *path-kind* findings after
hardening: 552 repos have 0, and 24 repos carry at least one — of which 10 hold a
finding that survived hand-verification.

---

## Accuracy: the false-positive classes, found and fixed

Dogfooding the gate on Helicon's own repo earlier this cycle had already found
two false-positive classes (a committed fixture read as running code; "git
tracks no such file" read as disproof), pinned in
`tests/test_probes_false_positives.py`. The public sweep exposed a **third and
dominant one**, plus a class that is not cheaply fixable and is therefore
excluded.

### Fixed — class 3: a filename *mentioned* is not a filename *claimed present*

92% of the naive sweep's findings were `named-path-gone`, and most were wrong.
The path probe fired on **every** backticked filename in **every** sentence, so
these all manufactured a contradiction:

- a schema subject — *"Each fact in `items.json` follows this schema:"*
- a generated file — *"Generates `graph.json` from the source code."*
- an example — *"e.g., `foo.ln.json` in the home directory."*
- a template/placeholder — *"create a new changelog file `2024-10-13.md`"*
- a **negation** — *"there is no `.eleventy.js`"*, *"No `karma.conf.js`"*
- a relative-escape token — *"`../frontend/lib/abi/generated.ts`"*

**Fix (in `helicon/probes.py`, extended not rewritten):** the path probe now
fires only when the sentence *asserts the file is present* ("lives in", "the
entry point is `x`", "defined in `x`", "see `x`") and there is no negation /
example / generation cue, and the token is not a relative-escape or glob.
Regression tests added in `tests/test_probes_false_positives.py` (class 3). This
change also makes the live doorway gate more precise, not just this report.
Effect on the corpus: path findings fell from **598 → 47**.

### Excluded — the kill-switch / HTTP-410 class

`retired-capability-advertised` fires when the code enforces a retirement (an
HTTP `410`, a `*_RETIRED` switch) that a doc still advertises. On Helicon's own
narrowly-scoped fixtures it is a true positive. On arbitrary public repos its
sampled precision is **1/15 = 0.07**, because `410` and disabled-flag constants
are ordinary code:

```text
$ git grep -n -- "410" tools/bedwindow/pkg/bedwindow/parity_test.go
  parity_test.go:60:  t.Errorf("n = %d, want 1 (A window expanded to [200,410))", n)   # a coordinate
$ git grep -n -- "410" client/static/services/pollService.js
  pollService.js:20:const UNRETRYABLE_CODES = [400, 401, 403, 404, 405, 409, 410, 422]  # a retry table
$ git grep -n -- "410" aida-core/src/scaffolding/codex_md.rs
  codex_md.rs:215:  environment: SPEC-410, BUG-339, ...                                 # a spec id
```

Per the discipline *"do not ship a number with a known-bad class in it,"* this
kind is reported here but **excluded from every published rate**. Hardening it to
open-world precision is future work, not this run.

### Disclosed — residual path false-positive classes (in the 31/47 that failed verification)

Not yet fixed; named so the 0.34 precision is honest and improvable:

- **multi-sentence mis-split** — the assertion splitter attaches a path token
  from an adjacent clause, so the probed path is not the one the sentence claims.
- **placeholder templates** — `objects/TYPE/000/SPEC-ID.yaml`,
  `ComponentName/ComponentName.tsx`, `/docs/rfcs/NNNN-short-name.md`,
  `YYYY-MM-DD-slug.md`: naming patterns, not files.
- **cross-repo references** — `PyAutoBrain/ORGANISM.md`,
  `credit-union-2-0-llc/cu2-platform (pool-tenants/broflo.json)`: the doc says
  the file lives in a *sibling* repo, and the checkout is not it.
- **user / tool config** — `.claude/launch.json`, "see `feedback_no_zhipu.md` in
  user memory": files that live at the user level, not in the repo.

---

## The verified contradictions

Aggregate rates are published by name; individual repos are shown only where the
evidence is unambiguous and framed as **"the doc and the code disagree"** — we
are measuring a systemic failure mode, not scoring strangers. Maintainers are
welcome to the per-repo detail. Every row below is a doc line that names a file
its own repository does not contain, proven by one command.

| Repo | Where | The doc says | The command | stdout |
|---|---|---|---|---|
| `hoangtruong01/HorseTrack` | `CLAUDE.md:9` | Read `MASTER_GUIDE.md` for the operating model | `git ls-files -- MASTER_GUIDE.md` | *(no output)* |
| `hoangtruong01/HorseTrack` | `CLAUDE.md:11` | Read `PORTABILITY.md` for copy strategy | `git ls-files -- PORTABILITY.md` | *(no output)* |
| `orbforge/sensorbox` | `CLAUDE.md:51` | entrypoint `asu/main.py` (FastAPI) | `git ls-files -- asu/main.py` | *(no output)* |
| `orbforge/sensorbox` | `CLAUDE.md:66` | Config lives in `www/config.js` | `git ls-files -- www/config.js` | *(no output)* |
| `DrakeDamon/Portfolio` | `AGENTS.md:5` | …config (`next.config.mjs`) | `git ls-files -- next.config.mjs` | *(no output)* |
| `Strategic-Cowork-Consulting/confidence-routed-extraction` | `CLAUDE.md:136` | FastAPI exception handlers live in `api/exceptions.py` | `git ls-files -- api/exceptions.py` | *(no output)* |
| `VarunDasharadhi/newsletter-demo` | `CLAUDE.md:16` | Read `workflows/scrape_website.md` | `git ls-files -- workflows/scrape_website.md` | *(no output)* |
| `jorgejr568/organizze-mcp` | `AGENTS.md:198` | Read `openapi.yaml` … it's the source of truth | `git ls-files -- openapi.yaml` | *(no output)* |
| `pvieito/CodeSignKit` | `CLAUDE.md:9` | Read `README.md` for architecture, targets, conventions | `git ls-files -- README.md` | *(no output)* |
| `pvieito/XCTestKit` | `CLAUDE.md:9` | Read `README.md` for architecture, targets, conventions | `git ls-files -- README.md` | *(no output)* |
| `limhaowei/prescription-manager` | `.cursor/rules/convex_rules.mdc:23` | HTTP endpoints are defined in `convex/http.ts` | `git ls-files -- convex/http.ts` | *(no output)* |
| `myadmin-plugins/mail-module` | `CLAUDE.md:109` | Read `CALIBER_LEARNINGS.md` for patterns | `git ls-files -- CALIBER_LEARNINGS.md` | *(no output)* |

Twelve verified sentences across ten repos. The most common shape is a
`CLAUDE.md` that instructs the agent to *read a guide the repository does not
contain* — the exact failure this product exists to catch, now measured in the
wild instead of asserted.

---

## Run the check on your own repo

```bash
pip install -e .
helicon sweep <owner/name-or-a-local-path>
```

One repo, one verdict, with the command and stdout behind every line. If it says
`CONTRADICTED`, the doc and the code disagree and the command is right there to
check us. If it says nothing, your agent-rules file and your tree still agree —
today.
