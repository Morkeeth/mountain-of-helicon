# Mount Helicon

**The test and trust layer for AI agent memory.** Memory systems store what your agent said. Mount Helicon regression-tests what it retrieves, scores whether that context is still true, and retires what isn't. CI for memory.

Built for the [Qwen Cloud Global AI Hackathon](https://qwencloud-hackathon.devpost.com/) -- Track 1: MemoryAgent.

## The Problem

Production memory accuracy drops to **49% after 30 days** at a 38% staleness rate (Mem0 ECAI 2025 research). Qwen3.7-Max runs autonomously for 35 hours making 1000+ tool calls -- and nobody audits what accumulates in its memory over those 35 hours. Mem0 ($24M raised) stores. Letta ($10M) organizes. Zep timestamps. **Nobody tests.** Stale context presented as current fact breaks workflows silently: retrieval benchmarks measure whether memory is *found*, never whether it is still *true*.

Mount Helicon is the exam. It runs on real data only -- this repo was built and tested against its author's live 2,800-cube memory, and it has failed its own audits more than once (see receipts in the demo).

## Quick Start (60 seconds, $0)

```bash
git clone https://github.com/MorkeethHQ/mount-helicon.git
cd mount-helicon
pip install -e .

helicon init        # auto-detects Claude Code, Cursor, Obsidian, git
helicon scan        # extract memory into HeliconCubes
helicon doctor      # health check: PATH, config, key, DB, last scan
helicon battery "what am I working on"   # context-quality verdict
helicon serve       # dashboard at http://localhost:8420
```

**Bring your own Qwen key (BYOK).** Get one free on the [Alibaba Cloud Model Studio free tier](https://www.alibabacloud.com/en/product/modelstudio), set `QWEN_API_KEY` or put it in `config.json`. The OpenAI-compatible endpoint is `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. **Keyless degrade:** without a key every deterministic test still runs; only the two LLM-judged tests (Contradiction, Grounding) switch off -- the battery says so instead of faking a verdict.

Judge reproduction from a clean machine is scripted: `bash scripts/judge-check.sh` clones, installs, boots, and fails loudly on any crack. `scripts/cloudshell-run.sh` is the same flow inside Alibaba Cloud Shell.

## Headline Features

- **`helicon snapshot`** -- regression tests for retrieved context. Capture what a task retrieves today; `snapshot check` fails when tomorrow's retrieval drifts. CI for memory.
- **`helicon battery "<task>"`** -- context-quality battery on what a task retrieves: Relevance, Freshness, Redundancy, Thinness (deterministic) + Contradiction, Grounding (judged live by Qwen). Verdict: HEALTHY / DEGRADED / BROKEN. Every verdict prints the age of the last scan, because a DEGRADED verdict is uninterpretable if the scan itself is stale. `--json` for scripts and CI.
- **`helicon reconcile`** -- timely forgetting. Re-scans sources and retires cubes reality no longer contains (dry-run by default, never touches human decisions). On the live DB it retired 20 superseded memories in its first run.
- **`helicon fix-skills`** -- write-back: Qwen writes missing descriptions into your agent skill files (dry-run by default, `.bak` backups). It fixed 7 of this project's own skills.
- **`helicon doctor`** -- five checks (PATH, config, key, DB, last scan), exit 1 on failure. The front door to a daily loop.
- **`helicon rule "<natural language>"`** -- prompted rules. Qwen compiles your sentence to a restricted predicate (whitelisted fields, never code); before approval you see coverage, samples, empirical precision against YOUR past decisions, and conflicts with other rules. One approved rule governs hundreds of items; applied rules are never counted as human evidence.
- **The regret ledger** -- killed memories become a ghost list (LeCaR cache-eviction mechanics). When retrieval wants one back, a time-decayed regret event blames the exact decision that killed it, and FINDINGS shows "you retired this, retrieval wanted it 2x since -- restore?". Wrong forgetting is measured, not assumed.
- **`helicon_flag` over MCP** -- point-of-use correction. Injected memories carry id + last_verified + used_count; the agent (or you, through it) flags stale/wrong/useful in one call. Flags become findings the human confirms -- the agent proposes, it never deletes.

## Three Layers

**Layer 1 -- Extraction.** Nine pluggable connectors: Claude Code (JSONL transcripts + memory files), Obsidian, git history, ChatGPT exports, Cursor, agent rules files, plus read-side adapters for **Letta MemFS**, **Graphiti** (bi-temporal metadata mapped into cubes; 17 tests), and **Mem0** -- the store Alibaba's own agent-memory docs recommend (Model Studio Memory Bank, Mem0 + Hologres, Mem0 + AnalyticDB), so Mount Helicon audits the stacks Alibaba itself suggests. Rewritten and expiring Mem0 memories carry their temporal fields into the freshness tests. Agent *rules* files (CLAUDE.md, AGENTS.md, .cursorrules) are split into section-level cubes so regression catches a single rule drifting. Every item becomes a **HeliconCube**: versioned memory unit with source, confidence, content hash, review status, decay parameters (MemOS-inspired). A SAGE-style novelty gate (ADD/NOOP/MERGE) prevents redundant storage.

**Layer 2 -- Review pattern learning.** Weibull forgetting curves with per-type shape (cliff decay for code, long tail for decisions). Auto-triage derives kill/approve rules from HUMAN reviews only -- its own decisions are excluded so it cannot reinforce its own echo. On first run it handled 585 of 1,268 cubes autonomously. Spin detection, kill prediction, Helicon Score.

**Layer 3 -- Meta-audit.** The system audits its own stored patterns: temporal staleness ("this week" in a 27-day-old file), factual contradictions (Qwen-judged), decay, pattern staleness, anti-confabulation challenges. The human reviews the memory review.

## Qwen Cloud API usage (where the LLM is load-bearing)

| Tier | Model | Used for |
|------|-------|----------|
| fast | `qwen3.6-flash` | Cube summarization, novelty gate, skill descriptions |
| default | `qwen3.6-plus` | Battery judging (Contradiction, Grounding), factual audit |
| deep | `qwen3.7-max` | Consolidation synthesis, optimization reports |

All calls go through the OpenAI-compatible endpoint `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` with a per-call SQLite response cache and per-operation cost tracking (`/api/tokens`). The two subjective battery tests are judged live and tagged `(qwen)` in output; if the judge call fails, the battery falls back to deterministic-only rather than fabricating a verdict.

## MCP Server (12 tools)

Agents audit their own memory mid-conversation. Add to `.claude.json`:

```json
{
  "mcpServers": {
    "helicon": { "command": "helicon", "args": ["mcp"], "cwd": "/path/to/mount-helicon" }
  }
}
```

| Tool | Description |
|------|-------------|
| `helicon_health` | Memory score and stats |
| `helicon_stale` | Decayed memories below threshold |
| `helicon_search` | Hybrid FTS5 + semantic search |
| `helicon_contradictions` | Active factual conflicts |
| `helicon_recent_reviews` | What the human approved/killed |
| `helicon_patterns` | Learned behavioral patterns |
| `helicon_context` | Proactive memory injection for a task -- every memory carries its id, last_verified, used_count |
| `helicon_flag` | Point-of-use correction: flag a memory stale/wrong/useful by id; stale/wrong become findings the human confirms |
| `helicon_playbook` | Task playbooks from review patterns |
| `helicon_compile` | Compile reviewed memory to injectable files |
| `helicon_triage` | Trigger auto-triage |
| `helicon_consolidate` | Run a consolidation (sleep) cycle |

The full JSON-RPC 2.0 handshake (initialize, tools/list, tools/call) is exercised in the receipts; `helicon mcp` runs the server on stdio, so the bare CLI never silently becomes a server.

## CLI (22 commands)

`init` `scan` `reconcile` `fix-skills` `serve` `triage` `review` `snapshot` `battery` `report` `rule` `doctor` `mcp` `score` `stack` `optimize` `eval` `embed` `playbooks` `compile` `consolidate` `eval-consolidation`

`helicon report` prints a **MemoryAgent Compliance Report**: the track's four sub-goals (efficient storage/retrieval, timely forgetting, recall under limited context windows, cross-session accuracy) scored live from your real memory, thresholds printed with the numbers. Any memory stack a connector can scan could be graded by the same exam.

Doc honesty is enforced: `python3 -m helicon.docdrift` compares this README's numeric claims against counts computed from source, and it runs in the test suite — stale docs fail the build. (It caught this very README claiming 20 commands the hour the 21st landed.)

Everything destructive is dry-run by default and takes `--apply`.

## Honest eval numbers

- Composite: **74.2** (retrieval P@3 + MRR + decay-AUC; audit axis excluded -- no labeled ground truth).
- Retrieval: P@3 0.692, MRR 0.615. Small internal benchmark (n=13, one label per query) -- disclosed, not hidden.
- **Decay predicts human kills at rank-AUC 0.877** (mean confidence of killed cubes 0.017 vs approved 0.256). A real, independent signal.
- Consolidation: ~9-10x fewer tokens; Qwen-judged quality favors synthesis (self-graded, shown as direction, not proof).
- Zero fake data anywhere: the demo DB is the author's real Claude Code transcripts (210+), Obsidian vault, and git repos.

## Research foundation

| Technique | Source | How Mount Helicon uses it |
|-----------|--------|---------------------------|
| Versioned memory cubes | MemOS (SJTU, 2025) | HeliconCube schema |
| Three-axis audit | Memory Bear (Dec 2025) | Temporal, factual, logical consistency |
| Weibull decay | SSGM (Mar 2026) / LiCoMemory | Non-uniform forgetting, kappa per type |
| Novelty gate | SAGE (May 2026) | ADD/NOOP/MERGE at ingestion |
| Anti-confabulation | Honest Lying (May 2026) | Challenge patterns against evidence |
| Retrieval learning | MetaMem (ACL 2026) | Track surfaced vs acted-on |
| Utility-aware ranking | MemRL-inspired | Q-value learning wired into retrieval |

## Architecture

- **Backend:** Python 3.12, FastAPI (72 endpoints), SQLite + FTS5 (21 tables), numpy embeddings (all-MiniLM-L6-v2, 384-dim, hybrid 60% semantic / 40% keyword search)
- **Frontend:** React 19, TypeScript, Vite, findings-first dashboard -- HEALTH (the mountain: one tile per battery task, a terracotta crack per broken one), FINDINGS (every failed check with why, evidence, action), LOG (receipts), plus Graph and Projects
- **AI:** Qwen Cloud API via OpenAI-compatible SDK (see table above)
- **Distribution:** BYOK + local-first. Proof-of-run on Alibaba Cloud via Cloud Shell (`scripts/cloudshell-run.sh`)

## License

MIT
