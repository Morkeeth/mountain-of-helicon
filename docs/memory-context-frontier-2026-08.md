# The memory / context / knowledge frontier — 2026-08

**Why this doc exists.** Oscar ordered a full search on the latest in the memory–context–knowledge area (2026-08-20) so Mountain of Helicon's direction is set against the live field, not last year's picture — and so the project's status is shareable with others. Three parallel research agents, ~60 searches, every claim sourced. Sections: (1) memory systems, (2) context engineering & personal knowledge infra, (3) does anyone score an agent setup.

## The synthesis — what this means for Mountain of Helicon

**1. The field converged on Helicon's substrate.** Plaintext, git-versioned, background-consolidated memory is what won 2026: Letta shipped memory-as-git-repo (Feb 2026), Anthropic shipped Dreams (May 2026), OpenAI shipped consumer Dreaming (June 2026), and Cursor *killed* its opaque non-diffable memory feature — the one negative data point, proving the trust model. Helicon's markdown/SQLite/receipts approach is not behind the frontier; it is the frontier's trust model.

**2. The wedge is measured, twice over.**
- **Nothing scores a whole personal stack** (skills + routines + memory content + context files) against a reference. The two attempts died at 5 and 0 GitHub stars; the primitives exist separately (rubrics, lint engines, reference corpora, leaderboards, memory harnesses) and nobody has composed them. Personal memory-store *content* quality has **zero entrants**.
- **The problem Helicon's exam attacks is unsolved at the top of the market**: on independent fact-consolidation benchmarks the field collapses — Mem0 18%, Graphiti/Zep 7% (the temporal-KG specialist worst at its own headline feature). "Is what we stored still true" is an open wound even for the $24M companies.

**3. The five things to steal** (each maps to a Helicon surface):
- **Validity windows, not deletion** (Zep): stamp superseded facts `valid_until:`, keep history queryable → MEMORY/DRIFT.
- **Tense-rewriting** (OpenAI Dreaming): any memory carrying a future date is re-evaluated after that date passes — a trivially implementable nightly rule → MEMORY.
- **Deterministic freshness over LLM judgment** (arXiv 2606.01435): slot-based recency rules beat asking the model who wins a contradiction → DRIFT.
- **Measure the rules file, don't just curate it** (arXiv 2601.20404: AGENTS.md = −28.6% runtime, −16.6% tokens in a controlled study): a rules-file change is an improvement only if the number moves → SETUP score.
- **Transcript mining that closes the loop** (Claude Code `/insights`, vibe-log): repeated instructions in transcripts are undischarged rules; surface them as proposed rule edits → HISTORY → SETUP.

**4. Competitive watch for the HISTORY surface**: local transcript observability is getting crowded (`/insights`, vibe-log, claude-view, Claudoscope, vibe-replay) — all *show* usage; none feeds a stack score or a memory store. Helicon's edge is composition: history → exam → score → improvement, one loop.

**5. The reference for "how good is your setup" now has literature behind it**: AgentLinter's named reference corpus, Anthropic's context-engineering guidance (index-in-context/bodies-on-disk, <200-line rules files, stable prefixes), ACE's failure modes (brevity bias, context collapse — incremental deltas beat rewrites). The SETUP score's rubric can cite sources, not taste.

---
# Part 1 · Memory Systems for AI Agents — the Mid-2026 Landscape

