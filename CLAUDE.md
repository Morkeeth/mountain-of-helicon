# Mountain of Helicon

Three-layer memory system for AI agent output. Extracts what agents built, learns how the human reviews, and audits its own memory for staleness and contradictions.

## What it does

- **Layer 1:** Extracts agent output from Claude Code transcripts, Obsidian, git, and coding-agent *rules* files (CLAUDE.md / AGENTS.md / .cursorrules / .clinerules / copilot-instructions), each split into section-level memories so regression can catch a single rule drifting
- **Layer 2:** Learns review patterns (velocity, shipping rates, spin detection, kill prediction)
- **Layer 3:** Audits its own stored patterns. Flags stale memories, contradictions, low-confidence patterns. Proposes prunes. Human reviews the memory review (meta-loop).

## Hackathon

- **Track:** Qwen Cloud Global AI Hackathon - MemoryAgent
- **Deadline:** Jul 20, 2026, 2pm PDT (verified at devpost source Jul 13; the old "Jul 9" was stale)
- **Prize:** $10K ($7K cash + $3K Alibaba Cloud credits)
- **Requirements:** Qwen Cloud API, Alibaba Cloud deployment, open source, 3-min demo video

## Stack

- Python (CLI scanner + FastAPI backend)
- Qwen Cloud API (qwen3.6-flash/plus + qwen3.7-max via OpenAI-compatible SDK)
- Distribution: BYOK + local-first. v0.1 advertises no hosted personal-store
  service; container/Function Compute files are deployment starting points, not
  a production availability claim.
- SQLite + FTS5 + numpy embeddings (41 tables: helicon_cubes, reviews, patterns, audit_log, retrieval_log, scan_log, entities, edges, entity_aliases, consolidations, qwen_cache, session_summaries, triage_log, eval_runs, score_history, battery_history, playbooks, memory_utility, cube_embeddings, context_snapshots, regret_events, rules, route_evidence, run_cards, judge_runs, govern_batches, task_runs, context_packets, context_packet_items, run_captures, run_events, prompt_library, doorway_cold, doorway_gate_cache, setup_snapshots, work_wagers, work_evidence, work_skill_reviews, next_moves, surface_opens, weekly_measurements), plus the cubes_fts FTS5 index. The live store held 47 tables on 2026-08-20 (`SELECT COUNT(*) FROM sqlite_master WHERE type='table'`) and grows on every scan, so the source CREATE TABLE count of 41 is what this check grades
- React/Vite (findings-first dashboard: HEALTH / FINDINGS / LOG primary, Graph + Projects secondary)
- Web Speech API (voice input for reviews)
- MCP Server (23 tools for agent self-audit + context injection)
- Auto-triage engine (autonomous kill/keep from patterns learned on HUMAN reviews only)
- CLI (`helicon init/scan/serve/triage/score/stack/optimize/embed/compile/playbooks/consolidate`)

## CLI (plug-and-play)

```bash
pip install -e .           # install with CLI entry point
helicon init                 # auto-detect Claude Code, Cursor, Obsidian, git
helicon scan                 # extract memory items from your sources
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

- ~3,800 live memories of ~6,900 total (2026-07-15; the store grows on every scan, so `helicon doctor` prints today's count). Live memories come from 4 enabled connectors (Claude Code, Git, Obsidian, Skills) plus human resolutions. Cursor memories exist but are all retired; the ChatGPT connector ships but is not enabled and has 0 memories
- Auto-triage rules learned from HUMAN reviews only (auto-triage's own decisions excluded so it can't reinforce its own echo)
- 41 entities, 605 edges in knowledge graph
- 35 routers (130 endpoints), 23 MCP tools, 68 CLI commands (+4 aliases)
- 6 task playbooks
- Q-value utility learning wired into retrieval ranking (reward from human rulings only, so it can't reinforce its own echo)
- Entity-boosted retrieval (41 entities wired)
- Semantic embeddings: text-embedding-v4 (Dashscope), 1024 dims per config.json. NOT all memories: 187 of 4,507 live cubes embedded (4,214 embedding rows mostly cover retired cubes) — measured 2026-08-20; the old "all-MiniLM-L6-v2, 384 dims, all memories embedded" claim was false at the object
- Hybrid search: 60% semantic + 40% FTS5 keyword, numpy vector ops
- Embedding-based consolidation: cosine similarity clustering + Qwen synthesis
- Core Memory Compiler: compiles reviewed memory to injectable files (data/compiled/)

## Honest eval numbers (no self-grading, no divide-by-zero)

- Composite: **~67** (as of 2026-07-13; run `helicon eval` to recompute. Retrieval P@3 + MRR + decay-AUC; audit excluded, no labeled ground truth)
- Retrieval: P@3 0.615, MRR 0.596 (n=13, auto-built internal benchmark, one label/query - disclose this)
- Decay predicts human kills: **rank-AUC 0.781** (mean confidence of killed memories 0.141 vs approved 0.268) - a real, independent signal
- Consolidation: ~9-10x fewer tokens (char-estimated), Qwen-judged quality favors synthesis (self-graded, show as direction not proof)

## Known gaps (do not overclaim in demo)

- Q-value loop is wired but dormant (few memories moved); surface->reward cycle not yet exercised in production
- context_impact is display-only; not fed back into ranking
- Write-back to ~/.claude/skills/ (inject_into_claude_code) is not wired to any surface; the pull path (helicon_context MCP) is the working half of the loop
