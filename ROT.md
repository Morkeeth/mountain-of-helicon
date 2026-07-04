# The Memory-Rot Catalogue

Agent memory fails in repeatable ways. This catalogue names the failure classes,
grounds each in documented public evidence, and maps each to the Mount Helicon
check that catches it — or honestly says none does yet. The origin story: four of
these failures happened in the author's own agent stack in a single day
(2026-07-04), and this repo's checks scored 1 caught / 3 missed on first contact.
Two misses were fixed the same night. That loop — incident → check → never twice —
is what "CI for agent memory" means.

Status per class: **TESTED** (a shipping check covers it) · **PARTIAL** (detector
exists, selection/coverage gap) · **GAP** (no check yet; on the roadmap).

| # | Failure class | What happens | Real instance (this repo's stack) | Helicon check | Status |
|---|---|---|---|---|---|
| R1 | **Cross-source contradiction** | Two sources disagree on a fact; the agent confidently serves one — often the wrong one | Two files disagreed on a birthday (Jul 13 vs Jul 18); a daily agent brief repeated the wrong date for 5 days | Battery `Contradiction` (Qwen-judged) + factual audit. Detector confirmed the real pair `critical`; production pairing across sources is the gap | **PARTIAL** |
| R2 | **Doc-drift** | Docs assert numbers/facts the source contradicts; agents read docs as truth | This README claimed 8 MCP tools while source had 11 | `helicon.docdrift` — README claims vs source counts, runs in pytest, stale docs fail the build. Caught itself 4 times in 24h | **TESTED** |
| R3 | **Staleness / expiry** | A time-boxed artifact (plan, status, priority list) outlives its validity and is reused as current | A 6-day-old execution plan was pasted into a fresh session and rebuilt yesterday's priorities | Weibull decay (runs on every scan) + battery `Expiry` (retrieved cube past its type's half-life) + `Freshness` (killed/decayed cubes served) | **TESTED** |
| R4 | **Supersession by rename** | An entity is renamed/replaced; the old name lives on across memory and docs | A project rename left 710 live memory items referencing the dead name | `reconcile` retires content that disappeared from sources; renamed-entity propagation (old name in *current* claims vs history) is the gap | **PARTIAL** |
| R5 | **Duplicate/echo memory** | The same fact stored N times crowds the context window and amplifies itself | Retrieval returned 2 identical trip-note cubes for one query | Battery `Redundancy` + ingest novelty gate (ADD/NOOP/MERGE) + consolidation | **TESTED** |
| R6 | **Title-only grounding** | Retrieval serves titles/metadata instead of decisions; verdicts sound informed but carry nothing | Ops battery run returned "titles, dates and high-level metadata tags rather than concrete verifiable statements" | Battery `Grounding` (Qwen-judged) + `Thinness` | **TESTED** |
| R7 | **Wrong eviction (regret)** | Aggressive forgetting kills memory that was still needed | 2 auto-triage kills were wanted back by retrieval within days | Regret ledger: ghost-list matching (LeCaR), time-decayed regret events blaming the exact kill decision | **TESTED** |
| R8 | **Retrieval regression** | An index/data/model change silently changes what a task retrieves | 4 of 13 benchmark tasks regressed vs baseline on first snapshot capture | `helicon snapshot add/check` — CI-style regression on retrieved context | **TESTED** |
| R9 | **Self-generated evidence loops** | A system learns rules from its own outputs and reinforces its own mistakes | An early triage rule's evidence was ~88% self-generated | Human-evidence guard: `auto-triage`, `agent-flag`, `rule:%` sessions excluded from all learning | **TESTED** |
| R10 | **Instruction-file drift** | Agent rules files (CLAUDE.md, .cursorrules, AGENTS.md) drift from reality; agents obey stale law | 20 retired sections detected across live rules files on first reconcile | Rules files split into section-level cubes; snapshot + reconcile cover them | **TESTED** |

Public evidence per class (research citations, lab statements, GitHub incidents)
is being compiled and will extend this file — every class above already has
documented instances beyond this repo's own stack.

## The loop

```
incident happens → becomes a check → check runs on every scan/report → never twice
```

Run the catalogue against your own stack: `helicon scan && helicon report`.
