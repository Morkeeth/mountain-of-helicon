# The Memory-Rot Catalogue

Agent memory fails in repeatable ways. This catalogue names the failure classes,
grounds each in documented public evidence, and maps each to the Mount Helicon
check that catches it — or honestly says none does yet. The origin story: four of
these failures happened in the author's own agent stack in a single day
(2026-07-04), and this repo's checks scored 1 caught / 3 missed on first contact.
Two misses were fixed the same night; the birthday pair (R1) got its selector
the next morning and now surfaces unprompted. That loop — incident → check →
never twice — is what "CI for agent memory" means.

Status per class: **TESTED** (a shipping check covers it) · **PARTIAL** (detector
exists, selection/coverage gap) · **GAP** (no check yet; on the roadmap).

| # | Failure class | What happens | Real instance (this repo's stack) | Helicon check | Status |
|---|---|---|---|---|---|
| R1 | **Cross-source contradiction** | Two sources disagree on a fact; the agent confidently serves one — often the wrong one | Two files disagreed on a birthday (Jul 13 vs Jul 18); a daily agent brief repeated the wrong date for 5 days | `helicon.pairing` — deterministic (person, topic, date) assertions across live cubes; disjoint intervals from two files = a candidate pair, Qwen detector rules on it, finding filed to the audit log on every `helicon report`. Found the real pair unprompted (6 vs 4 single-side asserters; cubes quoting both dates count as neither) | **TESTED** |
| R2 | **Doc-drift** | Docs assert numbers/facts the source contradicts; agents read docs as truth | This README claimed 8 MCP tools while source had 11 | `helicon.docdrift` — README claims vs source counts, runs in pytest, stale docs fail the build. Caught itself 4 times in 24h | **TESTED** |
| R3 | **Staleness / expiry** | A time-boxed artifact (plan, status, priority list) outlives its validity and is reused as current | A 6-day-old execution plan was pasted into a fresh session and rebuilt yesterday's priorities | Weibull decay (runs on every scan) + battery `Expiry` (retrieved cube past its type's half-life) + `Freshness` (killed/decayed cubes served) | **TESTED** |
| R4 | **Supersession by rename** | An entity is renamed/replaced; the old name lives on across memory and docs | A project rename left 710+ live memory items referencing the dead name | `helicon alias` — declared renames triage every dead-name ref by written rule: pre-rename = history (kept; retiring it would be R7), post-rename dead-name-only = current-claim rot, plus top-K leakage on current-name queries. First alias (glaze→helicon, UTC-normalized): 784 refs at the Jul 5 audit = 775 history + 9 rename-aware + 0 current-claims (recount moves with every scan) | **TESTED** |
| R5 | **Duplicate/echo memory** | The same fact stored N times crowds the context window and amplifies itself | Retrieval returned 2 identical trip-note cubes for one query | Battery `Redundancy` + ingest novelty gate (ADD/NOOP/MERGE) + consolidation | **TESTED** |
| R6 | **Title-only grounding** | Retrieval serves titles/metadata instead of decisions; verdicts sound informed but carry nothing | Ops battery run returned "titles, dates and high-level metadata tags rather than concrete verifiable statements" | Battery `Grounding` (Qwen-judged) + `Thinness` | **TESTED** |
| R7 | **Wrong eviction (regret)** | Aggressive forgetting kills memory that was still needed | 2 auto-triage kills were wanted back by retrieval within days | Regret ledger: ghost-list matching (LeCaR), time-decayed regret events blaming the exact kill decision | **TESTED** |
| R8 | **Retrieval regression** | An index/data/model change silently changes what a task retrieves | 4 of 13 benchmark tasks regressed vs baseline on first snapshot capture | `helicon snapshot add/check` — CI-style regression on retrieved context | **TESTED** |
| R9 | **Self-generated evidence loops** | A system learns rules from its own outputs and reinforces its own mistakes | An early triage rule's evidence was ~88% self-generated | Human-evidence guard, one written predicate (`db.human_evidence_sql`): `auto-triage`, `agent-flag`, `rule:%` and `seed%` sessions excluded from all learning (the Jul 5 audit caught 90 scripted seed reviews passing as human — quarantined same day) | **TESTED** |
| R10 | **Instruction-file drift** | Agent rules files (CLAUDE.md, .cursorrules, AGENTS.md) drift from reality; agents obey stale law | 20 retired sections detected across live rules files on first reconcile | Rules files split into section-level cubes; snapshot + reconcile cover them | R11 | **Identity coherence** | One entity's *definition* forks across sources — same name, incompatible genera (treasury vs tracker) — which R1's scalar-slot contradiction gate cannot see | "Yieldbound" forked into yield-treasury vs wallet-tracker across sources, silently, until a conversation exposed it | `helicon.identity` — reduce each article-gated defining clause ("X is a <genus>") to its head-noun genus; ≥2 incompatible genera across ≥2 source scopes = a fork. Deterministic genus tier + optional local-embedding semantic confirmation (drops same-concept rephrasings, cosine <0.45). Files to the audit log; resolve with the canonical definition | **TESTED** |
| R12 | **Phantom association** | A relation asserted between two entities that no source ever grounded — plausible, propagates, and no scalar/definition gate can see it | "Yieldbound rides the agent-payments wave → World" appeared in one idea note and spread as if established | `helicon.relations` — extract conceptual relation triples (narrow verb list; code keywords excluded) between capitalized entities; flag one asserted by a SINGLE speculative source (idea/draft/session) with NO independent corroboration (no other source co-mentions the pair). Files to the audit log | **TESTED** |

