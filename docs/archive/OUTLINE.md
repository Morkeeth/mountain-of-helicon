# Mount Helicon - Build Outline

**Tagline:** "Your agents are productive. You're not."

**What it is:** Agent-agnostic memory audit and review system. Reads memory from any AI tool, audits it for staleness and contradictions, learns your review patterns, and checks its own work.

**Deadline:** Jul 20, 2026, 2pm PDT (Qwen Cloud MemoryAgent hackathon; verified at devpost source Jul 13, old "Jul 9" was stale)

**V2:** Native Swift macOS app (post-hackathon)

---

## Research Foundation

Mount Helicon is built on six cutting-edge techniques from 2025-2026 ML research. This isn't a chatbot with memory bolted on.

| Technique | Source | What Mount Helicon borrows |
|-----------|--------|-------------------|
| **MemCube** | MemOS (Shanghai Jiao Tong, 2025) | Versioned memory units with metadata: source, valid_from, last_reinforced, confidence, type. Every memory is a structured object, not raw text. |
| **Three-axis audit** | Memory Bear (Dec 2025) | Audit on three dimensions: temporal (timelines consistent?), factual (contradictions?), logical (reasoning chains close?). Offline cron-style pass. |
| **MetaMem** | ACL 2026 Findings (OpenBMB) | Meta-layer that learns HOW to retrieve, not just what to store. Tracks which memory lookups were useful. Retrieval strategy improves over time. |
| **SSGM gates** | SSGM Framework (Mar 2026) | Consistency verification before any memory update commits. Stability monitor + safety governor veto bad updates. Prevents memory poisoning and semantic drift. |
| **Weibull decay** | SSGM (Mar 2026) via LiCoMemory (Huang 2025) | w(Δτ) = exp(-(Δτ/η)^κ). Non-uniform decay: κ<1 = slow start/fast end (archives), κ>1 = fast start/slow end (code). Ebbinghaus is the special case κ=1. |
| **Anti-confabulation** | "Honest Lying" (May 2026) | Reflective agents confabulate false beliefs that self-reinforce. Fix: adversarial audit challenges stored conclusions against fresh evidence. |

**Key stat:** Production memory accuracy drops to 49% after 30 days at 38% staleness (Mem0 research, ECAI 2025). Without temporal modeling, memory rots.

**Novelty gate at ingestion:** scores each new fact as novel (ADD), redundant (NOOP), or uncertain (LLM merge) so the store doesn't bloat with near-duplicates. Density-estimator novelty scoring is an established idea; our gate keeps provenance through a merge so a consolidated fact never loses the source it came from.

---

## Competitive Position

| Layer | Who | What's missing |
|-------|-----|---------------|
| Memory storage | Mem0 ($24M, 48K stars), Letta ($10M), Zep ($500K) | All single-platform. Append-only. No self-audit. |
| Temporal validity | Zep/Graphiti (bi-temporal windows, 63.8% LongMemEval) | Infrastructure-level, not user-facing |
| Self-improving | Cognee ($7.5M, graph self-maintenance) | No review interface. No human-in-the-loop. |
| Meta-memory | MetaMem, Memory Bear, SAGE | **Research only. Zero products.** |
| Agent review queue | Nobody | Langfuse/AgentOps observe. Nobody gates output. |
| Cross-platform | Nobody | Claude/ChatGPT/Cursor all siloed |

**Mount Helicon fills:** productized meta-memory audit + agent-agnostic review + cross-platform memory.

---

## The Product

### Three Memory Layers

**Layer 1: Extraction** - What did agents produce?
- Pluggable connectors: Claude Code JSONL, Obsidian vault, git repos, ChatGPT exports, Cursor memory banks, Mem0 API, any markdown/JSON
- Every extracted item becomes a HeliconCube — our structured memory unit: source, timestamp, type, content hash, valid_from, confidence, per-type decay
- Novelty gate at ingestion: ADD / NOOP / MERGE

