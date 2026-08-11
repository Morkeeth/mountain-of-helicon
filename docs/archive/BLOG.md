# Mount Helicon: An Agent-Agnostic Memory Audit System

*Oscar, June 2026*

> **Dated build diary.** The Build Timeline below is history: each day's numbers were true when written and are deliberately left alone, because rewriting them would forge the record this project exists to keep. Numbers stated in the present tense were refreshed on 2026-07-15. For current counts, README.md and ARCHITECTURE.md are the maintained surfaces, and `python3 -m helicon.docdrift` checks them against source.

---

I have 103 memory files spread across Claude Code, ChatGPT, and Cursor. I reviewed maybe 10 of them last month. I shipped from maybe 3. The rest sit there, decaying, contradicting each other, referencing "this week" from five weeks ago. Nobody checks them.

This is normal. Memory systems store everything, audit nothing.

Mount Helicon is a three-layer system that reads memory from any AI tool, audits it for staleness and contradictions, learns your review patterns, and checks its own stored conclusions. I built it in two weeks for the Qwen Cloud MemoryAgent track, using 1,268 real memory units extracted from 208 Claude Code transcripts, 150+ Obsidian files, and several other sources. Zero fake data.

## The Problem: Memory Rots

Mem0's ECAI 2025 research showed production memory accuracy drops to 49% after 30 days at 38% staleness. That number matched what I was seeing in my own setup. A memory file says a project is "in progress" when it was abandoned three weeks ago. Another says I decided to use React for a portfolio, while a newer file says I switched to a multi-model approach. Both live side by side in the memory store.

Every memory system I looked at focuses on the same thing: store more, retrieve better. Mem0 ($24M raised, 48K GitHub stars), Letta ($10M), Zep, Cognee ($7.5M) -- they all append. Nobody reviews. Nobody audits. Nobody asks "is this memory still true?"

## Research Foundation

I read a lot of papers before writing code, then built Mount Helicon's own take on six established patterns:

**Structured memory units.** Versioned memory-with-metadata (rather than raw text) is a well-understood idea in the memory-systems literature. Mount Helicon's HeliconCube is our build of it: every memory item is an object with source, timestamp, type, content hash, confidence score, and validity window — plus per-type decay, which is where we go further.

```python
@dataclass
class HeliconCube:
    id: str
    source: str          # "claude-code", "obsidian", "git", "chatgpt", "cursor"
    source_ref: str      # original session or file reference
    type: str            # "code", "memory", "draft", "decision", "project"
    content_hash: str    # SHA-256 for dedup and change detection
    confidence: float    # Weibull decay applied per-type
    review_status: str   # "pending", "approved", "revised", "killed"
    novelty_score: float | None  # SAGE-style gate score
    novelty_action: str | None   # ADD / NOOP / MERGE
    # ... 10 more fields
```

**Memory Bear (Dec 2025)** defined three-axis audit: temporal consistency (are timelines still valid?), factual consistency (do memories contradict?), and logical consistency (do reasoning chains hold?). Mount Helicon runs all three as an offline audit pass.

**SSGM Framework (Mar 2026) and LiCoMemory (Huang 2025)** gave me the forgetting model. Ebbinghaus decay treats all memory types equally. The Weibull distribution does not:

```python
def weibull_decay(days_since_reinforcement, eta, kappa, review_count=0):
    """w(dt) = exp(-(dt/eta)^kappa)
    kappa < 1: slow start, accelerates later (decisions, archives)
    kappa = 1: exponential (equivalent to Ebbinghaus)
    kappa > 1: fast initial decay, slows later (code, dashboards)
    """
    effective_eta = eta * (1 + 0.5 * review_count)
    return math.exp(-((days_since_reinforcement / effective_eta) ** kappa))
```

This matters. A draft post (kappa=1.8, eta=10) decays to 0.0000 after 42 days. A strategic decision (kappa=0.8, eta=30) is still at 0.18 confidence at the same age. Code rots fast. Decisions fade slowly. Ebbinghaus cannot express that difference.

