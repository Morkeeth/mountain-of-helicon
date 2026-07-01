# GLAZE Architecture

```
                            ANY AI AGENT PLATFORM
    ┌─────────────┬──────────────┬───────────┬──────────┬──────────┐
    │ Claude Code │   Obsidian   │    Git    │ ChatGPT  │  Cursor  │
    │   JSONL     │   Markdown   │  Commits  │   JSON   │ Memory   │
    └──────┬──────┴──────┬───────┴─────┬─────┴────┬─────┴────┬─────┘
           │             │             │          │          │
           └─────────────┴──────┬──────┴──────────┴──────────┘
                                │
                    ┌───────────▼───────────┐
                    │   SAGE Novelty Gate   │
                    │   ADD / NOOP / MERGE  │
                    │   (qwen-turbo)        │
                    └───────────┬───────────┘
                                │
    ════════════════════════════╪════════════════════════════════════
     LAYER 1: EXTRACTION       │
    ════════════════════════════╪════════════════════════════════════
                                │
                    ┌───────────▼───────────┐
                    │      GlazeCubes       │
                    │  1,268 versioned      │
                    │  memory units         │
                    │  (MemOS-inspired)     │
                    └───────────┬───────────┘
                                │
    ════════════════════════════╪════════════════════════════════════
     LAYER 2: REVIEW PATTERNS  │
    ════════════════════════════╪════════════════════════════════════
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
    ┌─────────▼──────┐ ┌───────▼────────┐ ┌──────▼───────┐
    │ Weibull Decay  │ │ Review Feed    │ │ Auto-Triage  │
    │ w=exp(-(t/η)^κ)│ │ sorted by      │ │ GLAZE makes  │
    │ per-type shape │ │ learned urgency│ │ its own       │
    │ (SSGM/LiCo)   │ │                │ │ decisions     │
    └────────────────┘ └───────┬────────┘ └──────┬───────┘
                               │                 │
                     ┌─────────▼─────────┐       │
                     │  Human Reviews    │       │
                     │  only uncertain   │       │
                     │  items remain     │◄──────┘
                     └─────────┬─────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼─────────┐ ┌────▼──────────┐
    │ Pattern        │ │ Spin Detection │ │ Retrieval     │
    │ Learning       │ │ N sessions,    │ │ Learning      │
    │ (qwen-plus)    │ │ 0 file changes │ │ (MetaMem)     │
    └────────────────┘ └────────────────┘ └───────────────┘
                                │
    ════════════════════════════╪════════════════════════════════════
     LAYER 3: META-AUDIT       │
    ════════════════════════════╪════════════════════════════════════
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
    ┌─────────▼──────┐ ┌───────▼────────┐ ┌──────▼───────┐
    │ 4-Axis Audit   │ │ Knowledge      │ │ Memory       │
    │ temporal       │ │ Graph          │ │ Consolidation│
    │ factual        │ │ 65 entities    │ │ "sleep"      │
    │ decay          │ │ 1,289 edges    │ │ cycles       │
    │ pattern stale  │ │ contradiction  │ │ cluster +    │
    │ (Memory Bear)  │ │ edges in red   │ │ merge        │
    │ (qwen-max)     │ │                │ │              │
    └────────────────┘ └────────────────┘ └──────────────┘
              │                 │                 │
              └─────────────────┼─────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Review Drift         │
                    │  Detection            │
                    │  (user model shift)   │
                    └───────────┬───────────┘
                                │
    ════════════════════════════╪════════════════════════════════════
     INFRASTRUCTURE             │
    ════════════════════════════╪════════════════════════════════════
                                │
    ┌───────────────────────────▼───────────────────────────────────┐
    │                      SQLite (13 tables)                      │
    │  glaze_cubes | reviews | patterns | audit_log | retrieval_log│
    │  scan_log | entities | edges | consolidations | qwen_cache   │
    │  session_summaries | triage_log | cubes_fts (FTS5)           │
    └───────────────────────────┬───────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
    ┌────▼──────────┐   ┌───────▼────────┐   ┌────────▼─────────┐
    │ FastAPI       │   │ MCP Server     │   │ Qwen Cloud       │
    │ 42 endpoints  │   │ 8 tools        │   │ Multi-model      │
    │ 12 routers    │   │ JSON-RPC 2.0   │   │ routing          │
    │               │   │ stdio          │   │                  │
    │               │   │                │   │ turbo: extract   │
    │               │   │ glaze_health   │   │ plus: patterns   │
    │               │   │ glaze_stale    │   │ max: audit       │
    │               │   │ glaze_search   │   │                  │
    │               │   │ glaze_contra   │   │ Response cache   │
    │               │   │ glaze_reviews  │   │ Cost tracking    │
    │               │   │ glaze_patterns │   │ Route learning   │
    │               │   │ glaze_context  │   │                  │
    │               │   │ glaze_triage   │   │                  │
    └────┬──────────┘   └────────────────┘   └──────────────────┘
         │
    ┌────▼──────────────────────────────────────────────────────────┐
    │                    React / Vite Web UI                        │
    │  5 tabs: Focus | Review | Audit | Graph | System              │
    │  Project intelligence: rollup, spin, ship rate, recommendations│
    │  Voice input (Web Speech API) | Keyboard shortcuts (j/k/a/r) │
    │  Force-directed graph | Session drift | Token budget          │
    │  Auto-triage preview + execute | Rule confidence display      │
    └──────────────────────────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────────────────────┐
    │                         CLI                                   │
    │  glaze init      Auto-detect Claude Code, Cursor, Obsidian   │
    │  glaze scan      Extract memory into GlazeCubes              │
    │  glaze serve     Start web UI on :8420                        │
    │  glaze triage    Auto-triage from learned patterns            │
    │  glaze score     Show Glaze Score + decay by type             │
    │  glaze stack     Audit AI tool setup                          │
    │  glaze optimize  LLM-powered optimization                    │
    └──────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Agent output (any platform)
  > Connector extracts structured items
  > SAGE novelty gate: ADD / NOOP / MERGE (qwen-turbo)
  > GlazeCube stored with content hash, confidence, type
  > Weibull decay applied per-type (kappa shapes forgetting curve)
  > AUTO-TRIAGE: rules from review history kill/approve high-confidence matches
  > Remaining items surface in review feed sorted by urgency
  > Human reviews only uncertain items: approve / revise / kill + voice
  > Pattern learning extracts behavioral rules (qwen-plus)
  > Session summary generated (Hermes-inspired)
  > 4-axis audit challenges stored patterns (qwen-max)
  > Context-aware prompts inject past decisions (ByteRover pattern)
  > Proactive MCP: agents request relevant context, GLAZE ranks and injects
  > Knowledge graph updated (entities + edges)
  > Drift detection flags behavior changes
  > Consolidation merges related memories ("sleep" cycle)
  > Cycle sharpens with each pass, triage handles more autonomously
```

## Research Citations

| Technique | Source | What GLAZE Uses |
|-----------|--------|-----------------|
| GlazeCube | MemOS (SJTU, 2025) | Versioned memory units with metadata |
| Three-axis audit | Memory Bear (Dec 2025) | Temporal, factual, logical consistency |
| Weibull decay | SSGM (Mar 2026) / LiCoMemory | Non-uniform forgetting: kappa per type |
| Novelty gate | SAGE (May 2026) | ADD/NOOP/MERGE at ingestion |
| Retrieval learning | MetaMem (ACL 2026) | Track surfaced vs acted-on |
| Anti-confabulation | Honest Lying (May 2026) | Challenge stored conclusions |
| Session summaries | Hermes Agent (Feb 2026) | Structured docs from completed sessions |
| Context injection | OpenClaw ByteRover (2026) | Past decisions in audit prompts |
| Efficiency | Coinbase (Jun 2026) | Cache, routing, cost visibility |
| Self-evolution | Hermes (Feb 2026) | Auto-triage from learned patterns |
| Context injection | Lossless-Claw/OpenClaw | Proactive MCP memory delivery |