**Layer 2: Review Patterns** - How does the human actually review?
- Learns from behavior, not words
- Review velocity by type (code: 24h, content: 14 days, resumes: never)
- Shipping patterns (what gets shipped vs killed vs ignored)
- Weibull decay curves per content type (κ>1 cliff for code/drafts, κ<1 long tail for decisions/archives)
- Spin detection: same topic in 4+ sessions without file changes
- Kill prediction: "Items like this that sit 30+ days have 94% kill rate"

**Layer 3: Meta-Audit (the differentiator)** - Is the memory itself still good?
- Three-axis audit (Memory Bear): temporal, factual, logical consistency
- SSGM consistency gates: verify before committing any pattern update
- Anti-confabulation: challenge stored patterns against fresh data
- MetaMem-style retrieval learning: track which patterns were useful
- Forgetting curves: confidence decays unless reinforced
- Memory budget: hard cap forces quality over quantity
- Human reviews the audit (meta-loop closes)

### Core Loop

```
Agents produce output (any platform)
  > Layer 1: extract + novelty gate (ADD/NOOP/MERGE)
  > Layer 2: present review feed, sorted by learned urgency
  > Human reviews (approve/revise/kill + voice)
  > Layer 2: update review patterns from behavior
  > Layer 3: periodic audit (three-axis + forgetting curves)
  > Layer 3: propose prunes, flag contradictions, challenge stale beliefs
  > Human reviews the memory audit
  > SSGM gate: verify consistency before committing updates
  > Cycle sharpens with each pass
```

### Learning Loops (how it gets smarter)

**Loop 1: Review signal accumulation**
```
Human reviews item → stored: {type, decision, time_to_review, age}
Every 10 reviews → Qwen analyzes full review history
Extracts patterns → updates feed sorting for next session
Signal: behavior, not words
```

**Loop 2: Pattern audit**
```
Every N reviews (or on demand):
Qwen reads stored patterns + last 30 days of review data
Three-axis check: temporal, factual, logical
Generates: {stale, contradicted, low_confidence, confabulated}
Human confirms prune / reinforce / dismiss
Audit decisions become data for next audit (meta-meta)
```

**Loop 3: Memory quality**
```
On demand or periodic:
Qwen cross-references memory files against actual usage
Flags: unused memory (0 references in 40 sessions)
Flags: contradicting memories (A says X, B says opposite)
Flags: confabulated beliefs (stored conclusion contradicts fresh evidence)
Human reviews flags → approved changes applied
SSGM gate validates consistency before commit
```

**Loop 4: Retrieval learning (MetaMem-inspired)**
```
Track which memory lookups influenced decisions
Which patterns were surfaced but ignored?
Which were surfaced and acted on?
Retrieval strategy improves: surface high-value patterns first
```

### Screens

**Feed** - Review cards sorted by learned urgency. HeliconCube snippet, source, age, spin count, confidence badge. Approve/revise/kill + voice input.

**Helicon Score** - What % of agent output you actually reviewed. Killing counts. Ignoring doesn't. Trends over time. Breakdown by source/type.

**Memory Audit** - Layer 3 output. Pattern list with confidence scores, staleness flags, contradiction alerts, confabulation warnings, proposed prunes. You review the memory itself.

**Patterns** - What Mount Helicon has learned: review velocity by type, shipping rates, decay curves, spin list. Each pattern shows data points, confidence, last reinforced date.

---

## Connectors (pluggable, agent-agnostic)

| Connector | Input format | Parser complexity |
|-----------|-------------|-------------------|
| Claude Code | JSONL transcripts + memory .md files | ~150 lines |
| Obsidian | Markdown with YAML frontmatter | ~80 lines |
| Git repos | Commits, uncommitted changes, branches | ~100 lines (gitpython) |
| ChatGPT | JSON export (conversations.json) | ~100 lines |
| Cursor | .cursorrules + memory bank .md files | ~60 lines |
| Mem0 API | REST API (if user has account) | ~50 lines |
| Generic markdown | Any .md folder | ~40 lines |
| People Radar | SQLite DB | ~40 lines |