**SAGE (May 2026)** contributed the novelty gate pattern: score incoming content as ADD (new information), NOOP (redundant), or MERGE (overlaps with existing). This cut unnecessary storage at ingestion.

**MetaMem (ACL 2026, OpenBMB)** showed that you can learn retrieval strategy from usage patterns, not just store and rank.

**Honest Lying (May 2026)** documented how reflective agents confabulate false beliefs that self-reinforce. The fix: adversarial audit that challenges stored conclusions against fresh evidence. This became Mount Helicon's meta-audit layer.

Two more systems shaped specific components. **Hermes Agent (Nous Research, Feb 2026)** used three-layer memory with FTS5 and a closed learning loop, which validated the SQLite approach. **Brian Armstrong's notes (Jun 2026)** on Coinbase's AI infrastructure -- response caching, model routing, cost visibility -- informed the token management layer.

## Architecture

Mount Helicon has three layers:

**Layer 1 (Extraction):** Connectors read from Claude Code JSONL transcripts, Claude Code memory files, Obsidian vaults, git repositories, agent skill files, ChatGPT exports, and Cursor memory banks. Twelve connector modules ship today; four are enabled in this repo's config (Claude Code, Obsidian, git, skills), and the rest are there for stores Helicon audits but does not own. Each connector produces `ConnectorResult` objects, which the scanner converts to HeliconCubes with content hashing and optional Qwen enrichment (summarization + SAGE novelty gate).

**Layer 2 (Review Pattern Learning):** Learns from behavior, not instructions. The system tracks review velocity by type, shipping rates (what gets approved vs. killed), spin detection (same topic discussed across 4+ sessions without file changes), and kill prediction. Every review decision feeds back into the model.

**Layer 3 (Meta-Audit):** The differentiator. Mount Helicon audits its own stored patterns. The temporal axis finds memory items with time-relative language ("this week", "tomorrow") that are days or weeks old. The factual axis uses Qwen to detect contradictions between overlapping memories. The decay axis flags items below confidence thresholds. The logical axis challenges patterns with few data points. The human reviews the audit findings, and those audit decisions become data for the next audit cycle. The meta-loop closes.

The data layer is 10 SQLite tables plus an FTS5 virtual table:

- `helicon_cubes` -- versioned memory units (1,268 rows from real data)
- `reviews` -- human review decisions with timing metadata
- `patterns` -- learned behavioral patterns with confidence and evidence
- `audit_log` -- three-axis audit findings with severity and proposed actions
- `retrieval_log` -- MetaMem-inspired tracking of which lookups influenced decisions
- `scan_log` -- connector run history
- `entities` -- knowledge graph nodes (projects, people, tools, concepts)
- `edges` -- co-occurrence and contradiction edges between entities/memories
- `consolidations` -- "sleep" cycle outputs (merged cluster summaries)
- `qwen_cache` -- SHA-256 keyed response cache for Qwen API calls
- `cubes_fts` -- FTS5 full-text search index on titles, content, summaries, and tags

## Key Technical Decisions

**Weibull over Ebbinghaus.** The shape parameter `kappa` makes all the difference. I defined per-type parameters based on observed review behavior:

| Type | eta (scale) | kappa (shape) | Behavior |
|------|-------------|---------------|----------|
| code | 7.0 | 1.5 | Cliff: stale fast, then plateaus |
| draft | 10.0 | 1.8 | Steep cliff: irrelevant within weeks |
| decision | 30.0 | 0.8 | Long tail: stays partially relevant |
| archive | 180.0 | 0.5 | Very long tail: slow fade over months |
| dashboard | 7.0 | 2.0 | Steepest cliff: stale within days |
| pattern | 60.0 | 0.7 | Long tail: learned behaviors persist |

Ebbinghaus is the special case where kappa=1 for every type. It cannot distinguish between a dashboard snapshot (worthless after a week) and a strategic decision (still partially valid after two months).

