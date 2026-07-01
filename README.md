# GLAZE

**Agent-agnostic memory audit system.** Most memory systems store what you said. GLAZE watches what you did, checks its own work, and flags when memory goes stale.

Built for the [Qwen Cloud Global AI Hackathon](https://qwencloud-hackathon.devpost.com/) -- Track 1: MemoryAgent.

## The Problem

Production memory accuracy drops to **49% after 30 days** at 38% staleness rate (Mem0 ECAI 2025 research). AI agents accumulate memory files, transcripts, and decisions without review. Mem0 ($24M raised, 48K stars) stores. Letta ($10M) organizes. Zep timestamps. **Nobody audits.** GLAZE does.

## Three Layers

### Layer 1: Extraction
Five pluggable connectors scan agent output from any platform:
- **Claude Code** -- JSONL transcripts + memory `.md` files
- **Obsidian** -- Vault markdown with YAML frontmatter
- **Git** -- Commit history across repositories
- **ChatGPT** -- Export parser for `conversations.json`
- **Cursor** -- Memory banks and `.cursorrules` files

Each item becomes a **GlazeCube** -- a versioned memory unit (inspired by MemOS) with source, confidence, content hash, review status, and decay parameters. SAGE-style novelty gate (ADD/NOOP/MERGE) prevents redundant storage at ingestion.

### Layer 2: Review Pattern Learning
GLAZE learns *how you review*, not what you say:
- **Weibull forgetting curves** -- `w(t) = exp(-(t/eta)^kappa)` with per-type shape. kappa>1 = cliff decay (code, drafts). kappa<1 = long tail (decisions, archives). From SSGM/LiCoMemory.
- **Auto-triage** -- after enough reviews, GLAZE derives rules and makes its own kill/approve decisions. Human only reviews uncertain items.
- **Spin detection** -- topics discussed in 4+ sessions without file changes
- **Kill prediction** -- historical kill rate by type and age
- **Glaze Score** -- percentage of memory reviewed and acted on

### Layer 3: Meta-Audit
The system checks its own stored patterns:
- **Temporal audit** -- "this week" in a 27-day-old file
- **Factual audit** -- contradicting memories about the same topic (Qwen-enhanced)
- **Decay audit** -- cubes below 5% confidence, never reviewed
- **Pattern staleness** -- patterns with low data points going stale
- **Anti-confabulation** -- challenge oldest patterns against fresh evidence (Honest Lying, 2025)
- **SSGM consistency gates** -- verify updates don't create new contradictions

## Project Intelligence

GLAZE groups cubes by project tag and computes per-project metrics:
- **Spin score** = sessions / shipped items. Over 3x = pure spin.
- **Ship rate** = approved / reviewed. 0% = no output.
- **Decay velocity** = how fast a project's memory is decaying
- **Urgency scoring** = weighted combination of spin + staleness + backlog + decay + momentum

The Focus tab shows ranked projects with one-line actions: "Stop planning, start shipping. 4 sessions per shipped item." or "Stale 62d. Either push a commit or archive."

## Advanced Features

### Knowledge Graph
Entity extraction from all cubes (projects, tools, concepts). Force-directed visualization with co-occurrence edges and contradiction edges (red). 65 entities, 546 edges from real data.

### Memory Consolidation ("Sleep" Cycles)
Neuroscience-inspired batch consolidation. Groups related cubes by topic overlap, merges them into higher-level consolidated memories. Raw cubes become episodes become schemas.

### Auto-Triage Engine
After enough human reviews, GLAZE derives triage rules from behavior. If 97% of code items get killed and confidence is below 10%, auto-kill. On first run, auto-triage handled 585 out of 1,268 cubes autonomously, pushing the Glaze Score from 7% to 53.6% without a single human decision.

### MCP Server (8 tools)
GLAZE exposes itself as an MCP tool so AI agents can audit their own memory mid-conversation:

| Tool | Description |
|------|-------------|
| `glaze_health` | Memory score and stats |
| `glaze_stale` | Find decayed memories below threshold |
| `glaze_search` | FTS5 full-text search across all cubes |
| `glaze_contradictions` | Active factual conflicts |
| `glaze_recent_reviews` | What the human approved/killed |
| `glaze_patterns` | Learned behavioral patterns |
| `glaze_context` | Proactive memory injection -- describe your task, get ranked memories |
| `glaze_triage` | Trigger auto-triage from agent context |

### CLI (plug-and-play)

```bash
pip install -e .
glaze init          # auto-detect Claude Code, Cursor, Obsidian, git repos
glaze scan          # extract memory into GlazeCubes
glaze serve         # start web UI on :8420
glaze triage        # run auto-triage from learned patterns
glaze score         # show Glaze Score + decay by type
glaze stack         # audit your AI tool setup
glaze optimize      # LLM-powered optimization suggestions
```

## Research Foundation

| Technique | Source | How GLAZE Uses It |
|-----------|--------|-------------------|
| GlazeCube schema | MemOS (SJTU, 2025) | Versioned memory units with metadata |
| Three-axis audit | Memory Bear (Dec 2025) | Temporal, factual, logical consistency |
| Weibull decay | SSGM (Mar 2026) / LiCoMemory | Non-uniform forgetting: kappa per type |
| Novelty gate | SAGE (May 2026) | ADD/NOOP/MERGE at ingestion |
| Consistency gates | SSGM Framework (Mar 2026) | Verify before committing updates |
| Anti-confabulation | Honest Lying (May 2026) | Challenge patterns against evidence |
| Retrieval learning | MetaMem (ACL 2026) | Track surfaced vs acted-on |
| Session summaries | Hermes Agent (Feb 2026) | Structured docs from completed sessions |
| Self-evolution | Hermes (Feb 2026) | Auto-triage from learned patterns |
| Context injection | Lossless-Claw/OpenClaw | Proactive MCP memory delivery |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLite + FTS5 (13 tables)
- **Frontend**: React 19, TypeScript, Vite 8, Tailwind CSS
- **AI**: Qwen Cloud API (turbo/plus/max) via OpenAI-compatible SDK
- **Deploy**: Alibaba Cloud ECS, Docker
- **Voice**: Web Speech API for review input
- **MCP**: JSON-RPC 2.0 stdio server (8 tools)
- **CLI**: pip-installable with 7 commands

## Quick Start

### Option A: CLI (recommended)

```bash
git clone https://github.com/MorkeethHQ/glaze.git
cd glaze
pip install -e .

glaze init                    # auto-detects your AI tools
# Edit config.json: add your Qwen API key
glaze scan                    # extracts memory into GlazeCubes
glaze serve                   # opens web UI at http://localhost:8420
```

### Option B: Manual

```bash
git clone https://github.com/MorkeethHQ/glaze.git
cd glaze

cp config.example.json config.json
# Edit config.json: add Qwen API key, adjust paths

pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
cp -r web/dist static

python3 scripts/seed.py
python3 -m uvicorn glaze.api.app:app --port 8420
```

### Option C: Docker

```bash
docker compose up -d
# Pre-seed: copy your local data/glaze.db into the container volume
```

### MCP Server

Add to your Claude Code config (`.claude.json`):

```json
{
  "mcpServers": {
    "glaze": {
      "command": "python3",
      "args": ["-m", "glaze.mcp_server"],
      "cwd": "/path/to/glaze"
    }
  }
}
```

Then ask Claude Code: "What's my memory health?" and it will call `glaze_health`.

## API (42 endpoints)

### Core
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check + cube count |
| GET | `/api/cubes` | List cubes with filters and sorting |
| GET | `/api/cubes/{id}` | Single cube detail |
| POST | `/api/scan` | Trigger fresh scan |

### Review
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/review` | Submit review decision + voice notes |
| GET | `/api/reviews` | Review history |
| GET | `/api/score` | Glaze Score with breakdown |
| POST | `/api/decay` | Run Weibull decay pass |
| GET | `/api/decay/stats` | Confidence stats by type |

### Patterns
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/patterns` | Learned behavioral patterns |
| POST | `/api/patterns/extract` | Extract new patterns |
| GET | `/api/patterns/spin` | Spin detection results |
| GET | `/api/patterns/kill-candidates` | Kill candidates by type/age |
| GET | `/api/patterns/shipping-rates` | Ship/kill rates by type |

### Audit
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/audit` | Audit findings (245 real findings) |
| POST | `/api/audit/run` | Run four-axis audit |
| POST | `/api/audit/confirm` | Confirm/reject finding |

### Auto-Triage
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/triage/run` | Execute auto-triage |
| GET | `/api/triage/stats` | Triage statistics |
| GET | `/api/triage/rules` | Derived triage rules |

### Knowledge Graph
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/graph` | Full graph (nodes + edges) |
| POST | `/api/graph/build` | Build graph from cubes |
| GET | `/api/graph/entity/{id}` | Entity detail + related cubes |

### Search & Sessions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/search` | FTS5 full-text search |
| POST | `/api/search/rebuild` | Rebuild FTS index |
| GET | `/api/sessions` | Session summaries |

### Consolidation
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/consolidations` | Consolidated memories |
| GET | `/api/consolidations/clusters` | Topic clusters |
| POST | `/api/consolidations/run` | Run sleep cycle |

### Project Intelligence
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | All projects with rollup stats |
| GET | `/api/projects/recommend` | Ranked recommendations by urgency |
| GET | `/api/projects/weekly` | Weekly touch/ship summary |
| GET | `/api/projects/context-switches` | Context-switch analysis |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/connectors` | Connector status |
| GET | `/api/timeline` | Ingestion timeline |
| GET | `/api/report` | Qwen-powered health report |

## Design

Scandinavian-minimal dark UI. Inter typeface, monochromatic zinc palette with restrained amber accent. Typography-driven hierarchy, generous whitespace, ghost buttons.

5 tabs: **Focus** (project intelligence + recommendations) | **Review** (card-by-card memory review with voice) | **Audit** (4-axis findings) | **Graph** (force-directed knowledge graph) | **System** (connectors, triage, tokens, setup)

Keyboard shortcuts: `j`/`k` navigate, `a` approve, `r` revise, `k` kill, `/` search.

## License

MIT
