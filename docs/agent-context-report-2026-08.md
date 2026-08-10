# The state of public agent context — verified 2026-08-09

## Question

Of the public repositories in the frozen corpus that still ship a root
agent-rules file, how many contain a path claim their current default branch
disproves?

“Disproves” means a concrete instruction points to repository content, the exact
command returns no path, and human context review finds no template, negation,
generated output, submodule, sibling repository, user-level path, or other
reasonable interpretation. An arguable row is FALSE.

## Headline

- **Input:** 591 unique `owner/repo` names.
- **Scored:** 577.
- **Excluded:** 14, named below.
- **Mechanical survivors:** 30 rows in 25 repositories.
- **Hand-verified TRUE:** 9 rows in 6 repositories.
- **Independent maintainer situations:** 5 (`CodeSignKit` and `XCTestKit` share
  one owner and the same symlinked instruction blob).
- **Finding precision:** 9 / 30 = **0.30**.
- **Verified repo prevalence:** 6 / 577 = **1.04%**.

The launch-safe result is therefore:

> Six of 577 scored public repositories contained an agent-context path claim
> that was false on the current default branch and sendable to the maintainer
> with executable evidence: **1.04%**.

This is a dated measurement of one corpus and one checkable failure class. It is
not a claim about all repositories or all forms of stale agent context.

## Exact run

```bash
python3 -m helicon sweep \
  --from bench/corpus/agent-context-2026-08.txt \
  --jobs 16 \
  --timeout 60 \
  --save scorecard.json
```

Measurement code includes:

- `01ceebc` — bind a probe to the assertion that earned it, not every sentence
  sharing the physical Markdown line;
- `800fc56` — scorecard-wide invariant: if a finding's own output names an
  existing file, do not publish it;
- `0ebb8e4` — repair four frozen-corpus lines contaminated by concatenated GitHub
  429 JSON while preserving 591 unique repository names.

The reduced per-repository machine receipt from that run is committed at
[`bench/results/agent-context-scorecard-2026-08-09.json`](../bench/results/agent-context-scorecard-2026-08-09.json).
It preserves all 591 statuses and all mechanical findings without temporary
clone paths.

The run completed with **no timeouts**. That is what happened tonight; no timeout
count is borrowed from a different run.

## How the measurement moved, with named causes

| Stage | Scored | Flagged repos | Rows | Named cause |
|---|---:|---:|---:|---|
| Current-main baseline | 573 | 27 | 53 | 18 assertion-projection duplicates; 5 output-names-existing-file rows; four malformed corpus entries |
| Assertion projection fixed | 573 | 27 | 35 | Exactly 18 duplicate rows removed; no repo changed status |
| Publication invariant fixed | 573 | 25 | 30 | Five wrong grep rows removed from two repos |
| Frozen corpus repaired | 577 | 25 | 30 | Four real repo names recovered from GitHub 429 contamination |
| Hand verification | 577 | 6 TRUE | 9 TRUE | 21 arguable/wrong rows rejected by named cause |

No rate changes without a row-level cause.

## Why the 18 duplicates existed

They were not repeated imports and not repeated probes.

Long Markdown paragraphs often contain several logical sentences on one physical
line. `probe_docs` correctly ran one path probe for the one sentence that named
the path. `doorway.repo_detail` then indexed that result by `(file, line)` and
assigned it to every sentence sharing the line. One raw probe became five
published rows.

The fix keys results by exact assertion. A line-level fallback is allowed only
when one assertion owns that physical line. Regression coverage reproduces five
rows from one probe and requires one published finding.

## Publication invariant

The strict path-glob branch already declined to publish when
`git ls-files -- */path` printed an existing file. Five rows escaped through
other probe shapes: their own `git grep` output began with an existing source
path.

The invariant now lives at the scorecard boundary:

> A finding whose own probe output names a file that exists in the checked
> repository is never published as a contradiction.

The regression test covers basename output, non-git path output, and grep output
in one scorecard, and separately proves that a genuinely absent path with
`(no output)` still publishes. Precision was gained by dropping wrong rows, not
by weakening the definition of a finding.

## Exact exclusions

The authoritative run excluded **14**, not 13. The expected
“3 timeouts / 8 clone failures / 2 no-rules” split did not occur on this run and
is not reported as if it did.

### Clone failed — 3

1. `WebSurfinMurf/openproject` — repository not found.
2. `al-siv/score68` — repository not found.
3. `invincible-jha/aumai-specs` — repository not found.

### No root rules file on the current default branch — 11