**SQLite over a vector database.** FTS5 handles full-text search well enough for the use case. The knowledge graph (entities + edges) stores co-occurrence and contradiction relationships without needing embeddings. Deployment stays simple: one file, no infrastructure beyond the Python process. Hermes Agent's FTS5-based approach validated this.

**Multi-model Qwen routing.** Three tiers: `qwen-turbo` for extraction and summarization (high volume, low complexity), `qwen-plus` for pattern detection and novelty gating (moderate complexity), and `qwen-max` for audit passes and contradiction detection (needs careful reasoning). Every call is logged with model, latency, token counts, and estimated cost:

```python
MODELS = {
    "fast": "qwen-turbo",
    "default": "qwen-plus",
    "deep": "qwen-max",
}

TIER_COST_PER_1K = {
    "qwen-turbo": 0.0003,
    "qwen-plus": 0.0008,
    "qwen-max": 0.0024,
}
```

The system also tracks per-operation routing data and generates recommendations: if an operation consistently runs fast with a high-tier model, it suggests downgrading to save cost.

**Cache-aware Qwen calls.** Identical prompts produce identical results. The cache key is a truncated SHA-256 of `model:system:user`:

```python
def _cache_key(system: str, user: str, model: str) -> str:
    return hashlib.sha256(f"{model}:{system}:{user}".encode()).hexdigest()[:24]
```

Cache entries are persisted in the `qwen_cache` SQLite table with token counts and timestamps. On a re-scan, previously enriched memories hit the cache instead of making API calls. The dashboard shows hit/miss rates and estimated tokens saved.

**Real data only.** The demo runs on 1,268 HeliconCubes extracted from my actual Claude Code transcripts (208+ sessions), Obsidian vault (150+ files), and git repositories. The audit findings are real: 57-day-old drafts with 0.0001 confidence, memory files that contradict each other, patterns with 3 data points claiming high confidence. Zero synthetic data, zero seed scripts for fake content.

## Knowledge Graph and Memory Consolidation

The knowledge graph extracts entities (projects, people, tools, concepts) from memory content using both regex patterns and optional Qwen-powered extraction, then builds two types of edges:

- **Co-occurrence edges:** two entities mentioned in the same memory are linked. Weight increases with frequency.
- **Contradiction edges:** when the factual audit detects a conflict between two memories, a `contradicts` edge is created with elevated weight.

The graph visualization uses a force-directed layout in the UI, with nodes sized by mention count and colored by entity type.

Memory consolidation runs as a "sleep" cycle, borrowing the neuroscience metaphor intentionally. The system finds clusters of related memories by tag overlap and title similarity, then uses Qwen to synthesize each cluster into a single consolidated summary. The prompt: "Like the brain during sleep, merge related memories into a single coherent summary." It outputs a title, synthesis, confidence score, key insights, and a list of what has become outdated.

## MCP Server

Mount Helicon exposes 14 tools via an MCP server (JSON-RPC 2.0 over stdio) so AI agents can audit their own memory. The eight below are the set this post was written around; README.md carries the current table of all 14:

- `helicon_health` -- overall memory health score, memory counts, decay stats by type
- `helicon_stale` -- find items below a confidence threshold
- `helicon_search` -- FTS5 full-text search across all memories
- `helicon_contradictions` -- pending contradiction findings from the factual audit
- `helicon_recent_reviews` -- the human's latest review decisions
- `helicon_patterns` -- learned behavioral patterns with confidence scores
- `helicon_context` -- proactive memory injection: describe your task, get ranked memories
- `helicon_triage` -- trigger auto-triage: Mount Helicon applies learned rules autonomously

Two new tools in v2: `helicon_context` (proactive memory injection for agents starting a task) and `helicon_triage` (agents can trigger auto-triage directly). This means an agent like Claude Code can check whether something it is about to store already exists, whether its own previous outputs are still considered valid, what the human tends to approve or kill, and load the most relevant memories for its current task. The agent becomes a participant in the audit loop, not just a subject of it.

## Build Timeline

