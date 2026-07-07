# Mount Helicon

**The test-and-focus layer for AI agent memory.** Mem0 stores it, Letta organizes it, Zep timestamps it — none of them test whether what's remembered is still *true*. Mount Helicon is the exam: it regression-tests what your agent retrieves, scores whether that context is still true, retires what isn't, and turns what's left into your next move — every answer citing the exact memory it came from. **CI for memory, with receipts.**

It sits *on top of any store* (or none), reads any agent's memory read-only — Claude Code, Cursor, Copilot, Cline, ChatGPT, git, Obsidian, or a Mem0/Letta/Graphiti store — and never becomes a store itself.

Built for the [Qwen Cloud Global AI Hackathon](https://qwencloud-hackathon.devpost.com/) -- Track 1: MemoryAgent.

## The Problem

The record is measured and it is bad. Shown two contradicting sources, GPT-4 flags the conflict only **6.3%** of the time -- it just picks one and answers confidently ([WikiContradict, NeurIPS 2024](https://arxiv.org/pdf/2406.13805)). The best frontier model detects that a stored memory has been invalidated **55.2%** of the time ([STALE, 2026](https://arxiv.org/pdf/2605.06527)). **64% of memory-agent recommendation errors trace to outdated memory that was never forgotten** ([Memora, 2026](https://arxiv.org/html/2604.20006v1)), and accuracy on superseded facts collapses from 68% to 28% as session history grows -- 24x more memory buys back zero points: "the bottleneck is memory maintenance, not comprehension" ([Supersede, 2026](https://arxiv.org/html/2606.27472)). Independent production testing of a popular OSS memory store measured **49% effective accuracy after 30 days at a 38% staleness rate** ([RankSquire Infrastructure Lab, 2026](https://ranksquire.com/2026/05/06/long-term-memory-for-ai-agents/)).

The labs know. OpenAI's Agents SDK docs say it verbatim: *"Memory can become stale. Agents are instructed to treat memories as guidance only."* Anthropic's memory-tool freshness strategy is one line: delete files *"that haven't been accessed in a long time."* Alibaba's own AnalyticDB team titled their blog *"Is Your AI Agent Getting Dumber?"* -- and Qwen3.7-Max markets 35-hour autonomous runs as *"resilient to context rot and instruction drift"* with no way for anyone to verify it. Mem0 ($24M) stores. Letta ($10M) organizes. Zep timestamps. Every shipped mitigation is recency deletion, write-time dedup, or "the human should review." **Nobody ships a test that asks: is this stored memory still true?**

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
helicon rot         # the rot exam: 10 documented failure classes, checked live
helicon serve       # dashboard at http://localhost:8420
```

**Bring your own Qwen key (BYOK).** Get one free on the [Alibaba Cloud Model Studio free tier](https://www.alibabacloud.com/en/product/modelstudio), set `QWEN_API_KEY` or put it in `config.json`. The OpenAI-compatible endpoint is `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. **Keyless degrade:** without a key every deterministic test still runs; only the two LLM-judged tests (Contradiction, Grounding) switch off -- the battery says so instead of faking a verdict.

Judge reproduction from a clean machine is scripted: `bash scripts/judge-check.sh` clones, installs, boots, and fails loudly on any crack. `scripts/cloudshell-run.sh` is the same flow inside Alibaba Cloud Shell.

## Three ways to run it (the dashboard is optional)

You don't have to host anything, and you don't need the browser.

- **CLI** — `helicon rot`, `helicon battery "<task>"`, `helicon doctor`, `helicon gold`. The full audit, headless. `helicon watch` runs it on a cron and only pings you when something *new* rots — the ambient, no-browser daily loop.
- **In your IDE / agent (MCP)** — `helicon mcp` exposes 13 tools so your coding agent audits and repairs its own memory mid-conversation: `helicon_context` pulls memory *with provenance*, `helicon_flag` corrects at the point of use, `helicon_stale`/`helicon_contradictions` surface rot. This is the agent-native path — the tool lives inside Claude Code / Cursor, no human dashboard required.
- **Dashboard** (`helicon serve`) — for when you want to sit down and review visually: Next Moves, findings, golden rules.

Packaged as a proper CLI (a `helicon` entry point via `pyproject.toml`), so once it's on PyPI the install is `pipx install mount-helicon` (or `uvx mount-helicon` for zero-install). Today, from the clone: `pip install -e .`, then `helicon init`.

## Headline Features

- **`helicon snapshot`** -- regression tests for retrieved context. Capture what a task retrieves today; `snapshot check` fails when tomorrow's retrieval drifts. CI for memory.
- **`helicon battery "<task>"`** -- context-quality battery on what a task retrieves: Relevance, Freshness, Redundancy, Thinness, Expiry (deterministic) + Contradiction, Grounding (judged live by Qwen). Verdict: HEALTHY / DEGRADED / BROKEN. Every verdict prints the age of the last scan, because a DEGRADED verdict is uninterpretable if the scan itself is stale. `--json` for scripts and CI.
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

## CLI (28 commands)

`init` `scan` `reconcile` `fix-skills` `serve` `triage` `review` `snapshot` `battery` `report` `rot` `gold` `evolve` `resolve` `watch` `alias` `rule` `doctor` `mcp` `score` `stack` `optimize` `eval` `embed` `playbooks` `compile` `consolidate` `eval-consolidation`

`helicon rot` runs **the rot exam**: the 10 documented memory-failure classes in [ROT.md](ROT.md) checked live against your real store -- deterministic, zero LLM calls, free to run daily. On this repo's own store it currently finds rot in 4 of 10 classes and says so — and as of Jul 5 all 10 classes are fully tested, 0 partial.

`helicon watch` makes the exam ambient: scan + selectors + rot exam on a timer (`helicon watch --install` writes the crontab line, every 6h), diffed against the last run. You get a macOS notification and a `drift-report.md` only when something NEW rots — no news, no noise. First run baselines silently.

`helicon gold` compiles **GOLDEN RULES**: the stack's law, built from your rulings, dismissal precedents, approved triage rules, declared renames, canonical sources and standing feedback — every rule with its provenance (a rule without provenance is a vibe). `--inject` writes it to `~/.claude/GOLDEN_RULES.md` (dry-run default, `.bak` kept) so every session can obey it. `helicon evolve` is the night command: scan, every selector, the exam, a gold recompile, and the morning delta — what your stack learned while you slept.

`helicon report` prints a **MemoryAgent Compliance Report**: the track's four sub-goals (efficient storage/retrieval, timely forgetting, recall under limited context windows, cross-session accuracy) scored live from your real memory, thresholds printed with the numbers. Any memory stack a connector can scan could be graded by the same exam.

## Audit a store you don't own

The exam is not limited to your own memory. Any repo with a committed agent-rules file (AGENTS.md, CLAUDE.md, .cursorrules, ...) is a memory store someone's agent obeys every session — so it can be examined:

```bash
bash scripts/demo_public_store.sh          # default: openai/codex AGENTS.md
```

This replays the file across its REAL git history (no staging): ingests an old commit, snapshots retrieval, replays to HEAD, reconciles, runs the rot exam. On openai/codex (27 real commits of AGENTS.md edits, cited by SHA in the output): 5 sections retired as drifted, 1/1 retrieval snapshot regressed — R10 and R8, live, on a store we don't own. Reproducible by anyone.

## The life-OS benchmark — scored against human-labeled rot

On Jul 5 a 5-agent manual audit swept the operator's real second brain (Obsidian vault + Claude Code memory dir), archived 33 stale docs and stamped 21 drifting docs with dated `> **LOUPE` correction banners. Those banners are a labeled dataset of real memory rot. The benchmark ingests the same corpora with the banners stripped (the answer key never enters the input) and scores the deterministic detectors against them:

```bash
python3 scripts/rot_bench_lifeos.py    # read-only on sources, throwaway DB, zero LLM
```

Honest numbers from the first run (232 files, 1,667 section cubes): **6/16 file-level catches, 4/16 strict facet-match** — the output labels the difference itself. What it caught: both merge-status flips (audit doc still said 'NOT patched' after the fix merged), a stale dashboard doc, a dead 7-week-old plan. What it found that the humans missed: a win-count fight (9 vs 10) living in the resume and two application drafts, and 35 files still asserting a dead project name post-rebrand. Named misses, on the roadmap: overlapping-date-range drift (Aug 14-22 vs Aug 15-24 overlap, so interval semantics reads agreement), living-doc supersession without a declared rename, and content-based staleness (a young file asserting old facts).

## Access & trust model (read this before connecting your vault)

A tool that audits your memory reads your memory. That access is scary, so here is exactly what Mount Helicon does with it — from the code, not a promise:

**Reads (always read-only):** your configured sources — Claude Code transcripts, Obsidian vault, git repos, rules files, memory stores via adapters. Connectors never write to a source. The life-OS benchmark and the rot exam open the store read-only.

**Writes, exhaustively:**
- its own SQLite DB and `data/` (findings, verdicts, drift reports, compiled context)
- `helicon fix-skills` and other write-backs: **dry-run by default**, `--apply` required, `.bak` written next to every file before modification, second run is a no-op
- `helicon watch --install`: one tagged line in your crontab, removed by `--uninstall`
- `helicon compile --inject`: skill files under `~/.claude/skills/helicon-*.md` — explicitly invoked, never automatic (and our own store still carries the pre-rename `glaze-*` artifacts from the old injector as a live example of why write-backs need lifecycle discipline; the skills audit flags them)
- your vault: **never**. Corrections are cubes in Helicon's store, not edits to your files. You stay the only writer of your second brain.

**Leaves your machine:** nothing, unless you configure a Qwen key — then excerpts of candidate memories (truncated cube content) go to the model for judging, and the response is cached locally. Keyless mode runs every deterministic check with zero egress and says so instead of degrading silently.

**Decisions:** every destructive or state-changing action (kill, retire, resolve, dismiss, rule application) is either made by you or made by a written rule you previewed and approved — and automated decisions are quarantined from the learning loop (rot class R9), so the tool cannot launder its own output into your evidence.
## Your domain, your lexicon (config, not code)

The claim-conflict detectors ship with built-ins (win counts, episode numbers, merge status, decision status) and take the rest from `config.json` — an enterprise wiki or research vault declares its own counted things and polar statuses, and gets the same conflict machinery, evidence receipts and resolve loop:

```json
"claims": {
  "metrics":   {"headcount": "\\b(\\d{2,5})\\s+employees\\b"},
  "statuses":  {"contract": {"live": "contract (is )?live", "expired": "contract (is )?expired"}},
  "canonical": {"wins": "mindmap.md"}
}
```

`canonical` encodes the single-source-of-truth rule: declare WHERE a fact's truth lives, and a conflict files as *"Drift from canon: canon says 9; 8, 10 asserted elsewhere"* — the human confirms a pre-decided direction instead of adjudicating from scratch.

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

- **Backend:** Python 3.12, FastAPI (75 endpoints), SQLite + FTS5 (22 tables), numpy embeddings (all-MiniLM-L6-v2, 384-dim, hybrid 60% semantic / 40% keyword search)
- **Frontend (optional):** React 19, TypeScript, Vite. Four surfaces — **Next Moves** (memory state → cited next prompts/goals, generated by Qwen, every move citing the memory it came from), **Memory** (sources, review coverage, health), **Needs Ruling** (every failed check with why/evidence/action, grouped Drift / Stale / Smartness), **Golden Rules** (rulings compiled with provenance, injectable). The dashboard is one of three interfaces (CLI · MCP-in-IDE · dashboard)
- **AI:** Qwen Cloud API via OpenAI-compatible SDK (see table above)
- **Distribution:** BYOK + local-first. Proof-of-run on Alibaba Cloud via Cloud Shell (`scripts/cloudshell-run.sh`)

## License

MIT
