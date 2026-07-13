# Mount Helicon

Three-layer memory system for AI agent output. Extracts what agents built, learns how the human reviews, and audits its own memory for staleness and contradictions.

## What it does

- **Layer 1:** Extracts agent output from Claude Code transcripts, Obsidian, git, and coding-agent *rules* files (CLAUDE.md / AGENTS.md / .cursorrules / .clinerules / copilot-instructions), each split into section-level memory cubes so regression can catch a single rule drifting
- **Layer 2:** Learns review patterns (velocity, shipping rates, spin detection, kill prediction)
- **Layer 3:** Audits its own stored patterns. Flags stale memories, contradictions, low-confidence patterns. Proposes prunes. Human reviews the memory review (meta-loop).

## Hackathon

- **Track:** Qwen Cloud Global AI Hackathon - MemoryAgent
- **Deadline:** Jul 9, 2026
- **Prize:** $10K ($7K cash + $3K Alibaba Cloud credits)
- **Requirements:** Qwen Cloud API, Alibaba Cloud deployment, open source, 3-min demo video

## Stack

- Python (CLI scanner + FastAPI backend)
- Qwen Cloud API (qwen3.6-flash/plus + qwen3.7-max via OpenAI-compatible SDK)
- Distribution: BYOK + local-first; Alibaba Cloud proof via Cloud Shell (ECS dead: KYC, decided Jul 3)
- SQLite + FTS5 + numpy embeddings (18 tables: helicon_cubes, reviews, patterns, audit_log, retrieval_log, scan_log, entities, edges, consolidations, qwen_cache, session_summaries, triage_log, eval_runs, score_history, playbooks, memory_utility, cube_embeddings, context_snapshots)
- React/Vite (findings-first dashboard: HEALTH / FINDINGS / LOG primary, Graph + Projects secondary)
- Web Speech API (voice input for reviews)
- MCP Server (11 tools for agent self-audit + context injection)
- Auto-triage engine (autonomous kill/keep from patterns learned on HUMAN reviews only)
- CLI (`helicon init/scan/serve/triage/score/stack/optimize/embed/compile/playbooks/consolidate`)

## CLI (plug-and-play)

```bash
pip install -e .           # install with CLI entry point
helicon init                 # auto-detect Claude Code, Cursor, Obsidian, git
helicon scan                 # extract memory items into HeliconCubes
helicon serve                # start web UI on :8420
helicon triage               # run auto-triage from learned patterns
helicon triage --dry-run     # preview what would be triaged
helicon score                # show Helicon Score + decay by type
helicon stack                # audit your AI tool setup
helicon optimize             # LLM-powered optimization suggestions
helicon battery "<task>"     # context-quality battery on retrieved memory (relevance/freshness/redundancy/thinness + LLM contradiction/grounding); every verdict prints last-scan age
helicon doctor               # health check: PATH, config, Qwen key, DB, last scan
helicon mcp                  # run the MCP server on stdio (bare `helicon` stays a CLI)
```

## Dev Commands

```bash
# Backend (dev mode)
python3 -m uvicorn helicon.api.app:app --port 8420

# Frontend (dev mode)
cd web && npx vite --port 5173

# MCP Server
python3 -m helicon.mcp_server

# Full pipeline (legacy)
python3 scripts/seed.py
python3 -c "from helicon.config import load_config; from helicon.db import init_db, rebuild_fts; from helicon.graph import build_graph; c=load_config(); conn=init_db(c['db_path']); rebuild_fts(conn); build_graph(conn)"
```

## Key constraint

Zero fake data. Demo uses Oscar's real Claude Code transcripts (210+), Obsidian vault (150+ files), and git repos.

## Current Stats

- ~2,800 active cubes (3,800 total) from 5 connectors (Claude Code, Git, Obsidian, Cursor AI tracking, ChatGPT)
- Auto-triage rules learned from HUMAN reviews only (auto-triage's own decisions excluded so it can't reinforce its own echo)
- 41 entities, 605 edges in knowledge graph
- 14 routers, 11 MCP tools, 20 CLI commands
- 6 task playbooks
- Q-value utility learning wired into retrieval ranking (reward from human rulings only, so it can't reinforce its own echo)
- Entity-boosted retrieval (41 entities wired)
- Semantic embeddings: all-MiniLM-L6-v2, 384 dims, all cubes embedded
- Hybrid search: 60% semantic + 40% FTS5 keyword, numpy vector ops
- Embedding-based consolidation: cosine similarity clustering + Qwen synthesis
- Core Memory Compiler: compiles reviewed memory to injectable files (data/compiled/)

## Honest eval numbers (no self-grading, no divide-by-zero)

- Composite: **74.2** (retrieval P@3 + MRR + decay-AUC; audit excluded, no labeled ground truth)
- Retrieval: P@3 0.692, MRR 0.615 (n=13, auto-built internal benchmark, one label/query - disclose this)
- Decay predicts human kills: **rank-AUC 0.877** (mean confidence of killed cubes 0.017 vs approved 0.256) - a real, independent signal
- Consolidation: ~9-10x fewer tokens (char-estimated), Qwen-judged quality favors synthesis (self-graded, show as direction not proof)

## Known gaps (do not overclaim in demo)

- Q-value loop is wired but dormant (few cubes moved); surface->reward cycle not yet exercised in production
- context_impact is display-only; not fed back into ranking
- Write-back to ~/.claude/skills/ (inject_into_claude_code) is not wired to any surface; the pull path (helicon_context MCP) is the working half of the loop