**Days 1-2:** Built 5 connectors (Claude Code JSONL + memory files, Obsidian, Git, ChatGPT, Cursor). Scanned real data. Got 1,268 HeliconCubes into the database.

**Days 3-4:** Qwen Cloud integration via DashScope OpenAI-compatible API. Forgetting engine with Weibull decay. Audit engine with four axes. 82 audit findings on first run.

**Days 5-7:** FastAPI backend (28 endpoints, 8 routers). React/Vite frontend. Voice input via Web Speech API. Keyboard shortcuts (j/k navigate, a/r/k to approve/revise/kill, / for search). 7 tabs: Review, Audit, Graph, Sleep, Patterns, Tokens, Overview.

**Days 8-12:** Knowledge graph with entity extraction and force-directed visualization. MCP server with 6 tools. Memory consolidation ("sleep" cycles). FTS5 full-text search. Contradiction resolution UI. Retrieval learning (Loop 4).

**Days 13-14:** Weibull decay (replacing simple Ebbinghaus). Multi-model routing with cost tracking. Response cache with SHA-256 prompt hashing. Token dashboard with per-model and per-operation breakdowns.

**Day 15:** Auto-triage engine. This is the feature that turns Mount Helicon from a tool into an agent. After enough human reviews, Mount Helicon derives triage rules: if 79% of `code` items historically get killed and this one has <10% confidence, auto-kill it. The human only reviews uncertain items. On first run, auto-triage handled 585 out of 1,268 memories autonomously, pushing the Helicon Score from 7% to 53.5% without a single human decision.

```python
def run_auto_triage(conn, dry_run=False):
    rules = compute_triage_rules(conn)   # derive from review history
    for rule in rules:
        if rule["rule_confidence"] < 0.5:
            continue
        rows = conn.execute(
            "SELECT id FROM helicon_cubes WHERE type = ? AND confidence < ? AND review_status = 'pending'",
            (rule["cube_type"], rule["confidence_threshold"])
        ).fetchall()
        for row in rows:
            conn.execute("UPDATE helicon_cubes SET review_status = 'killed'", ...)
```

Also added proactive MCP context injection: `helicon_context` lets agents describe their current task and receive ranked memories by relevance, plus active patterns and open contradictions. The agent does not search; Mount Helicon decides what is relevant and delivers it.

**Day 16:** CLI for plug-and-play setup. Three commands from zero to auditing:

```bash
pip install helicon-audit
helicon init       # auto-detects Claude Code, Cursor, Obsidian, git repos
helicon scan       # extracts memory into HeliconCubes
helicon serve      # starts the review UI
```

Also added `helicon stack` (audits your AI tool setup: session count, memory files, vault size, stack completeness %), `helicon triage` (run auto-triage from the terminal), `helicon score` (see your Helicon Score with decay-by-type breakdown), and `helicon optimize` (Qwen-powered analysis of your memory patterns with specific recommendations). The init command walks the filesystem, finds `~/.claude`, `~/.cursor`, Obsidian vaults on iCloud, and git directories, then writes a ready-to-use `config.json`. No manual path editing.

**Day 17:** Project Intelligence layer. The demo killer. Mount Helicon now groups memories by project tag, computes per-project metrics (ship rate, spin score, decay velocity, days since last output), and ranks projects by what needs attention.

The Focus tab opens first. Top banner: "You touched 11 projects this week. You shipped from 6." Below that, project cards ranked by urgency. Each card shows:

- **Spin score** = sessions / shipped items. Over 3x means pure spin (talking about it, not building it).
- **Ship rate** = approved / total reviewed. 0% means nothing survived review.
- **Days since output** = last commit or approved memory. Over 14d = stale.
- **Urgency score** = weighted combination of spin + staleness + review backlog + decay + shipping momentum.

Mount Helicon picks one-line actions per project: "Stop planning, start shipping. 4 sessions per shipped item." or "Stale 62d. Either push a commit or archive." With Qwen enabled, it generates personalized recommendations from the actual data.

This is the feature that makes the demo undeniable. Not "here's a tool that tracks memory" but "here's a system that tells you what to do next, based on what you actually did."