V1 ships: Claude Code + Obsidian + Git. Others are stretch goals but architecture supports them from day 1.

---

## Architecture

```
ANY AGENT PLATFORM                 CLOUD (Alibaba ECS)

Claude Code JSONL ------+
Obsidian vault ----------+
Git repos ---------------+          +-------------------+
ChatGPT export ----------+--sync--> | Mount Helicon Backend     |
Cursor memory banks -----+          | (Python/FastAPI)   |
Mem0 API ----------------+          |                   |
Any markdown/JSON -------+          | Qwen Cloud API:   |
                                    |  - extraction     |
                                    |  - novelty gate   |
                                    |  - pattern detect  |
                                    |  - three-axis audit|
                                    |  - anti-confab     |
                                    |                   |
                                    | SQLite:           |
                                    |  - helicon_cubes    |
                                    |  - reviews        |
                                    |  - patterns       |
                                    |  - audit_log      |
                                    |  - retrieval_log  |
                                    +--------+----------+
                                             |
                                    +--------v----------+
                                    | Web UI            |
                                    | (React/Vite)      |
                                    | Desktop-first     |
                                    | Voice input       |
                                    +-------------------+

V2: Native Swift macOS app replaces Web UI
    Direct filesystem access, menu bar, always-on
```

---

## HeliconCube Schema

```python
{
    "id": "gc_abc123",
    "source": "claude-code",           # connector that produced it
    "source_ref": "session_9ea00c3e",  # original session/file/commit
    "type": "file_created",            # file_created | decision | draft | code | pattern | ...
    "content": "...",                  # actual content or snippet
    "content_hash": "sha256:...",      # for dedup / change detection
    "created_at": "2026-06-24T...",
    "valid_from": "2026-06-24T...",
    "last_reinforced": "2026-06-24T...",
    "confidence": 0.85,                # Weibull decay applied (κ per type)
    "review_status": "pending",        # pending | approved | revised | killed | ignored
    "review_count": 0,
    "spin_count": 0,                   # times discussed without file change
    "novelty_score": 0.72,             # SAGE-style: how novel was this at ingestion
    "tags": ["content", "linkedin"],
    "metadata": {}                     # connector-specific data
}
```

---

## Build Plan

### Actual pace

| Day | Planned | Actual | Status |
|-----|---------|--------|--------|
| 1-2 | Connectors + HeliconCube model | 5 connectors (CC, Obsidian, Git, ChatGPT, Cursor), 1268 memories | DONE |
| 3 | Qwen Cloud integration | Qwen client working (qwen-plus via DashScope) | DONE |
| 4 | SQLite + forgetting engine | 6-table schema, Ebbinghaus decay, score, patterns | DONE |
| 5 | Audit engine + FastAPI | 4-axis audit (82 findings), 18 API endpoints verified | DONE |
| 6-7 | React frontend | Full web UI with 4 tabs, filters, keyboard shortcuts | DONE |
| 8 | Voice + UX polish | Web Speech API, Scandinavian-minimal redesign | DONE |
| 9 | Alibaba ECS deploy | Docker + compose ready, blocked on KYC (~Jun 28) | BLOCKED |
| 10-11 | Data quality + learning loops | 91 reviews seeded, 6 patterns extracted, Qwen health report | DONE |
| 12 | Architecture diagram + README | SVG diagram, README updated, MIT license | DONE |
| 13 | FTS5 + Knowledge Graph | FTS5 search, entity extraction (41 entities, 605 edges), force-directed viz | DONE |
| 14 | MCP Server | 6-tool MCP server (helicon_health, helicon_stale, helicon_search, etc.) | DONE |
| 15 | Memory Consolidation | "Sleep" cycles, cluster detection (30 clusters), batch consolidation | DONE |
| 16 | Contradiction Resolution | Side-by-side comparison UI, one-click resolution | DONE |
| 17 | Retrieval Learning (Loop 4) | retrieval_log tracking, precision computation on every review | DONE |
| 18 | Deploy + Demo | Alibaba Function Compute (ECS dropped on KYC, Jul 3; see DEPLOY-FC.md) + Cloud Shell proof, 3-min video | NEXT |
| 19 | Submit | Devpost | Deadline: Jul 20 (2pm PDT) |