Research date: 2026-08-20. ~17 web searches. Source-quality note applied throughout: several widely-cited "neutral" comparison sites are vendor-owned — [vectorize.io's comparison articles](https://vectorize.io/articles/best-ai-agent-memory-systems) are written by Hindsight's parent company, [mem0.ai's "State of AI Agent Memory 2026"](https://mem0.ai/blog/state-of-ai-agent-memory-2026) is Mem0 marketing, and [evermind.ai's framework roundups](https://evermind.ai/blogs/8-best-ai-agent-memory-frameworks-for-developers-in-2026) are EverMind marketing. Vendor sites are used only for facts about their own products; all self-benchmarks are labeled as such.

## Letta (MemGPT)

**Architecture in one line:** OS-inspired tiered memory — the agent itself edits named in-context "memory blocks" (core memory) and pages archival memory in/out, rather than an external pipeline doing extraction ([letta.com/blog/agent-memory](https://www.letta.com/blog/agent-memory/)).

**Genuinely novel:** Two things, both real. (1) **Sleep-time compute** (April 2025): a second background agent shares the primary agent's memory blocks and rewrites them while the primary is idle — memory management decoupled from conversation latency, so the sleeper can run a bigger, slower model than the responder ([letta.com/blog/sleep-time-compute](https://www.letta.com/blog/sleep-time-compute/)). This preceded and clearly prefigured both Anthropic's and OpenAI's 2026 "Dreaming" features. (2) **Context Repositories** (February 2026): memory projected onto the local filesystem as plain files ("MemFS") and versioned in git — every memory change is a commit with a message, subagents merge divergent learned context through standard git operations ([letta.com/blog/context-repositories](https://www.letta.com/blog/context-repositories/)).

**Marketing:** "Machines that learn" framing; the original MemGPT DMR benchmark was later beaten by Zep on Zep's own eval — the benchmark war between these two is vendor-on-vendor throughout.

**Adoption signal:** The MemGPT paper is the founding document of the whole category; Letta remains the reference architecture cited in every 2026 survey ([vectorize.io comparison](https://vectorize.io/articles/best-ai-agent-memory-systems) — vendor source, but the "Letta = full control, self-managed" positioning is consistent across independent writeups like [MachineLearningMastery's 2026 roundup](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/)).

**Steal for a personal stack:** Context Repositories is the most stealable idea on this list for a CLAUDE.md-style setup: memory as plain files under git, where every consolidation is a reviewable diff with a commit message. Also the two-model split — cheap model talks, expensive model consolidates offline.

## Mem0

**Architecture in one line:** LLM extraction pipeline turns conversation into atomic facts stored in a hybrid vector-store + knowledge-graph backend, scoped to user/session/agent, with an LLM conflict-detection step on write ([mem0.ai](https://mem0.ai/); formalized in their April 2026 paper per [vectorize.io](https://vectorize.io/articles/best-ai-agent-memory-systems)).

**Genuinely novel:** Less the architecture (extract-facts-into-vectors is now commodity) than the ops maturity: 21 framework integrations, five vector-store backends, and an April 2026 single-pass hierarchical extraction algorithm for token efficiency ([mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) — vendor source).

**Marketing:** The headline numbers — "26% higher accuracy than OpenAI memory on LOCOMO, 91% lower p95 latency, 90% fewer tokens" — are Mem0-run benchmarks ([mem0.ai](https://mem0.ai/)). Independent evaluation is much less kind: on Memory Agent Bench's Fact Consolidation task Mem0 scores **18%** (see "What nobody solves yet"). And its recency handling has a documented failure mode: the base configuration can retrieve an old address if it's semantically closer to the query than the current one ([atlan.com Zep-vs-Mem0](https://atlan.com/know/zep-vs-mem0/)).

**Adoption signal:** Strongest in the category: ~48K GitHub stars, $24M Series A (Oct 2025, Basis Set), 186M API calls/quarter ([valueaddvc.com](https://valueaddvc.com/blog/the-ai-memory-problem-how-startups-are-solving-for-persistent-context)).

**Steal:** The three-scope hierarchy (user / session / agent) is a clean mental model for a personal stack. Also the write-time conflict check: run extraction and contradiction-detection as one pass, not as a later cleanup.

## Zep / Graphiti

**Architecture in one line:** Bi-temporal knowledge graph — every edge (fact) carries a validity window (became-true, superseded-at) plus provenance, built incrementally in real time from "episodes" ([arxiv.org/abs/2501.13956](https://arxiv.org/abs/2501.13956), Jan 2025; [getzep.com temporal-knowledge-graph](https://www.getzep.com/ai-agents/temporal-knowledge-graph/)).

**Genuinely novel:** Edge invalidation is the best contradiction-resolution design in the category: when a fact changes, the old edge is marked invalid with a timestamp rather than deleted, so "what was true in January" remains answerable while only the current fact surfaces by default ([atlan.com](https://atlan.com/know/zep-vs-mem0/), [neo4j.com Graphiti writeup](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)). Point-in-time queries are a real capability nobody else ships cleanly.

**Marketing:** "Outperforms MemGPT on DMR" is Zep's own paper on a benchmark of their choosing. And the design does not survive independent stress: Graphiti/Zep scored **7%** on the Fact Consolidation benchmark — worse than Mem0 — despite contradiction-handling being its headline feature ([arxiv 2606.01435](https://arxiv.org/html/2606.01435v1)).

**Adoption signal:** Graphiti ~30K GitHub stars, Apache-2.0, promoted by Neo4j ([neo4j.com](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)); Zep is the "temporal context" pick in most 2026 roundups ([braintrust.dev](https://www.braintrust.dev/articles/best-ai-agent-memory-tools-2026)).

**Steal:** The bi-temporal idea costs almost nothing to adopt in a markdown memory system: never delete a superseded fact — stamp it `valid_until:` and keep it. A GOLDEN_RULES "settled rulings" pattern is halfway there; the missing half is the machine-checkable validity window.

## LangMem / LangChain memory

**Architecture in one line:** Python SDK giving LangGraph agents three memory types — episodic (past interactions), semantic (extracted facts), and procedural (the agent rewrites its own system prompt from feedback) ([langchain.com/blog/langmem-sdk-launch](https://www.langchain.com/blog/langmem-sdk-launch), [github.com/langchain-ai/langmem](https://github.com/langchain-ai/langmem)).

**Genuinely novel:** Procedural memory — prompt self-rewriting from accumulated feedback — is the one idea here the others underweight. The rest is a thin, competent layer over LangGraph's store.

**Marketing/reality gap:** Still pre-1.0 (v0.0.30, October 2025 — no release in ~10 months as of mid-2026), and third-party benchmarking puts p95 latency at ~60 seconds, unusable for interactive agents ([vectorize.io langchain-memory-alternatives](https://vectorize.io/articles/langchain-memory-alternatives) — competitor-adjacent source, but the stale release cadence is verifiable on [GitHub](https://github.com/langchain-ai/langmem)).

**Adoption signal:** ~746K monthly PyPI downloads, 5M+ total (June 2026) — big by download count, but that reflects LangChain's gravity, not LangMem's quality ([atlan.com](https://atlan.com/know/long-term-memory-langchain-agents/)).

**Steal:** Procedural memory as a named, separate store. A personal stack that captures feedback but never automatically folds it back into the operating prompt is doing episodic capture without the procedural loop.

## Claude Code native memory + CLAUDE.md ecosystem

**Architecture in one line:** Four layers of plain markdown: scoped CLAUDE.md instruction files (human-written law), Auto Memory (agent-written dated notes in `~/.claude/projects/<project>/memory/`, on by default since early 2026), a MEMORY.md index, and a consolidation pipeline built on Anthropic's Dreams primitive ([milvus.io claude-code-memory](https://milvus.io/blog/claude-code-memory-memsearch.md), [thepromptshelf.dev guide](https://thepromptshelf.dev/blog/claude-code-memory-auto-memory-system-2026/)).

**Genuinely novel:** **Dreams / Dreaming** — announced at Code w/ Claude, May 2026, documented as a first-class platform primitive ([claude.com/blog/new-in-claude-managed-agents](https://claude.com/blog/new-in-claude-managed-agents), [platform.claude.com/docs/en/managed-agents/dreams](https://platform.claude.com/docs/en/managed-agents/dreams) — primary sources). A scheduled process reads the memory store plus past session transcripts and emits a reorganized store: duplicates merged, stale or contradicted entries replaced with latest values, cross-session patterns surfaced, output as a reviewable diff with optional human approval. Secondary sources report a 24h-or-5-sessions trigger and Harvey (legal AI) claiming ~6x agent completion-rate lift ([blog.imseankim.com](https://blog.imseankim.com/claude-dreaming-anthropic-managed-agents-memory-consolidation-harvey-6x-may-2026/), [claudefa.st](https://claudefa.st/blog/guide/mechanics/auto-dream) — the 6x number is unverified against any primary source; treat as vendor-relayed anecdote). Community replicas exist for the local CLI ([grandamenium/dream-skill](https://github.com/grandamenium/dream-skill)).

**Marketing/limits:** Everything is files-on-one-machine: auto memory doesn't sync across devices, and there's no retrieval layer — memory is either in context or grep-able, nothing in between ([milvus.io](https://milvus.io/blog/claude-code-memory-memsearch.md), which is itself selling a vector-search fix).

**Adoption signal:** CLAUDE.md is arguably the most-used agent memory format in the world by daily active use; the "memory-as-reviewable-markdown" pattern the startups are now converging on (Letta's Context Repositories) is this pattern productized.

**Steal:** What it lacks and the others have: (1) validity windows on facts (Zep), (2) a real consolidation cadence with a diff you approve (Dreams exists but the local pipeline is young — the dream-skill repo's existence signals demand ahead of supply), (3) any retrieval smarter than grep.

## OpenAI / ChatGPT memory ("Dreaming")

**Architecture in one line:** Consumer-scale background synthesis — a batch process reads across a user's multi-year conversation history during idle time and rewrites a compact memory state, replacing the old curated saved-memories list ([openai.com/index/chatgpt-memory-dreaming](https://openai.com/index/chatgpt-memory-dreaming/) — primary source; shipped to Plus/Pro in the US, June 4 2026 per [neowin.net](https://www.neowin.net/news/openai-is-rolling-out-a-major-upgrade-to-chatgpt-memory/)).

**Genuinely novel:** Self-updating memories with tense: "you're going to Singapore in July" rewrites itself to "you went to Singapore in July 2026" after the trip — OpenAI's own canonical example. Plus "memory sources": personalized responses show which memories were used, deletable/correctable inline. OpenAI explicitly frames the motivation as staleness-at-scale.

**Marketing:** The improvement numbers circulating (factual recall 67.9%→82.8%, preference adherence 55.3%→71.3%) are OpenAI internal evals relayed by secondary press ([tech-insider.org](https://tech-insider.org/chatgpt-dreaming-v3-memory-update-2026/), [techtimes.com](https://www.techtimes.com/articles/317840/20260605/chatgpt-memory-dreaming-update-openai-rewrites-personalization-engine-limits-audit-trail.htm)); unverifiable on openai.com directly — treat as vendor-claimed. TechTimes also reports the update *reduced* the audit trail's granularity — the transparency story cuts both ways.

**Adoption signal:** Largest deployed memory system on earth by user count; not available as infrastructure — you can't build on it, only be a subject of it.

**Steal:** Tense-rewriting on time-indexed facts is a beautiful, simple consolidation rule: any memory containing a future date is re-evaluated after that date passes. Trivially implementable in a markdown stack with a nightly pass.

## Cursor Memories

**Architecture in one line:** Sentence-sized project-scoped facts proposed by a background model mid-chat, user-approved before saving, auto-injected into future conversations — not in the repo, not versioned, not shared with teammates ([localskills.sh guide](https://localskills.sh/blog/cursor-memories-guide), [forum.cursor.com](https://forum.cursor.com/t/about-cursors-memory-record-feature/107355)).

**The arc is the finding:** Shipped mid-2025 → **removed in version 2.1.x in late 2025** → 2026 is a cottage industry of third parties selling persistent-memory workarounds for Cursor ([blockchain-council.org](https://www.blockchain-council.org/ai/cursor-ai-track-memory-across-conversations/), [memnexus.ai](https://memnexus.ai/blog/2026-02-20-cursor-persistent-memory), [hindsight.vectorize.io](https://hindsight.vectorize.io/blog/2026/06/12/cursor-persistent-memory)). A major vendor shipped agent memory, watched it, and pulled it — the only negative data point in this whole landscape, and worth more than most launches.

**Steal:** The approval-before-save gate (a background model proposes, human confirms) is the right trust model for personal memory — and the removal is a warning: unversioned, un-inspectable memory that users can't audit gets distrusted and killed. The systems that survived 2026 (CLAUDE.md, Letta) are the file-based, diffable ones.

## The newer 2026 entrants

**Cloudflare Agent Memory** (private beta, April 17 2026) — managed extraction + retrieval on Workers/Durable Objects/Vectorize, pitched at "context rot"; differentiator is edge distribution, pricing unannounced ([infoq.com](https://www.infoq.com/news/2026/04/cloudflare-agent-memory-beta/)). *Signal:* the memory layer is now a hyperscaler checkbox.

**AWS Bedrock AgentCore Memory & Google Vertex AI Memory Bank** — both GA or near-GA by Q1-Q2 2026, both priced identically at $0.25 per 1,000 memory events ([agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/09/aws-bedrock-agentcore-vs-azure-ai-agent-service-vs-google-vertex-ai-agents-q2-2026)). *Signal:* identical pricing = commoditization of managed extract-and-retrieve.

**Hindsight (Vectorize)** — open-source; four memory networks (World facts / Experiences / Opinions-with-confidence / Observations) with retain-recall-**reflect** operations and four parallel retrieval strategies (semantic, BM25, graph, temporal) plus reranking ([vectorize.io/blog/introducing-hindsight](https://vectorize.io/blog/introducing-hindsight-agent-memory-that-works-like-human-memory), paper: [arxiv 2512.12818](https://arxiv.org/pdf/2512.12818), [VentureBeat coverage](https://venturebeat.com/data/with-91-accuracy-open-source-hindsight-agentic-memory-provides-20-20-vision)). "Most accurate ever benchmarked" (LongMemEval SOTA, Jan 2026) is self-reported. *Steal:* separating **beliefs with confidence scores** from facts — holding "prefers X (0.7)" distinctly from "ruled X" maps exactly onto a rulings-vs-hunches distinction.

**Supermemory** — universal memory API (add/search/connect), multimodal ingestion, custom vector-graph engine, sub-300ms hybrid search; $26M seed Oct 2025 with Google exec backing ([techcrunch.com](https://techcrunch.com/2025/10/06/a-19-year-old-nabs-backing-from-google-execs-for-his-ai-memory-startup-supermemory/)). *Steal:* memory-plus-personal-RAG as one surface rather than two systems.

**Memvid** — no database: data, embeddings, index, and metadata packaged in a single append-only `.mv2` file of hash-stamped "Smart Frames," a rewindable timeline; claims 0.025ms P50 retrieval ([devgenius.io comparison](https://blog.devgenius.io/ai-agent-memory-systems-in-2026-mem0-zep-hindsight-memvid-and-everything-in-between-compared-96e35b818da8), claims unverified). *Steal:* the single-portable-file idea — memory you can copy between machines — directly answers Claude Code's no-sync gap.

**MIRIX** — academic multi-agent memory system, six memory types (Core/Episodic/Semantic/Procedural/Resource/Knowledge-Vault) each managed by its own agent; self-reported SOTA 85.4% on LOCOMO ([arxiv.org/abs/2507.07957](https://arxiv.org/abs/2507.07957)). *Steal:* the taxonomy, not the machinery.

**Honcho (Plastic Labs) & Cognee** — Honcho bets on "social memory": continually-updated representations of *people* rather than facts; Cognee is the self-hosted open-source graph-memory pick ([glukhov.org provider comparison](https://www.glukhov.org/ai-systems/memory/agent-memory-providers/), [braintrust.dev](https://www.braintrust.dev/articles/best-ai-agent-memory-tools-2026)). *Steal from Honcho:* entity-centric memory — a maintained model of a person, not an append log.

## Cross-cutting patterns

**1. Sleep-time consolidation went from research idea to table stakes in 14 months.** Letta shipped sleep-time compute April 2025; Anthropic shipped Dreams as a managed-agents primitive May 2026; OpenAI shipped consumer Dreaming June 2026; academia followed with learned consolidators (Auto-Dreamer, [arxiv 2605.20616](https://arxiv.org/pdf/2605.20616)). The shared shape: a background pass, off the latency path, optionally on a bigger model, that merges duplicates, resolves contradictions, retenses time-expired facts, and emits a reviewable rewrite. This is the defining memory feature of 2026.

**2. Memory is converging on files and git, not databases.** Letta's Context Repositories (Feb 2026), Claude Code's markdown-everything, community dream-skills, Memvid's portable file — the winning trust model for *personal* memory is diffable plaintext under version control, while databases (vector, graph) win for *product* memory at scale. Cursor's removal of its opaque memory feature is the counterexample that proves it.

**3. Contradiction resolution has exactly two live designs, and they trade off.** Zep/Graphiti: invalidate the old edge with a timestamp, keep history, point-in-time queries work. Mem0 and most others: LLM conflict-detection at write time, most-recent-wins, with a documented failure where semantic similarity beats recency. A 2026 paper argues both are wrong to let the LLM adjudicate at all: deterministic slot-based freshness rules beat LLM judgment on conflict resolution ([arxiv 2606.01435, "Don't Ask the LLM to Track Freshness"](https://arxiv.org/pdf/2606.01435)).

**4. Decay/forgetting is an active research front but barely shipped.** FSFM's taxonomy of forgetting ([arxiv 2604.20300](https://arxiv.org/abs/2604.20300)), FadeMem's biologically-inspired fading ([arxiv 2601.18642](https://arxiv.org/pdf/2601.18642)), Ebbinghaus-curve and ACT-R-inspired usage-reinforced decay ([Towards Data Science](https://towardsdatascience.com/context-windows-forget-what-matters-i-used-a-140-year-old-psychology-paper-to-fix-ai-memory/), [ACM HAI '26](https://dl.acm.org/doi/10.1145/3765766.3765803)). In products, "decay" mostly means Dreaming-style pruning passes; nobody ships true usage-weighted forgetting.

**5. Benchmark theater is endemic.** Every vendor is SOTA on a benchmark it chose or built: Mem0 on LOCOMO, Zep on DMR, Hindsight on LongMemEval, MIRIX on ScreenshotVQA. Two major surveys now exist to cut through it ([Memory in the Age of AI Agents, arxiv 2512.13564](https://arxiv.org/abs/2512.13564); [arxiv 2603.07670](https://arxiv.org/abs/2603.07670)).

## What nobody solves yet

**Fact consolidation under adversarial updates — everyone fails.** On Memory Agent Bench's Fact Consolidation task (a newer fact supersedes an older one; the system must return the current value), the field collapses: Mem0 **18%**, RAPTOR/GraphRAG/MIRIX **14%**, Graphiti/Zep **7%** — the temporal-knowledge-graph specialist scoring worst on the exact problem it markets ([arxiv 2606.01435](https://arxiv.org/html/2606.01435v1)). Every "resolves contradictions" claim above should be read against these numbers.

**Knowing a memory is stale ≠ acting on the update.** The STALE benchmark's core finding: models can often *recognize* that a memory is outdated yet still *apply* the stale belief, and they're highly susceptible to queries that presuppose outdated information ([arxiv 2605.06527](https://arxiv.org/pdf/2605.06527)). Consolidation fixes the store; nothing yet fixes the retrieval-time reasoning.

**Cross-tool, cross-device memory portability.** Claude Code memory doesn't sync between machines; ChatGPT memory is a walled garden; Cursor pulled its feature; every startup wants to *be* the universal layer, which is why none is. Memvid's portable file and Letta's git remotes are the only credible portability primitives, and neither is a standard.

**Memory safety/governance.** Memory contamination and poisoning (MemGuard, [arxiv 2605.28009](https://arxiv.org/pdf/2605.28009)), and governance of self-evolving memory (SSGM, [arxiv 2603.11768](https://arxiv.org/pdf/2603.11768)) are papers, not products — nobody ships a production answer to "what if the agent wrote something wrong/malicious into its own memory and then consolidated it into invisibility." Notably, OpenAI's Dreaming reportedly *reduced* audit-trail granularity.

**The verdict for a personal stack:** the field converged on the plaintext-versioned-background-consolidated pattern — the pieces worth stealing are Zep's validity windows, OpenAI's tense-rewriting rule, Hindsight's belief-vs-fact separation with confidence, LangMem's procedural feedback-to-prompt loop, and deterministic (not LLM-judged) freshness rules per arxiv 2606.01435. The open wounds — consolidation correctness, staleness-at-retrieval, portability — are unsolved everywhere, including by the $24M companies.

---
# Part 2 · Context Engineering & Personal Knowledge Infrastructure — Frontier Report (2026-08-20)

Method note: web-search based (~20 searches/fetches). Claims cite primary or named-author sources; programmatic SEO content was discarded. Dates given per source.

## 1. Context engineering as a discipline

- **Anthropic's canonical guidance** — "Effective Context Engineering for AI Agents" (Anthropic applied AI team, Sept 2025) framed context engineering as the successor to prompt engineering: "curating and maintaining the optimal set of tokens during LLM inference." Core prescriptions: system prompts at the right "altitude" (clear, not micromanaging), minimal viable tool sets (if a human can't say which tool applies, the agent can't either), and three techniques for long horizons — compaction, structured note-taking, and multi-agent architectures. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **ACE — Agentic Context Engineering** (Stanford/UC Berkeley/SambaNova, arXiv 2510.04618, Oct 2025; open-sourced on GitHub 2026) is the most-cited research formalization: context as an **evolving playbook** maintained by a Generator/Reflector/Curator loop. Its two named failure modes are now standard vocabulary: **brevity bias** (summaries drop domain insight) and **context collapse** (iterative rewriting erodes detail). Fix: structured, *incremental delta updates* rather than full rewrites. Reported: +10.6% on AppWorld, +8.6% finance reasoning. https://arxiv.org/abs/2510.04618 · https://sambanova.ai/blog/ace-open-sourced-on-github · https://github.com/ace-agent/ace
- **Manus's production lessons** (Yichao "Peak" Ji, manus.im blog, July 2025) remain the practitioner reference for the inference-cost side: KV-cache hit rate is "the single most important metric for a production-stage agent" (10x cost difference on cached vs uncached tokens); keep prompt prefixes stable (a timestamp at the top of a system prompt kills the cache); make context append-only; treat the **file system as unlimited external context** with *restorable* (not lossy) compression — drop a document's content but keep its path so it can be re-read. https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- **HumanLayer / Dex Horthy — "Advanced Context Engineering for Coding Agents" (ACE-FCA)**: the leading practitioner methodology for coding agents, covered by Gergely Orosz's Pragmatic Engineer (2025-26). Key practice: **frequent intentional compaction** — keep context utilization at 40–60%, write research/plan files as compact human-readable artifacts, and *restart the session with better steering* rather than pushing a degraded context forward. Spec-first over vibe-prompting; the human reviews the plan, not 2,000 lines of diff. https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md · https://newsletter.pragmaticengineer.com/p/context-engineering-with-dex-horthy

## 2. Context rot — the empirical basis

- **Chroma's "Context Rot" technical report** (July 2025, popularized via Timothy B. Lee's Understanding AI coverage) tested 18 frontier models (GPT-4.1, Claude 4 family, Gemini 2.5, Qwen3): **every model degrades as input length grows**, non-uniformly, well before the advertised window fills. https://www.understandingai.org/p/context-rot-the-emerging-challenge
- The **"lost in the middle"** U-shape (accuracy highest at start/end of context, >30% degradation mid-context) replicates across model families and underpins why "just stuff the window" fails. Summarized with the 2026 literature at https://www.morphllm.com/context-rot
- 2026 extensions: "Classifier Context Rot" (arXiv 2605.12366, 2026) shows even monitor/judge models degrade with context length — meaning your *evaluators* rot too, not just your workers. https://arxiv.org/html/2605.12366v1
- The emergent 2026 architecture consensus is **hybrid**: retrieve/navigate to a relevant subset, then long-context reason over it — not pure RAG, not pure long-context. (Survey framing: https://glasp.co/articles/context-rot-rag-long-context-hybrid)

## 3. Compaction, memory primitives, and platform support

- **Anthropic context management platform features** (announced Sept 2025, anthropic.com/news/context-management): **context editing** (server-side clearing of old tool_result bodies while keeping the tool_use record — an 84% token reduction in a 100-turn eval, enabling runs that otherwise die of context exhaustion) and the **memory tool** (file-based `/memories` directory the model is instructed to check first and maintain, assuming "context could be reset at any moment"). https://www.anthropic.com/news/context-management · Cookbook: https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools
- **Managed compaction API** (beta flag `compact-2026-01-12`, Jan 2026): the API auto-summarizes history past a configurable threshold (min 50K tokens) into a compaction block; supports Opus 4.6/Sonnet 4.6 across direct API, Bedrock, Vertex, Foundry; customizable via an `instructions` field. Practitioner-noted tradeoff: server-side opacity — you can't inspect what was lost. https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-compaction.html
- **Letta (ex-MemGPT)** is the reference architecture for agent-managed memory: **memory blocks** (labeled, size-capped sections of the context window, shareable across agents) plus **sleep-time agents** — background agents that share the primary agent's memory blocks and consolidate/rewrite them while the primary is idle, decoupling memory maintenance from response latency. https://www.letta.com/blog/memory-blocks/ · https://www.letta.com/blog/sleep-time-compute/ · https://docs.letta.com/guides/agents/architectures/sleeptime/
- **Anthropic Agent Skills** (launched Oct 2025; SKILL.md format): **progressive disclosure** as the load-bearing pattern — ~tens of tokens of name+description always loaded, full SKILL.md loaded on trigger, referenced files loaded only during execution. This is the platform's answer to context rot: an index in context, bodies on disk. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview

## 4. CLAUDE.md / AGENTS.md — rules files and their maintenance

- **AGENTS.md won the standards war.** Originally an OpenAI/Codex push; GitHub Copilot added native support Aug 2025; by Dec 2025, 60,000+ OSS projects and 20+ tools (Cursor, Cline, Windsurf, Codex, Gemini CLI, Jules, Zed, Amp, Factory…). Stewardship moved to the **Agentic AI Foundation** (a Linux Foundation directed fund) for vendor neutrality. Deliberately schema-free markdown. https://www.morphllm.com/agents-md-guide · https://blog.agentailor.com/posts/top-ai-agent-standards-2026
- **It measurably works**: "On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents" (Lulla, Baltes, Treude et al., arXiv 2601.20404, submitted Jan 28 2026, revised Mar 2026) — 10 repos, 124 PRs, with/without AGENTS.md: **−28.64% median runtime, −16.58% output tokens, comparable completion rates**. First controlled evidence the rules file pays for itself. https://arxiv.org/pdf/2601.20404
- **Best-practice consensus (2026)**: keep it small (Anthropic's own target is ~under 200 lines); one canonical file with CLAUDE.md/others symlinked or generated from it, never contradicting; audit for stale rules and *test whether the agent actually follows each rule*. Unblocked published a 7-step CLAUDE.md audit method (https://getunblocked.com/blog/audit-fix-bloated-claude-md/); **AgentLint** (agentlint.app) is an emerging linter-style tool for rules files (https://www.agentlint.app/blog/claude-md-best-practices-2026/); ClaudeForge does generation/maintenance (via https://www.scriptbyai.com/claude-code-resource-list/).
- **Claude Code auto-memory** (2026): per-repo `~/.claude/projects/<project>/memory/` with a MEMORY.md index (first 200 lines / 25KB loaded every session) plus topic files read on demand — the index-plus-lazy-load pattern applied to agent self-notes; plain markdown, machine-local, `/memory` to manage. https://code.claude.com/docs/en/memory
- **Self-updating rules files** are now a mainstream pattern, not a hack: Addy Osmani's "Self-Improving Coding Agents" (Jan 31, 2026) describes the loop — atomic task, validate via tests/lint gates, commit, *update AGENTS.md with discovered patterns/gotchas*, reset context; "each improvement should make future improvements easier"; archive obsolete rules out rather than letting the file bloat. https://addyosmani.com/blog/self-improving-agents/

## 5. Personal knowledge bases wired to agents

- **Karpathy's "LLM wiki" gist** (published ~April 4, 2026 per coverage; "a spec, not a piece of software"; 5,000+ stars within two months) is the defining document of 2026 personal-knowledge-for-agents: don't retrieve on demand (RAG) — **compile knowledge over time like code**. Three layers: immutable raw sources → LLM-maintained interlinked markdown wiki (one page per concept) → a schema file defining conventions. His argument: the cross-reference bookkeeping that makes humans abandon wikis is exactly what LLMs are good at. Coverage: https://techstrong.ai/articles/google-launches-a-universal-format-for-karpathys-llm-wiki/ · https://akitaonrails.com/en/2026/05/18/ai-agent-memory-karpathy-llm-wiki-agentmemory/
- **Google's Open Knowledge Format (OKF) v0.1** (June 12, 2026) standardized the pattern: vendor-neutral markdown-plus-YAML-frontmatter bundles, shippable as a git repo or tarball, consumable by any agent — an interoperability layer for curated agent knowledge. https://www.marktechpost.com/2026/06/16/google-cloud-introduces-open-knowledge-format-okf-a-vendor-neutral-markdown-spec-for-giving-ai-agents-curated-context/ · https://kfchou.github.io/llm-wiki-google-okf/
- **Obsidian + Claude Code** is the dominant DIY implementation: the vault as external memory, agents reading/writing plain markdown directly (no plugin required; Local REST API plugin for programmatic access). Notable open-source builds: **obsidian-second-brain** (eugeniughelbur — persistent memory for Claude Code + 6 other CLI agents, hybrid semantic search, self-rewriting notes, scheduled agents that maintain the vault overnight; https://github.com/eugeniughelbur/obsidian-second-brain) and **claude-obsidian** (AgriciDaniel — drop-any-source, agent files and links it, explicitly based on the Karpathy pattern; https://github.com/AgriciDaniel/claude-obsidian). The common workflow: sub-agents scan the vault for related notes *before* writing anything new. https://pasqualepillitteri.it/en/news/962/obsidian-claude-code-second-brain-persistent-memory

## 6. Harness portability — moving memory between Claude Code, Cursor, Codex

- The portability conversation crystallized in 2026 around **user-owned, local-first, markdown-based state layers** that outlive any one harness:
  - **agentmemory** (jayzeng): local markdown store (daily logs, scratchpad, topic notes, durable decisions) + qmd semantic search, shared by Claude Code, Codex, Cursor, and Cursor CLI — "the same store even as models and harnesses change." https://github.com/jayzeng/agentmemory (deep-dive: https://knightli.com/en/2026/05/19/agentmemory-persistent-memory-ai-coding-agents/)
  - **Memorix** (AVIDS2): cross-agent memory via MCP — one shared project memory surviving "new chats, IDE switches, terminal sessions, and handoffs" across 14+ harnesses. https://github.com/AVIDS2/memorix
  - Local-first engineering results are strong: one build reports 94.5% LoCoMo recall@10 at 70ms p50, fully local. https://hackernoon.com/how-i-built-local-first-memory-for-claude-code-cursor-and-codex-945percent-locomo-recall10-70ms-p50
- The three portability layers as of mid-2026: **AGENTS.md** (behavioral instructions, per-repo, Linux Foundation stewarded), **OKF bundles** (curated knowledge, git-portable), **MCP memory servers / local markdown stores** (accumulated experience). A caution from reviewers: cross-agent memory is only as good as its audit surface — "AgentMemory is useful only if you audit what it remembers." https://www.developersdigest.tech/blog/github-trending-agentmemory-2026-05-16

## 7. Observability of your own agent usage

- **Claude Code built-ins**: `/usage` (24h/7d breakdown from local session history; https://code.claude.com/docs/en/costs) and — the notable 2026 addition — **`/insights`** (~April 2026): scans up to 200 local sessions, runs an Opus-powered five-phase pipeline (scan → parse → facet extraction of goals/outcomes/friction → aggregation → insight generation), outputs an HTML report at `~/.claude/data/report.html` covering focus areas, interaction style, what's working, **friction with examples, and concrete CLAUDE.md improvement suggestions** — fully local. https://blog.vincentqiao.com/en/posts/claude-code-insights/
- **vibe-log-cli** (open source): analyzes Claude Code *and* Codex sessions locally; monthly retrospectives, "instructions you keep repeating" → CLAUDE.md optimization, unused-feature blind spots. https://github.com/vibe-log/vibe-log-cli
- **claude-view**: mission-control dashboard — full sub-agent tree with per-agent cost/token breakdown, week-over-week comparisons, queryable via MCP ("how much did I spend today"). https://claudeview.ai/changelog/ · https://recca0120.github.io/en/2026/04/07/claude-view-mission-control/
- **Claudoscope** (macOS): session viewer + cost analytics computed locally from transcripts, four-threshold cost alerts, read-only MCP server so Claude can query your own usage. https://claudoscope.com/ · **Claude Logs**: per-turn token/cost estimation with dated pricing tables, CSV export. https://claudelogs.com/ · **vibe-replay**: year-in-review over your own transcripts ("878 sessions, 52.9k tool calls"). https://vibe-replay.com/blog/personal-insights/
- **session-retrospective skill** (accidentalrebel): a Claude Code skill that runs a structured retro on the just-finished session — the lightweight, in-harness version of the same idea. https://github.com/accidentalrebel/claude-skill-session-retrospective
- Population-level baseline for comparison: Anthropic's "How Claude Code is used in practice" (2026) — debugging share of sessions fell 33%→19%; humans make planning decisions, Claude makes execution decisions. https://www.anthropic.com/research/claude-code-expertise
- For power users, OpenTelemetry export exists (e.g. https://github.com/ColeMurray/claude-code-otel), but the 2026 pattern for *personal* observability is clearly **local transcript mining, not hosted telemetry**.

## Who's doing it best

- **Anthropic** — the only vendor shipping the full stack as primitives: context editing, memory tool, managed compaction, Skills' progressive disclosure, auto-memory, and `/insights` (the first vendor-shipped *self*-observability with rules-file feedback). Their Sept 2025 essay is still the field's reference text.
- **Dex Horthy / HumanLayer** — best *human workflow* around coding agents: intentional compaction at 40–60% utilization, research/plan artifacts as the compaction medium, restart-don't-push-through. The Pragmatic Engineer coverage made it the de facto industry playbook.
- **Manus** — best *production economics*: KV-cache-first design, append-only context, restorable compression, filesystem-as-context.
- **Letta** — best *memory architecture* research-to-product: memory blocks + sleep-time consolidation is the pattern everyone else is converging on.
- **Karpathy (+ Google OKF)** — best *personal knowledge* framing: knowledge compiled like code, not retrieved like search; now with a portable standard.
- **ACE authors (Stanford/Berkeley/SambaNova)** — best *theory of rules-file evolution*: named the failure modes (brevity bias, context collapse) and proved incremental deltas beat rewrites.

## What a self-improvement tool for an agent stack should copy

1. **Incremental deltas, never full rewrites, of the evolving context.** ACE's core empirical finding: iterative rewriting causes context collapse; curated append/edit deltas preserve detail and compound. (arXiv 2510.04618)
2. **Index in context, bodies on disk.** Skills' progressive disclosure and auto-memory's 200-line MEMORY.md index with on-demand topic files are the same mechanism; a self-improvement tool should audit that the index stays a pointer layer and never re-inlines the bodies. (platform.claude.com Skills docs; code.claude.com/docs/en/memory)
3. **Restorable compression + stable prefixes.** Drop content, keep the path/reference so anything can be re-read; never let a mutable header (timestamp, live status) sit at the top of an always-loaded file. (manus.im)
4. **Measure the rules file, don't just curate it.** arXiv 2601.20404 gives the template: run the same tasks with/without (or before/after) the rules file and report runtime/token deltas — a rules-file change is only an improvement if the number moves. Pair with a stale-rule audit that tests whether the agent actually obeys each rule (Unblocked's 7-step method).
5. **Mine your own transcripts locally, and close the loop into the rules file.** `/insights` and vibe-log both converge on the same move: friction extracted from real sessions → concrete CLAUDE.md/AGENTS.md edits. Repeated instructions in transcripts are undischarged rules; a self-improvement tool should surface them automatically. (blog.vincentqiao.com; github.com/vibe-log/vibe-log-cli)
6. **Sleep-time consolidation.** Memory maintenance as a background agent sharing the primary's memory, not a closing chore in the main loop — the Letta pattern, echoed by Obsidian tools running scheduled overnight vault-maintenance agents. (letta.com/blog/sleep-time-compute; github.com/eugeniughelbur/obsidian-second-brain)
7. **Reset over persist.** Both Osmani's loop and Horthy's intentional compaction treat a fresh context seeded with better artifacts as superior to a long degraded one — the tool's job is making the *seed* (plan files, learnings, memory index) good enough that resets are cheap. (addyosmani.com; humanlayer ace-fca.md)
8. **Keep the knowledge layer portable and auditable.** Plain markdown, git-shippable, harness-agnostic (AGENTS.md + OKF-style bundles + local memory stores), with an explicit audit surface for what the agent has remembered — memory you can't inspect is memory you can't trust. (morphllm.com/agents-md-guide; MarkTechPost OKF; developersdigest.tech)

---
# Part 3 · Does anything score a personal AI-agent setup? (mid-2026)

**Short answer: the lane is occupied at the edges and empty in the middle.** Config *linters* and config *scorers* exist (all small, free, prompt- or CLI-based; none has traction beyond a few hundred stars). Usage *leaderboards* exist and are where the "flex" culture lives. Security scanners for agent configs are a real, funded category. But nothing scores a person's **whole stack** — skills + routines + memory content + context files — against a reference of "good," and nothing at all scores the *content quality of a personal memory store*. That is the wedge.

## 1. Config scorers — "get a score out of 100" (exists, tiny, un-productized)

The closest things to "Lighthouse for your agent setup." All are free skills/prompts/CLIs, none is a product, none has a sharing/leaderboard mechanic:

- **Claude Code Excellence Audit** (Rom Iluz) — installs as a `/audit` slash command; scans global + project config and grades a 100-point rubric across 8 categories: Memory/CLAUDE.md (25), modular rules (15), settings/permissions (15), subagents (15), commands (10), hooks (10), MCP (5), skills (5). Grade scale A+ to F; landing page claims "most setups score 30–60 on first audit." **Adoption: 5 GitHub stars, 0 forks** — the idea validated, the product absent. No leaderboard, no share feature. ([landing](https://audit-my-cc.replit.app/), [repo](https://github.com/romiluz13/claude-code-excellence-audit), [LobeHub listing](https://lobehub.com/skills/romiluz13-claude-code-excellence-audit))
- **cc-health-check** (yurukusa) — free CLI, 20 checks across 6 dimensions (safety guards, code quality, monitoring, recovery, autonomy, coordination), 0–100 score with fix commands. Reads `~/.claude/settings.json` and CLAUDE.md files. **Archived July 2, 2026 with zero stars** — a direct attempt at exactly this niche that died with no adoption. ([repo](https://github.com/yurukusa/cc-health-check))
- **"Scoring your Claude Code setup across 8 dimensions"** — blog-post rubric, run-it-yourself prompt, no tool. ([daveinside.com](https://daveinside.com/blog/scoring-and-improving-your-claude-code-setup-across-8-dimensions/))
- **claude-code-ultimate-guide audit prompts** (FlorianBruniaux) — copy-paste audit prompts (`audit-prompt.md`, `context-audit-prompt.md`), not tooling. ([repo file](https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/main/tools/audit-prompt.md))
- **Skill-level auditors** — a cluster of skills that grade *skills* specifically against Anthropic's best practices: Skill Auditor ([mcpmarket](https://mcpmarket.com/tools/skills/skill-auditor)), Skill Evaluator ([mcpmarket](https://mcpmarket.com/tools/skills/skill-evaluator-1)), community skill-doctor plugins ([claudeskills.info](https://claudeskills.info/plugins/anthropics/claude-plugins-community/skill-doctor/)). Anthropic's own **skill-creator plugin** has Eval/Improve/Benchmark modes with executor/grader/comparator agents — official, but scoped to one skill at a time, not the stack. ([anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md))

## 2. Config linters — errors and warnings, not grades (the most mature lane)

These treat CLAUDE.md/AGENTS.md like code. Rule-based, deterministic, no "how good is your setup" verdict:

- **agnix** — "the missing linter and LSP for AI coding assistants": **448 rules** across Claude Code, Codex CLI, Cursor, Copilot, Cline, Gemini CLI, Kiro; validates CLAUDE.md, AGENTS.md, SKILL.md, hooks, `*.mcp.json`, `.cursorrules`; IDE plugins + autofixes. **387 stars, 1,191 commits** — the biggest thing in the whole space. Lints; does not score. ([repo](https://github.com/agent-sh/agnix))
- **claudelint** — 116 rules across 10 categories; catches circular CLAUDE.md imports, dangerous skill commands, misconfigured MCP servers. ([claudelint.com](https://claudelint.com/), rule count per search result — unverified beyond the site listing)
- **AgentLinter** (Simon Kim, v0.1 Feb 2026, v2.3 Mar 2026, MIT) — the only one that names its **reference corpus**: rules derived from Anthropic's guidelines, academic papers (Gloaguen et al. 2026, Song et al. TMLR 2026), and "patterns from high-performing agent workspaces." Scores 8 dimensions 0–100 (structure, clarity, completeness, security, consistency, memory strategy, runtime config, skill safety) across CLAUDE.md/AGENTS.md/SOUL.md/skills dirs for Claude Code, Cursor, Windsurf, OpenClaw, Moltbot. The closest existing thing to "reference of what good looks like" — but file-scoped, not stack-scoped. ([agentlinter.com](https://agentlinter.com/))
- **cclint** — TypeScript CLAUDE.md linter/optimizer. ([repo](https://github.com/felixgeelhaar/cclint))
- **cursor-doctor** — Cursor-rules diagnostic: conflict detection, redundancy, token-budget breakdown, gap analysis, auto-fix. ([dev.to writeup](https://dev.to/nedcodes/i-rewrote-my-cursor-linter-into-a-full-diagnostic-tool-and-added-auto-fix-5ehb))
- Community practice pieces on linting/scoring CLAUDE.md: [dev.to "Check, Score, Improve & Repeat"](https://dev.to/cleverhoods/claudemd-lint-score-improve-repeat-2om5), [yeda-ai "Score your CLAUDE.md like a linter"](https://yeda-ai.com/kb/skills-mcp/score-claude-md-linter-contradictions).

## 3. Usage rankers & the "flex" culture — leaderboards exist, but they rank *activity*, not setup quality

- **AIQ Rank** (Second Coffee LLC, launched recently, private beta for teams) — "a fitness tracker for your AI craft." Scores your last 30 days of **actual session activity** across 11 dimensions (customization, orchestration, background work, tool breadth, planning…) for Claude Code, Codex CLI, OpenCode, Cursor, Cowork. Percentile-based, max 1000, public leaderboard with S-tier, private company leaderboards for teams/candidates. This is the leaderboard mechanic the config scorers lack — but it measures *behavior*, not the setup itself. ([aiqrank.com](https://www.aiqrank.com/))
- **claude-code-leaderboard** — hook-based token-usage tracker with a global leaderboard; ranks volume, nothing about quality. ([repo](https://github.com/grp06/claude-code-leaderboard))
- **Sharing culture = repos, not rankings.** People share setups as dotfiles repos ([yulonglin/dotfiles](https://github.com/yulonglin/dotfiles), [benswift/.dotfiles](https://github.com/benswift/.dotfiles), [citypaul/.dotfiles](https://github.com/citypaul/.dotfiles), [haberlah's forkable dotfiles-claude](https://medium.com/@haberlah/configure-claude-code-to-power-your-agent-team-90c8d3bca392)), "my setup" blog posts ([freek.dev](https://freek.dev/3026-my-claude-code-setup), [drmowinckels.io](https://drmowinckels.io/blog/2026/dotfiles-coding-agents/)), and since late 2025 as **Claude Code plugins/marketplaces** — Anthropic explicitly frames plugins as the sharing unit ([anthropic.com/news/claude-code-plugins](https://anthropic.com/news/claude-code-plugins)). It's show-and-tell; no scoring, no comparison, no badge.

## 4. Security scanners — the funded adjacent category

Agent-config auditing *for threats* is a real commercial lane (the "security-audit" half of the analogy exists; the "Lighthouse" half doesn't):

- **Snyk agent-scan** — scans AI agents, MCP servers, and agent *skills* for prompt injection, tool poisoning, toxic flows. ([repo](https://github.com/snyk/agent-scan))
- **mcp-scan** (Invariant Labs) — scans MCP configs for tool poisoning, shadowing, cross-origin escalation. ([blog](https://invariantlabs.ai/blog/introducing-mcp-scan))
- Plus Enkrypt AI MCP Scanner ([enkryptai.com](https://www.enkryptai.com/mcp-scan)), AgentAuditKit GitHub Action ([marketplace](https://github.com/marketplace/actions/agentauditkit-mcp-security-scan)), Inkog ([inkog.io](https://inkog.io/mcp-security)).

## 5. Memory benchmarks — runnable outside papers, but only on memory *systems*, never on your *store*

The harnesses are genuinely usable now, not paper-only:

- **LongMemEval** ships a public eval harness: feed timestamped history to *your own chat system*, output jsonl, run `evaluate_qa.py`. **LongMemEval-V2** (2026) adds a packaged harness, data-prep tools, and leaderboard utilities. ([repo](https://github.com/xiaowu0162/longmemeval), [V2 repo](https://github.com/xiaowu0162/LongMemEval-V2))
- **mem0/memory-benchmarks** — open-source suite, one-command LongMemEval runs against a Mem0 backend. ([repo](https://github.com/mem0ai/memory-benchmarks), [mem0 2026 benchmark survey](https://mem0.ai/blog/ai-memory-benchmarks-in-2026))
- Runnable notebook walkthroughs exist ([NirDiamant/Agent_Memory_Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques/blob/main/all_techniques/29_memory_benchmarks_LoCoMo/memory_benchmarks_locomo.ipynb)); vendors compete on scores publicly ([Mastra 95% LongMemEval](https://mastra.ai/research/observational-memory)).

**But this is a disguised null.** Every harness benchmarks the *retrieval machinery* by injecting the benchmark's own synthetic conversations. Nothing evaluates the **content of an existing personal store** — staleness, contradictions, pointer rot, duplication, one-line-rule discipline in a real MEMORY.md/vault. LoCoMo/LongMemEval cannot be pointed at your store; they replace it.

## 6. Maturity models — enterprise-only

Agent maturity models exist and are everywhere in 2026 — but all are org-level assessments (5-pillar, 1–5 stages, governance/talent/data): [digitalapplied self-assessment guide](https://www.digitalapplied.com/blog/agentic-ai-maturity-model-enterprise-self-assessment-guide), [agility-at-scale](https://agility-at-scale.com/ai/agents/enterprise-ai-agent-maturity-model/), [AgentMarketCap "pilot purgatory"](https://agentmarketcap.ai/blog/2026/04/11/enterprise-agent-deployment-maturity-model-2026), [Sema4](https://sema4.ai/blog/ai-maturity-model-2026/). None addresses an individual's stack.

## The empty lanes

1. **Whole-stack scoring against a reference.** Nothing evaluates skills + routines/automations + memory content + context files as one system. Existing scorers check *file presence and shape* ("do you have hooks? is CLAUDE.md structured?"), never *whether the content is good* (contradictions across files, dead pointers, rules that never fire). Searches tried: "audit your Claude Code setup score," "agent stack maturity score 2026," "score your AI setup." Closest hits are §1, all file-shape-level; the one direct attempt (cc-health-check) archived at 0 stars.
2. **Personal memory-store content quality.** Nothing found that scores an existing memory store (MEMORY.md, vault, mem0 account contents) for staleness/contradiction/recall usefulness. Searches tried: "LoCoMo LongMemEval run on personal memory store," "memory benchmark CLI mem0 zep letta." All hits benchmark the retrieval *system* on synthetic data (§5).
3. **Routines/automations review.** Nothing reviews a person's cron jobs, scheduled agents, or hook pipelines for quality/redundancy/risk. Searches tried: "tool reviews your AI automations routines audit score" — returned only enterprise workflow-platform listicles and prompt-eval SaaS (Braintrust, Confident AI), all aimed at product teams evaluating LLM outputs, not a person's automation stack.
4. **Setup-quality leaderboard / shareable badge.** No "Lighthouse score" social object exists. The leaderboards that exist (AIQ Rank, claude-code-leaderboard) rank *usage activity*; the scorers that exist have no sharing mechanic. Searches tried: "Claude Code setup leaderboard share screenshot," "reddit share your Claude Code setup flex." Sharing culture is thriving (dotfiles repos, plugins, awesome-lists) but entirely unscored — the "settings flex" happens as repo links and blog posts, never as a comparable number.
5. **Personal maturity model.** All maturity models found are enterprise/org assessments (§6). Nothing found for "how mature is *my* agent operation." Searches tried: "agent stack maturity model score AI agent setup 2026."

**Net read:** the primitives all exist separately — rubric (excellence-audit), reference corpus (AgentLinter), lint engine at scale (agnix), leaderboard mechanic (AIQ Rank), runnable memory harnesses (LongMemEval-V2) — but nobody has composed them into "run one command, get a graded report on your whole agent stack against a documented reference, share the score." The two products that tried the scoring half have 5 and 0 stars; the memory-content and routines lanes have zero entrants at all.