**Day 18:** Decay-based triage. The auto-triage engine previously only learned from review history (behavioral rules). Types with few reviews had no rules. Now Mount Helicon also generates decay-based rules: if the Weibull model says confidence is below 5% and multiple items of that type are in the same state, auto-kill them. The Weibull curve itself is the evidence, not the review history. This added 3 new rules (draft, file_created, idea) and triaged 92 more items, pushing the score from 53.6% to 60.9%. Total auto-triage: 677 items handled without human input.

Also: full system audit, README rewrite (was showing 28 endpoints when there are 42), config.example.json for Docker builds, Dockerfile port fix. The codebase is now 11,313 lines across Python and TypeScript.

**Day 19:** Task playbooks and context impact tracking. Two new modules that close the loop between "what Mount Helicon surfaces" and "did it help."

Task playbooks mine the review history into 6 categories (build, content, design, audit, context, career). Each playbook contains: rules extracted from feedback memories, review stats (ship rate, kill rate), and a ready-to-use prompt template. The `helicon_playbook` MCP tool matches any task description to the best playbook, so an agent starting a "write a tweet" task automatically gets content voice rules and timing constraints. 6 playbooks, all populated from real data.

Context impact tracking connects retrieval to outcomes. When `helicon_context` surfaces memories, Mount Helicon logs what was shown. When a review happens, it marks which surfaced memories were "acted on." Over time, this builds a usefulness score per memory: how often was it surfaced, how often did the human act on it? Memories that get surfaced 10 times but never acted on are noise. This is the "did having this memory make the output better?" question, answered with data.

Matching logic uses word-level tag overlap (not substring) to avoid false positives. 51 API endpoints, 14 routers, 9 MCP tools, 9 CLI commands.

**Day 20:** Three features that build on established retrieval-and-memory patterns and take each further.

**Q-value utility learning.** Reinforcement-learning utility ranking is a known pattern; our build has one deliberate difference. Every memory gets a utility score that updates with each retrieval cycle: `Q_new = Q_old + alpha * (reward - Q_old)`. When a memory is surfaced via `helicon_context` and the human later approves it, reward=1.0. If killed, reward=0.0. The Q-value feeds back into retrieval ranking via `score = (1-lambda)*relevance + lambda*Q`. The difference: reward comes from a *human* ruling only, never the system's own auto-triage — so the loop can't reinforce its own echo, the failure mode a naive utility signal has.

**Entity-boosted retrieval.** Entity-aware hybrid search is an established retrieval pattern. Mount Helicon already had 41 entities and 605 edges in its knowledge graph, but they weren't wired into retrieval. Now: when a task mentions an entity (e.g., "relay"), the system finds all memories linked to that entity in the graph and boosts their retrieval score. Three signals combined: FTS relevance + Q-value utility + entity graph boost.

**Core Memory Compiler.** Compiling memory into loadable context is an established pattern; ours compiles from *human rulings and Golden Rules with provenance*, not raw memory — so the output is governed law, not a summary. It produces `core-memory.md` (top 20 highest-utility approved memories), 6 skill files (one per task category with feedback rules), and a `claude-md-patch.md` (suggested CLAUDE.md additions). These are files agents can load without calling any MCP tool. The compiler runs via `helicon compile` CLI or `helicon_compile` MCP tool.

57 API endpoints, 14 routers, 11 MCP tools, 11 CLI commands.

**Day 21:** Semantic search is live.