1. `GOVINSAGA/gobblecube-eta-challenge`
2. `MattKilmer/claude-autofix-bot`
3. `Shlomob/ocmonitor-share`
4. `VASST/PVAC`
5. `WaveringAna/wisp.place-monorepo`
6. `alexeygrigorev/ai-data-pipelines`
7. `charyou/SoraVault`
8. `emdmed/terminal-notes`
9. `erent8/Advanced-Customer-Detection`
10. `nwbort/accc-mergers`
11. `ven0m79/dm-project`

These are exclusions, never clean repos and never part of the denominator.

## Verified TRUE rows

| Repo | Doc:line | Claim | Command | Output |
|---|---|---|---|---|
| `hoangtruong01/HorseTrack` | `CLAUDE.md:9` | Read `MASTER_GUIDE.md` | `git ls-files -- MASTER_GUIDE.md` | `(no output)` |
| `hoangtruong01/HorseTrack` | `CLAUDE.md:11` | Read `PORTABILITY.md` | `git ls-files -- PORTABILITY.md` | `(no output)` |
| `hoangtruong01/HorseTrack` | `AGENTS.md:9` | Read `MASTER_GUIDE.md` | `git ls-files -- MASTER_GUIDE.md` | `(no output)` |
| `hoangtruong01/HorseTrack` | `AGENTS.md:11` | Read `PORTABILITY.md` | `git ls-files -- PORTABILITY.md` | `(no output)` |
| `Strategic-Cowork-Consulting/confidence-routed-extraction` | `CLAUDE.md:136` | Exception handlers live in `api/exceptions.py` | `git ls-files -- api/exceptions.py` | `(no output)` |
| `jorgejr568/organizze-mcp` | `AGENTS.md:198` | `openapi.yaml` is the source of truth | `git ls-files -- openapi.yaml` | `(no output)` |
| `myadmin-plugins/mail-module` | `CLAUDE.md:109` | Read `CALIBER_LEARNINGS.md` | `git ls-files -- CALIBER_LEARNINGS.md` | `(no output)` |
| `pvieito/CodeSignKit` | `CLAUDE.md:9` | Read `README.md` | `git ls-files -- README.md` | `(no output)` |
| `pvieito/XCTestKit` | `CLAUDE.md:9` | Read `README.md` | `git ls-files -- README.md` | `(no output)` |

Every SHA, full claim, command, output, TRUE/FALSE decision, and reason for all
30 mechanical survivors is recorded in
[`agent-context-verification-2026-08-09.md`](agent-context-verification-2026-08-09.md).

## The three maintainer messages

These survived a second independent clone and context review.

### HorseTrack

`CLAUDE.md` and `AGENTS.md` direct agents to `MASTER_GUIDE.md` and
`PORTABILITY.md` as operating sources. At `3ee8c1f`, both
`git ls-files -- MASTER_GUIDE.md` and `git ls-files -- PORTABILITY.md` return no
path; please restore those guides or update the references.

### confidence-routed-extraction

`CLAUDE.md:136` says FastAPI exception handlers live in `api/exceptions.py`, but
that path is not tracked at `178a7c3`. The handlers are implemented in
`src/extraction/api/main.py`; please update the instruction to point contributors
to the existing module.

### organizze-mcp

`AGENTS.md:198` tells contributors to read `openapi.yaml` before adding wire
fields, but that file is not tracked at `bde178e`. Please add the specification
or a reproducible retrieval step, or update the guidance to its canonical source.

## The 21 rejected rows

| Cause | Rows |
|---|---:|
| Generated runtime/analysis output | 2 |
| Path scoped to a git submodule | 3 |
| Explicit peer-repository path | 1 |
| Filename/path template | 4 |
| Generic framework/example guidance | 2 |
| Negation or intentional absence | 4 |
| User-level or environment-specific path | 3 |
| Installer-owned basename | 1 |
| Guidance about consumer repositories | 1 |
| **Total FALSE** | **21** |

Examples include `NNNN-short-name.md`, `YYYY-MM-DD-slug.md`, “No
`karma.conf.js`,” a file explicitly “in user memory,” and paths that exist inside
pinned submodules. None are findings.

## Reproduction and review standard

1. Run the frozen corpus command.
2. Preserve every repo status; exclusions are named.
3. For each survivor, clone the current default branch and record its SHA.
4. Rerun the exact command.
5. Read surrounding context and search for templates, generation, submodules,
   sibling repositories, user paths, negation, and history.
6. If two defensible sentences cannot be sent to the maintainer, mark it FALSE.

This report measures what survived that process, not what made the page
interesting.