Where that plan landed, as of 2026-07-15: ~90 API endpoints across 22 routers, 14 web tabs, 24 tables, an MCP server with 14 tools, and 43 CLI commands. These are checked against source by `python3 -m helicon.docdrift`, so recompute rather than trust this line.

---

## Demo Script (3 min)

**0:00-0:15** Hook: "13 agents ran last week across Claude Code, Cursor, and ChatGPT. I reviewed 3 outputs. Shipped zero. Most memory systems would store that sentence. Mount Helicon knows it from watching my behavior."

**0:15-0:45** Layer 1 - Extraction: Real HeliconCubes from 208 Claude Code transcripts and 103 memory files. A 57-day LinkedIn post (confidence: 0.0001, Weibull decay with κ=1.8 cliff). Two unreviewed resumes. A memory file that contradicts another. Novelty gate caught 14 redundant entries at ingestion.

**0:45-1:15** Layer 2 - Review patterns: Voice review a card. Mount Helicon updates behavioral model. "You review code in 24h (confidence: 0.91, 47 data points). Content sits 14 days (confidence: 0.87). This post discussed in 6 sessions, file changed twice. Kill prediction: 91%."

**1:15-1:45** Layer 2 - Spin detection: "7 planning documents for content publishing. Zero posts published. Spin score: critical."

**1:45-2:30** Layer 3 - Meta-audit: Three-axis results. Temporal: "status file from May 29 references 'this week' actions that are 27 days old." Factual: "project_portfolio.md says V3, project_paris_portfolio.md says Fable version. Which is current?" Logical: "feedback_stop_being_cautious.md and feedback_test_before_prompt.md may conflict." Confidence decay shown. Human confirms prune. SSGM gate validates. Memory sharpens.

**2:30-2:45** Helicon Score: 12 → 38 after reviewing 8 items. "Killing counts. Ignoring doesn't."

**2:45-3:00** Close: "Mem0 stores. Letta organizes. Zep timestamps. Mount Helicon audits. Most memory agents remember what you said. Mount Helicon remembers what you did, checks its own work, and works with any agent platform."

---

## What Makes This Win MemoryAgent

Most submissions: chatbot that remembers your name. One layer of memory. One platform.

Mount Helicon has three layers and works with any agent:
1. **Extraction** - pluggable connectors, SAGE novelty gate (most stop here)
2. **Review patterns** - behavioral memory with Weibull decay (not conversational)
3. **Meta-audit** - three-axis audit, SSGM gates, anti-confabulation (nobody else does this)

Built on established memory-systems patterns and taken further — versioned memory units, multi-axis audit, non-uniform decay, retrieval learning — with the identity/phantom-coherence layer and the rulings-become-law loop being our own. Grounded in the literature, not a reimplementation of it.

Real data: 208 Claude Code transcripts (49MB), 103 memory files (444K), 150+ Obsidian files, 652 contacts. Zero fake data.

---

## Resume Value

Fills two identified skills gaps:
1. **"No public agent artifact"** → open-source agent memory product backed by published ML research
2. **"Eval thin"** → the audit layer IS an evaluation system for memory quality

Demonstrates: research-to-product translation (6 papers → shipping code), ML-informed architecture, evaluation system design, production memory engineering.

---

## Open Questions

1. **Auth?** Simple password for demo, or none?
2. **Data sync:** CLI push from local to ECS? rsync? Git-based?
3. **SQLite vs vector DB:** Start with SQLite FTS5 for search. Add embeddings later if needed?
4. **Qwen model:** qwen3-plus for everything, or qwen3-235b for audit passes?