## Public evidence per class

The classes are not this repo's invention — they are the documented failure
record of the field. Selected evidence (papers, the labs' own docs, measured
numbers):

- **R1 cross-source contradiction** — GPT-4 acknowledges a conflict between
  two contradicting passages **6.3%** of the time unprompted, ~88% only when
  explicitly told to look ([WikiContradict, NeurIPS 2024](https://arxiv.org/pdf/2406.13805)) —
  the capability exists; nothing in production asks the question. Still true
  at the 2026 frontier: on real conflicting web references, GPT-4.1-class
  models recover under half of the conflicting viewpoints and explain **<16%**
  of the reasoning behind them, half the human score
  ([CONFRAG, ACL 2026](https://aclanthology.org/2026.acl-long.11.pdf)); even
  when a conflict is noticed, models fail to localize WHICH passages conflict
  ~half the time ([MAGIC, EMNLP 2025](https://arxiv.org/html/2507.21544v3)) —
  the pairing job this repo does deterministically. Which source wins is set
  by task framing and model certainty, not correctness: context-following
  swings **6-71%** by framing alone, replicated May 2026 on GPT-5.5, Claude
  Sonnet 4.6 and Gemini 2.5 ([Three Regimes, 2026](https://arxiv.org/abs/2605.11574);
  lineage: [ClashEval, NeurIPS 2024](https://arxiv.org/abs/2404.10198)). A
  wrong fact duplicated across files beats a right fact stated once
  ([Task Matters, 2025](https://arxiv.org/pdf/2506.06485)). Alibaba names the
  class "context conflict" ([AnalyticDB blog](https://www.alibabacloud.com/blog/is-your-ai-agent-getting-dumber-alibaba-cloud-analyticdb-unveils-ai-context-engineering_602803)).
- **R2 doc-drift** — appears in **zero** academic papers as a class (white
  space). Its ripple-effect cousin is measured: knowledge edits fail to
  propagate to entailed facts (MEMIT logical generalization **0.188**,
  [RippleEdits, TACL 2024](https://arxiv.org/pdf/2307.12976)).
- **R3 staleness/expiry** — best frontier model scores **55.2%** overall on
  knowing its memories are no longer valid ([STALE, 2026](https://arxiv.org/pdf/2605.06527));
  **64%** of memory-agent recommendation errors trace to outdated memory never
  forgotten, measured on GPT-5.2, Claude Sonnet 4.5, Gemini 3 Pro and
  Qwen3-32B over Mem0/LangMem/MemoryOS, penalty growing weekly→quarterly
  ([Memora, 2026](https://arxiv.org/html/2604.20006v1));
  49% effective accuracy after 30 days in independent production testing of a
  popular OSS store ([RankSquire, 2026](https://ranksquire.com/2026/05/06/long-term-memory-for-ai-agents/)).
  OpenAI's Agents SDK: *"Memory can become stale... treat memories as guidance
  only."* Anthropic's memory tool: expire by access time. Model Studio:
  memories have "no expiration date"; users should "periodically review and
  clean."
- **R4 supersession** — accuracy on superseded facts collapses **68% → 28%**
  as history grows 2→48 sessions, measured up to gpt-5.4; 24x more memory
  recovers zero points ([Supersede, 2026](https://arxiv.org/html/2606.27472)). LLM code completion
  uses deprecated APIs at **25-38%** ([ICSE 2025](https://arxiv.org/abs/2406.09834)).
- **R5 duplicate/echo** — "context confusion" in Alibaba's taxonomy; evidence
  frequency drives which fact wins (see R1), so duplicates amplify themselves.
- **R6 title-only grounding** — retrieval precision of **0.05–0.08** can look
  competitive on answer-level metrics; existing benchmarks can't see junk
  injection at all ([PrecisionMemBench, 2026](https://arxiv.org/html/2605.11325)).
- **R7 wrong eviction** — the inverse failure; cache literature measures it as
  miss-after-evict and learns from it ([LeCaR, HotStorage'18](https://github.com/sylab/LeCaR)),
  which is the mechanism this repo's regret ledger implements.
- **R8 retrieval regression** — one irrelevant sentence drops solve rates by
  double digits ([GSM-IC, ICML 2023](https://openreview.net/pdf?id=JSZmoN03Op));
  answer position alone moves multi-doc QA accuracy **30%+**
  ([Lost in the Middle, TACL 2024](https://arxiv.org/abs/2307.03172)).
- **R9 self-evidence loops** — one poisoned memory entry reaches **≥80%**
  attack success at <0.1% poison rate ([AgentPoison, NeurIPS 2024](https://arxiv.org/abs/2407.12784));
  the benign version is a triage engine grading its own decisions.
- **R10 instruction-file drift** — commercial assistants drop **30-60%** on
  long-term memory with knowledge updates ([LongMemEval, ICLR 2025](https://arxiv.org/abs/2410.10813));
  Qwen3.7-Max is marketed as *"resilient to context rot and instruction
  drift"* with no published way to verify it
  ([Qwen3.7 launch](https://www.alibabacloud.com/blog/qwen3-7-the-agent-frontier_603154)).

## In the wild — verified public incidents

Real, linkable issues (each fetched and verified 2026-07-04); the classes ship
in production today:

- **R1+R3, three weeks ago** — [mem0#5614](https://github.com/mem0ai/mem0/issues/5614)
  (Jun 17, 2026, closed "not planned" the NEXT DAY): a production financial
  agent burned by superseded earnings data asks for staleness detection,
  conflict detection and retrieval-quality metrics — this repo's feature
  list, requested by a user, declined by the vendor. Their words: *"memory
  quality failures are silent... an agent giving bad advice due to stale
  memories looks just like one giving good advice."*
  [mem0#5588](https://github.com/mem0ai/mem0/issues/5588) (Jun 16, 2026):
  memory TTL/expiry offered WITH a working PR — closed "not planned". And
  the vendor's own [State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
  (Jul 3, 2026) calls staleness "a harder, open problem."
- **R1** — [mem0#4536](https://github.com/mem0ai/mem0/issues/4536): "I love
  Chinese food" then "I hate Chinese food" → conflict resolver deletes BOTH;
  the agent now knows nothing. [claude-code#23769](https://github.com/anthropics/claude-code/issues/23769):
  partial memory summary contradicts project docs, corrections compound the
  corruption across sessions.
- **R2** — [claude-code#57200](https://github.com/anthropics/claude-code/issues/57200)
  (open): an infra decision never written back to the architecture doc; the
  next session's agent believed the doc and burned "days" re-deriving a
  settled decision. [python-genai#1606](https://github.com/googleapis/python-genai/issues/1606)
  (open, p2): every AI tool — including Google's own — keeps generating a
  deleted API; broken output scares devs off, so fresh correct examples never
  appear, so the training data stays wrong.
- **R3** — [mem0#4573](https://github.com/mem0ai/mem0/issues/4573): production
  audit of 10,134 memories found **97.8% junk**; a small model hallucinated
  "User prefers Vim" once and the pipeline re-extracted it from its own recall
  **808 times** — one lie laundered into the store's most confident fact.
  [letta#3146](https://github.com/letta-ai/letta/issues/3146): dashboard shows
  today, the prompt the model sees says yesterday — auto-closed with the label
  "stale". [claude-code#34776](https://github.com/anthropics/claude-code/issues/34776):
  a user describes 30 days of accumulating, contradicting, self-referential
  memories with no audit mechanism — closed "not planned".
  [Cursor forum#149416](https://forum.cursor.com/t/cursorrules-getting-ignored/149416):
  rules silently evicted mid-session; staff: "a known one".
- **R4** — [mem0#4896](https://github.com/mem0ai/mem0/issues/4896): "my name is
  LGY" → "my name is LGS" stored as two co-equal facts forever — **closed as
  not planned**. [graphiti#1489](https://github.com/getzep/graphiti/issues/1489)
  (open): deleted episodes leave stale references and orphaned entities; the
  dead entity lives on in the graph.

Four of those were closed by the vendors as *not planned* and one as *stale*.
The rot classes are known, reported, and declined — which is why the test
layer has to live outside the stores.

## Where this sits vs existing benchmarks

MemoryAgentBench, Memora, STALE, PrecisionMemBench, AgentAssay and kin score a
memory *capability* once, on a curated corpus, in a lab. AgentAssay regression-
tests agent *workflows*, not memory content. Nothing in the literature runs
continuously against a live production memory store, regression-tests memory
content between versions, or covers doc-drift as a class. Capability benchmarks
exist; **CI for a production memory store does not.** That is the claim this
repo makes, and the catalogue above is its test plan.

## The loop

```
incident happens → becomes a check → check runs on every scan/report → never twice
```

Run the catalogue against your own stack: `helicon scan && helicon report`.