Rewrote the embedding layer to use numpy vector search instead of sqlite-vec (which doesn't work on macOS Python 3.12 -- `enable_load_extension` is not compiled in). Embeddings stored as BLOBs in a regular SQLite table. Cosine similarity computed in Python with numpy matrix multiplication. No external vector DB, no native extensions.

1,268 memories embedded in 19 seconds with all-MiniLM-L6-v2 (384 dims, 80MB model). 100% coverage. Hybrid search combines semantic similarity (60% weight) and FTS5 keyword match (40% weight). "Content strategy twitter" returns the exact content strategy files at 0.745 hybrid score. The MCP retrieval pipeline (`helicon_context`) now uses hybrid search automatically when embeddings exist, falling back to FTS5-only when they don't.

This is the biggest retrieval quality jump so far. FTS5 keyword-only was ~25% P@3 on conceptual queries. Semantic search catches synonyms, related concepts, and fuzzy matches that keyword search misses entirely.

**Day 22:** Six-item technical audit sweep.

1. **Embedding-based consolidation.** The consolidation engine now uses cosine similarity to find semantic clusters before falling back to tag/title overlap. At threshold 0.75, it finds 18 embedding clusters: 7 edits to `proof-of-favour.ts` bundled together, dashboard edits grouped, hotline-related files clustered. Neuroscience-inspired memory compression -- like the brain during sleep.

2. **Deep Cursor connector.** Cursor stores AI code tracking in `~/.cursor/ai-tracking/ai-code-tracking.db`. The connector now reads `scored_commits` (75 commits with AI/human line attribution) and `conversation_summaries`. Each commit includes lines added by tab completion vs composer vs human, plus an AI percentage. 24 new memories from Cursor data alone.

3. **Consolidation MCP tool.** `helicon_consolidate` is now the 12th MCP tool. Agents can trigger memory consolidation without the web UI. Combined with `helicon_context` and `helicon_triage`, an agent can now self-audit, retrieve, consolidate, and triage its own memory.

4. **Eval harness upgraded.** The retrieval benchmark now uses hybrid search instead of FTS5-only. P@3 jumped from 25% to 62.5%. MRR from 0.2 to 0.5. Forgetting accuracy at 93.6%. Composite eval score: 76.8%.

5. **Auto-inject tested and working.** `inject_into_claude_code()` writes 7 skill files to `~/.claude/skills/`: core memory + 6 per-category skill files. Claude Code loads these automatically. The compiler-to-agent loop is closed.

   > **Correction, 2026-07-15:** that last sentence did not survive. `inject_into_claude_code()` still exists in `compiler.py` and still works if you call it, but no command ever wires it up, so nothing invokes it in practice and the push half of the loop is not closed. The pull half is what shipped: `helicon_context` over MCP. The claim is left standing above because the timeline is a record, not a pitch. `helicon policy --inject` is the write-back that did close, into `~/.claude/GOLDEN_RULES.md`.

6. **Triage rules broadened.** Added confidence floor (kill below 20%), unreviewed-type rules (kill types with zero human reviews below 70%), and high-kill-rate behavioral (>95% kill rate, threshold raised to 60%). Score pushed from 60.9% to 76.2%.

12 MCP tools, 12 CLI commands, 5 connectors, eval composite 76.8%.

## What Makes Mount Helicon Different

Most memory systems sit at Layer 1: store and retrieve. Some reach Layer 2: organize and index. Mount Helicon's contribution is Layer 3: audit what you have stored, check it against fresh evidence, and learn from the human's review behavior to do it better next time. And now Layer 4: make its own decisions about what to keep and what to kill, based on what it learned from the human.

The cross-platform extraction is not a feature for its own sake. It is what makes the audit meaningful. When you can see a Claude Code memory file that says "project is active" alongside a git history showing no commits in 40 days, the contradiction becomes visible. Siloed memory cannot surface that.

The meta-loop is the core idea. Mount Helicon stores patterns about how the human reviews. Then it audits those patterns. Then the human reviews the audit. Then Mount Helicon uses those patterns to auto-triage obvious cases. Each pass sharpens the model. The human reviews less, not more. The goal is a Helicon Score going up while review time goes down.

---

*Mount Helicon is open source and built for the Qwen Cloud Global AI Hackathon, MemoryAgent track. Stack: Python, FastAPI, SQLite + FTS5, React/Vite, Qwen Cloud API (turbo/plus/max), MCP (JSON-RPC 2.0). Repository: [github.com/MorkeethHQ/mount-helicon](https://github.com/MorkeethHQ/mount-helicon)*
