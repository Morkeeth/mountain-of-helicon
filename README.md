# Mountain of Helicon

**Executable preflight for agent context.** Mountain of Helicon checks whether
the instructions an agent is about to load still match the repository in front
of it. Every contradiction carries the command and stdout that proved it.

It is local-first, keyless for deterministic checks, and warns by default before
work continues. It can also audit longer-lived memory, let a human rule on
contradictions, and compile those rulings into policy agents can query through
CLI or MCP.

## The measured finding

We ran the frozen 591-repository corpus and scored 577 current default branches;
14 exclusions are named. After removing projection duplicates, enforcing the
existing-file evidence invariant, and hand-verifying all 30 mechanical survivors,
**6 repositories (1.04%) contained a sendable doc-vs-code contradiction**.
Finding-level precision was 9/30. The rejected rows and reasons are part of the
result, not a footnote.

The frozen corpus, commands, stdout, exclusions, and hand-verification ledger are
in [`docs/agent-context-report-2026-08.md`](docs/agent-context-report-2026-08.md).
Release gates and intentionally deferred work are tracked in
[`LAUNCH_ROADMAP.md`](LAUNCH_ROADMAP.md).

## Try the complete terminal demo

```bash
git clone https://github.com/Morkeeth/mountain-of-helicon.git
cd mountain-of-helicon
python3 scripts/check_python.py
python3 -m pip install -e .
bash scripts/demo.sh
```

The demo scans named public repositories, installs the Claude Code doorway hook
into an isolated throwaway settings file, shows the warning with executable
evidence, and records an explicit override. It does not touch your real Claude
settings or memory store. Python 3.10+ is required; the preflight gives older
macOS Python 3.9 users the exact upgrade command without a traceback.

**Bring your own Qwen key (BYOK).** Get one free on the [Alibaba Cloud Model Studio free tier](https://www.alibabacloud.com/en/product/modelstudio), set `QWEN_API_KEY` or put it in `~/.helicon/config.json`. `helicon init` keeps configuration and the SQLite store under `~/.helicon/`, never inside the installed package. **Keyless degrade:** without a key every deterministic test still runs; only the two LLM-judged tests (Contradiction, Grounding) switch off -- the battery says so instead of faking a verdict.

## What ships

- **Doorway:** `helicon sweep` checks agent-rules files against repository
  reality; `helicon doorway install` adds a reversible Claude Code preflight.
- **Memory governance:** a 13-class rot exam, human rulings, receipts, undo, and
  Golden Rules.
- **Agent access:** local MCP exposes 23 tools, plus an authenticated remote endpoint.
- **Connectors:** Claude Code, Cursor and Cursor Cloud exports, git, Obsidian,
  agent rules, ChatGPT exports, Mem0, Letta, Graphiti, and LifeOS adapters.
- **Dashboard:** Doorway, Rulings, governed runs, memory health, and the deeper
  Lab surfaces.

## Visual demo

The web bundle is generated, never committed stale. From a source checkout:

```bash
helicon demo
```

On first run this installs/builds the dashboard with npm, seeds a labelled
19-memory demo under `~/.helicon/demo`, and serves it only on
`http://127.0.0.1:8420/#findings`. No personal connector runs and no API key is
required.

## Use it on your own stack

```bash
helicon init
helicon scan
helicon doctor
helicon audit
helicon check "what am I working on"
helicon serve
```

Qwen is optional and BYOK. Without a key, deterministic checks continue and the
two LLM-judged checks report themselves unavailable rather than fabricating a
verdict. Semantic embeddings are an optional install; the core remains slim.

## CI for agent memory (GitHub Action)

The rot exam runs in CI, so a pull request that drifts your agent's instruction files fails the build — CI for memory, literally. `helicon ci` scans a repo's committed `CLAUDE.md` / `AGENTS.md` / `.cursorrules` / `.clinerules` / copilot-instructions, runs 13 documented failure classes through the 13-class deterministic exam (no key, no torch, no LLM), emits GitHub annotations + a job-summary table, and exits non-zero on rot. R13 goes further than reading: it runs a probe against the repo's own running code and reports which sentences the system contradicts.

```yaml
# .github/workflows/memory-ci.yml
name: memory-ci
on: [push, pull_request]
jobs:
  rot-exam:
    runs-on: ubuntu-latest
    steps:
      - uses: Morkeeth/mountain-of-helicon@main
        with:
          fail-on: rot   # or 'none' for report-only
```

Locally it's the same one command: `helicon ci`. This repo dogfoods the exam in
report-only mode (`--fail-on none`) so known R6 findings remain visible without
making unrelated pull requests permanently red. Teams that have ruled their
baseline clean should use the Action's default `fail-on: rot`.

## The live doorway (a warning backed by executable proof)

Everything above produces a verdict. The doorway puts it where work begins: a
Claude Code `UserPromptSubmit` hook warns when the repository disproves loaded
instructions, naming the offending lines and executable evidence in the terminal.
Warning is the default because a preflight that wedges a terminal gets removed.
Teams that explicitly want enforcement can set `HELICON_GATE_MODE=block`.

```bash
helicon board                 # every repo under ~/CODE and what it loads into an agent
helicon board --repo <name>   # every loaded line, with its probe verdict
helicon doorway install       # wire the gate into ~/.claude/settings.json (backup + diff + confirm)
helicon doorway install --uninstall   # remove exactly what it added
helicon hook --print-config   # the settings.json snippet (never auto-installed)
helicon receipt <session>     # did the harness actually RECEIVE the injection?
```

The gate a stranger installs is **keyless and config-free**: `helicon doorway install`
writes one `UserPromptSubmit` hook (shown as a diff, backed up first, idempotent,
and exactly reversible), and the hook — `python3 -m helicon doorway gate` — needs no
`config.json` to run. On the next prompt in any repo whose loaded docs its own code
disproves, the warning appears in your terminal and the run continues. Warnings and
explicit overrides log into your configured store (so they show up in `helicon runs`
/ the dashboard), and fall back to a standalone `~/.helicon` store for a stranger
who has no config.

Three rules it obeys, all from the same law:

- **Machine-evidenced.** A `CONTRADICTED` verdict came from a probe that executed and
  disagreed. The operator can correct/demote the line, continue after the warning,
  or explicitly record an override reason.
- **Cold lines never block.** Demoting a line keeps it forever and loads nothing, so
  it cannot poison a run and must not stop one. `--demote` is a real exit, not advice.
- **Fail open, loudly.** Any error lets the prompt through; a doorway that bricks a
  terminal gets uninstalled, and then it governs nothing. Logged warning/override
  events make intervention inspectable — the absence of one proves nothing.

`helicon receipt` is the honest half of delivery. Every other step can be satisfied by
a row Helicon itself wrote; this one opens the transcript the **harness** wrote and
looks for a content-derived token, ruling `RECEIVED` / `NOT_FOUND` / `UNVERIFIABLE`.
UNVERIFIABLE is a verdict, never rounded up. Injections are checked against the
~32k context-rot onset first and trimmed if they would exceed it — a memory tool that
quietly causes the rot it detects is the joke writing itself.

## Headline Features

- **`helicon snapshot`** -- regression tests for retrieved context. Capture what a task retrieves today; `snapshot check` fails when tomorrow's retrieval drifts. CI for memory.
- **`helicon check "<task>"`** -- context-quality battery on what a task retrieves: Relevance, Freshness, Redundancy, Thinness, Expiry (deterministic) + Contradiction, Grounding (judged live by Qwen). Verdict: HEALTHY / DEGRADED / BROKEN. Every verdict prints the age of the last scan, because a DEGRADED verdict is uninterpretable if the scan itself is stale. `--json` for scripts and CI.
- **`helicon reconcile`** -- timely forgetting. Re-scans sources and retires memories reality no longer contains (dry-run by default, never touches human decisions). On the live DB it retired 20 superseded memories in its first run.
- **`helicon fix-skills`** -- write-back: Qwen writes missing descriptions into your agent skill files (dry-run by default, `.bak` backups). It fixed 7 of this project's own skills.
- **`helicon doctor`** -- five checks (PATH, config, key, DB, last scan), exit 1 on failure. The front door to a daily loop.
- **`helicon rule "<natural language>"`** -- prompted rules. Qwen compiles your sentence to a restricted predicate (whitelisted fields, never code); before approval you see coverage, samples, empirical precision against YOUR past decisions, and conflicts with other rules. One approved rule governs hundreds of items; applied rules are never counted as human evidence.
- **The regret ledger** -- killed memories become a ghost list (LeCaR cache-eviction mechanics). When retrieval wants one back, a time-decayed regret event blames the exact decision that killed it, and FINDINGS shows "you retired this, retrieval wanted it 2x since -- restore?". Wrong forgetting is measured, not assumed.
- **`helicon_flag` over MCP** -- point-of-use correction. Injected memories carry id + last_verified + used_count; the agent (or you, through it) flags stale/wrong/useful in one call. Flags become findings the human confirms -- the agent proposes, it never deletes.

## Three Layers

**Layer 1 -- Extraction.** Pluggable connectors cover Claude Code, Cursor and Cursor Cloud exports, Obsidian, git history, ChatGPT exports, agent rules, LifeOS, Letta MemFS, Graphiti, and Mem0. Rewritten and expiring Mem0 memories carry their temporal fields into freshness tests. Agent *rules* files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`) are split into section-level memories so regression catches one section drifting. Every item becomes a **HeliconCube**: a versioned memory unit with source, confidence, content hash, review status, and decay parameters. A novelty gate prevents redundant storage.

**Layer 2 -- Review pattern learning.** Weibull forgetting curves with per-type shape (cliff decay for code, long tail for decisions). Auto-triage derives kill/approve rules from HUMAN reviews only -- its own decisions are excluded so it cannot reinforce its own echo. On its first run it handled 585 of the 1,268 memories the store held at that time autonomously. Spin detection, kill prediction, Helicon Score.

**Layer 3 -- Meta-audit.** The system audits its own stored patterns: temporal staleness ("this week" in a 27-day-old file), factual contradictions (Qwen-judged), decay, pattern staleness, anti-confabulation challenges. The human reviews the memory review.

## Qwen Cloud API usage (where the LLM is load-bearing)

| Tier | Model | Used for |
|------|-------|----------|
| fast | `qwen3.6-flash` | Memory summarization, novelty gate, skill descriptions |
| default | `qwen3.6-plus` | Battery judging (Contradiction, Grounding), factual audit, Next Moves |
| deep | `qwen3.7-max` | Consolidation synthesis, optimization reports |
| retrieval | `text-embedding-v4` | Dense vectors (1024-dim) for hybrid + semantic search |
| retrieval | `qwen3-rerank` | Two-stage rerank over RRF-fused candidates |

All calls go through the OpenAI-compatible endpoint `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` with a per-call SQLite response cache and per-operation cost tracking (`/api/tokens`). The two subjective battery tests are judged live and tagged `(qwen)` in output; if the judge call fails, the battery falls back to deterministic-only rather than fabricating a verdict.

## MCP Server (23 tools)

Agents audit their own memory mid-conversation. Add to `.claude.json`:

```json
{
  "mcpServers": {
    "helicon": { "command": "helicon", "args": ["mcp"], "cwd": "/path/to/mountain-of-helicon" }
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
| `helicon_guard` | Check a proposed claim against the compiled law *before* writing it: `blocked` / `warn` / `clean` |
| `helicon_ask` | Guarded retrieve — what is safe to believe about a topic: the ruled-true answer + retrieved context split into safe vs. ruled-wrong |
| `helicon_brief` | The morning brief — all five pillars in one call: truth, continuity, direction, reflection, calm |
| `helicon_portrait` | Grounded portrait of what the record shows about the person, plus its health |
| `helicon_context` | Proactive memory injection for a task -- every memory carries its id, last_verified, used_count |
| `helicon_flag` | Point-of-use correction: flag a memory stale/wrong/useful by id; stale/wrong become findings the human confirms |
| `helicon_playbook` | Task playbooks from review patterns |
| `helicon_compile` | Compile reviewed memory to injectable files |
| `helicon_triage` | Trigger auto-triage |
| `helicon_prompt_gate` | Gate an execution prompt through a Wager -- approves only after a human accepted a BUILD or REPAIR move, else abstains |
| `helicon_capture_launch` | Freeze the acceptance test and context packet before implementation starts |
| `helicon_capture_closeout` | Close a run with real artifacts and a real verification receipt |
| `helicon_workgraph_trace` | Join one work card to its task run, context, memory, skills and evidence |
| `helicon_workgraph_attention` | Name the missing graph edge -- link_run, freeze_context, attach_artifact, choose_move |
| `helicon_workgraph_learning` | Withhold recommendations until real resolved outcomes accumulate |
| `helicon_workgraph_review_skill` | Record the skill version actually loaded, hashed over its bytes |
| `helicon_consolidate` | Run a consolidation (sleep) cycle |

The full JSON-RPC 2.0 handshake (initialize, tools/list, tools/call) is exercised in the receipts; `helicon mcp` runs the server on stdio, so the bare CLI never silently becomes a server.

### Remote MCP for cloud agents

`helicon serve` also exposes a stateless MCP endpoint at `/mcp` when a dedicated
token is configured:

```bash
export HELICON_MCP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
HELICON_CONFIG=/path/to/config.json helicon serve
```

Configure the remote client with `https://your-helicon-host/mcp` and send
`Authorization: Bearer <token>`. The endpoint refuses to start with a token
shorter than 32 characters, rejects requests over 1 MiB, serializes access to
the SQLite connection, and returns `Cache-Control: no-store`.

Remote access deliberately exposes the agent workflow, including context,
guard, ask, and point-of-use flags, but not `helicon_compile`,
`helicon_triage`, or `helicon_consolidate`. Those maintenance tools can write
host files or mutate the store in bulk and remain available only through the
local stdio transport.

The built-in server does not terminate TLS. Put it behind HTTPS on a private
network or an authenticated reverse proxy; never send the bearer token over
plain HTTP and never expose a personal memory store directly on a public IP.
`HELICON_PASSWORD` protects dashboard API routes and is intentionally separate
from `HELICON_MCP_TOKEN`.

### Feed Cursor Cloud runs back into memory

The `cursor-cloud` connector reads local export bundles containing
`index.json` and per-run `transcript.json`, `diff-metadata.json`, and
`events.json` files:

```json
{
  "connectors": {
    "cursor-cloud": {
      "enabled": true,
      "export_dir": "~/Downloads/cursor-cloud-agent-transcripts",
      "include_text": false
    }
  }
}
```

It selects the newest export for each stable cloud-agent id and produces one
idempotent session summary: repository, branch, model, status, message/tool
counts, observed tool failures, events, and diff/PR outcome. Metadata-only is
the default because raw exports may contain private prompts, reasoning,
terminal commands, file contents, diffs, and credentials.

Set `include_text` to `true` only when conversation prose belongs in the memory
store. That opt-in includes bounded user and final-assistant text with common
token patterns redacted. Reasoning, tool arguments, terminal output, file
contents, search results, and diffs are never ingested.

## CLI (58 commands)

`init` `scan` `reconcile` `fix-skills` `serve` `demo` `triage` `review` `route` `score-runs` `runs` `run` `hook` `receipt` `judge-bench` `bench` `attribute` `move` `leaderboard` `snapshot` `lens` `taste` `check` `report` `read` `audit` `consistency` `volatility` `unreviewed` `fleet` `queue` `guard` `ask` `brief` `board` `sweep` `doorway` `repair` `ci` `policy` `evolve` `lift` `resolve` `watch` `alias` `rule` `doctor` `mcp` `score` `stack` `optimize` `eval` `embed` `playbooks` `reflect` `compile` `consolidate` `eval-consolidation`

Four of them answer to a second name, kept working so older muscle memory doesn't break: `battery` = `check`, `rot` = `audit`, `heal` = `repair`, `gold` = `policy`. Aliases, not extra commands, so they are not counted above.

`helicon route` turns output-verification into a **model-routing recommendation**: it reads the eval store — the verified verdicts `review --terminals` produced — and ranks models by Wilson-scored verified-pass-rate per task-class, with sample size and confidence attached. The model is attributed from the git co-author trailer of the commits that produced the output; the outcome is a real reality-check, never a guess. Below a sample threshold it says *insufficient evidence*, never a fabricated number. `helicon route --record --run` builds the evidence first. See [docs/ROUTE.md](docs/ROUTE.md).

`helicon score-runs` and `helicon runs` score whole RUNS, the same output-verification one level up and made cost-aware: `score = verified yield / cost - damage`. Cost comes from the real transcript token usage, yield from the `review --terminals` verdicts, damage from an incident flag. Every term traces to a real source; nothing is vibed. `score-runs --card` cuts one run card, `runs` renders the scored history, `runs --suggest` reads what to run next off it. See [docs/RUNS.md](docs/RUNS.md).

`helicon judge-bench` benchmarks Qwen as the memory-rot judge against the operator's own human rulings, and (with an OpenRouter key) against GPT/Claude on the same probes. Real result (run #2, 26 probes, 13 real contradictions + 13 controls, ground truth = the operator's own rulings): **qwen3.6-plus ties anthropic/claude-sonnet-5 at 0.962 accuracy and beats openai/gpt-5 (0.808)**, at $0.00444 per run and in 54s against Sonnet's 144s and GPT's 245s. qwen3.6-flash holds 0.923 for $0.00167, 8x cheaper than qwen3.7-max for the same specificity. And **every model, Qwen and Claude and GPT alike, missed `unit-drift`**: some rot is a domain ruling rather than a logical contradiction, and no judge at any price catches it. That is what the human-ruling layer exists for. Reproduce: `helicon judge-bench --set all --save` (needs `openrouter_api_key` for the competitors); the Judge tab reads the saved run, and renders an unrun bench as unrun. See [docs/ROUTE.md](docs/ROUTE.md).

`helicon move` is the context-mover: read memory from one platform, VERIFY each item (freshness, and with `--verify-contradictions` the Qwen judge), and render the survivors into another platform's native format (`claude-code` / `cursor` / `markdown`). Memory moves verified, never blindly; held-back items are listed with why. Dry-run by default; `--apply` backs up the target first.

`helicon leaderboard` is the population-scale version: it reads git history across many repos (where multiple models and harnesses actually co-authored commits) and ranks models by how often their commits SURVIVE vs get REVERTED, Wilson-scored. Execution-free (git only, so it is bounded and cannot freeze a machine); the revert is the honest failure signal. On 927 attributed commits across 25 local repos it already separates opus-4.6 / opus-4.8 / fable-5 / cursor by reliability.

`helicon repair` runs **the self-healing audit loop** — the thing no retriever can do. It scores the four truth gates (freshness / volatility / consistency / retrieval) on a store, surfaces each drift with its cross-source evidence, proposes a repair (retire the stale memory, move a fast fact to the live layer) as a diff you accept, applies the accepted ones, and re-scores so the gates visibly move. `helicon repair --demo` runs it on a seeded, universally-legible store (the classic "I told my agent I'm vegetarian, then started eating chicken again — it never updated" contradiction, plus a stale goal and a fast fact); `--apply` closes the loop.

`helicon audit` runs **the rot exam**: the 13 documented memory-failure classes in [ROT.md](ROT.md) checked live against your real store -- deterministic, zero LLM calls, free to run daily. On this repo's own store it currently finds rot in several of 13 classes and says so — and as of Jul 5 all classes are fully tested, 0 partial.

`helicon watch` makes the exam ambient: scan + selectors + rot exam on a timer (`helicon watch --install` writes the crontab line, every 6h), diffed against the last run. You get a macOS notification and a `drift-report.md` only when something NEW rots — no news, no noise. First run baselines silently.

`helicon policy` compiles **GOLDEN RULES**: the stack's law, built from your rulings, dismissal precedents, approved triage rules, declared renames, canonical sources and standing feedback — every rule with its provenance (a rule without provenance is a vibe). `--inject` writes it to `~/.claude/GOLDEN_RULES.md` (dry-run default, `.bak` kept) so every session can obey it. `helicon evolve` is the night command: scan, every selector, the exam, a gold recompile, and the morning delta — what your stack learned while you slept.

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

Honest numbers from the first run (232 files, 1,667 section memories): **6/16 file-level catches, 4/16 strict facet-match** — the output labels the difference itself. What it caught: both merge-status flips (audit doc still said 'NOT patched' after the fix merged), a stale dashboard doc, a dead 7-week-old plan. What it found that the humans missed: a win-count fight (9 vs 10) living in the resume and two application drafts, and 35 files still asserting a dead project name post-rebrand. Named misses, on the roadmap: overlapping-date-range drift (Aug 14-22 vs Aug 15-24 overlap, so interval semantics reads agreement), living-doc supersession without a declared rename, and content-based staleness (a young file asserting old facts).

## Access & trust model (read this before connecting your vault)

A tool that audits your memory reads your memory. That access is scary, so here is exactly what Mountain of Helicon does with it — from the code, not a promise:

**Reads (always read-only):** your configured sources — Claude Code transcripts, Obsidian vault, git repos, rules files, memory stores via adapters. Connectors never write to a source. The life-OS benchmark and the rot exam open the store read-only.

**Writes, exhaustively:**
- its own SQLite DB and `data/` (findings, verdicts, drift reports, compiled context)
- `helicon fix-skills` and other write-backs: **dry-run by default**, `--apply` required, `.bak` written next to every file before modification, second run is a no-op
- `helicon watch --install`: one tagged line in your crontab, removed by `--uninstall`
- `helicon compile`: compiled context files under `data/compiled/` (`--output` redirects). It writes nothing into `~/.claude/`: an auto-inject path exists in the source (`compiler.inject_into_claude_code`) but no command calls it, so the pull path (`helicon_context` over MCP) is the working half of that loop and the push half is unwired. Our own store still carries pre-rename `glaze-*` skill files from an older injector, which the skills audit flags: a live example of why write-backs need lifecycle discipline
- `helicon policy --inject` (alias `helicon gold --inject`): `~/.claude/GOLDEN_RULES.md`, dry-run by default, `.bak` kept
- your vault: **never**. Corrections are memories in Helicon's store, not edits to your files. You stay the only writer of your second brain.

**Leaves your machine:** nothing, unless you configure a Qwen key — then excerpts of candidate memories (truncated content) go to the model for judging, and the response is cached locally. Keyless mode runs every deterministic check with zero egress and says so instead of degrading silently.

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

- Composite: **~67** (live, as of 2026-07-13 — run `helicon eval` to recompute; retrieval P@3 + MRR + decay-AUC; audit axis excluded -- no labeled ground truth).
- Retrieval: P@3 0.615, MRR 0.596. Small internal benchmark (n=13, one label per query) -- disclosed, not hidden.
- **Decay predicts human kills at rank-AUC 0.78** (mean confidence of killed memories 0.14 vs approved 0.27). A real, independent signal.
- Consolidation: ~9-10x fewer tokens; Qwen-judged quality favors synthesis (self-graded, shown as direction, not proof).
- The public demo store is 19 labelled planted memories and contains no personal
  data. Live scans read only the sources each user configures.

## Built on established patterns, extended

Mountain of Helicon's capabilities stand on well-understood memory-systems patterns and take each one further. The lineage, stated honestly — the second column is the established idea, the third is our own build on top of it:

| Capability | Established pattern | How Mountain of Helicon extends it |
|-----------|--------|---------------------------|
| Versioned memory units | Structured memory units, not raw text | HeliconCube: source, hash, valid_from, confidence, decay per type |
| Multi-axis audit | Temporal/factual/logical consistency checks | 13-class rot exam, each with a receipt and a never-twice guard |
| Weibull decay | Non-uniform forgetting curves | Per-type kappa, and decay rank-predicts human kills (AUC 0.78) |
| Novelty gate | ADD/NOOP/MERGE at ingestion | Gate + provenance, so a merge never loses the source it came from |
| Anti-confabulation | Challenge claims against evidence | Grounding check + R12 phantom-association catch |
| Retrieval learning | Track surfaced vs acted-on | Q-value ranking rewarded by human rulings only — no self-echo |
| Identity & phantom coherence | *(ours — no store or prior system does this)* | R11 fork detection, R12 phantom catch, rulings compiled to law |

## Architecture

<p align="center">
  <img src="docs/architecture.svg" alt="Mountain of Helicon architecture: the store, retrieve, output, attribute, rule, law loop" width="100%">
</p>


- **Backend:** Python 3.12, FastAPI (121 endpoints), SQLite + FTS5 (38 tables). **Qwen-native retrieval when a Model Studio key is configured**: `text-embedding-v4` (1024-dim) dense vectors + FTS5, fused by Reciprocal Rank Fusion, then a `qwen3-rerank` two-stage pass — the whole retrieve→rerank stack on Alibaba Cloud (falls back to local MiniLM + linear fusion, FTS-only, when no key)
- **Frontend (optional):** React 19, TypeScript, Vite. Four surfaces — **Next Moves** (memory state → cited next prompts/goals, generated by Qwen, every move citing the memory it came from), **Memory** (sources, review coverage, health), **Needs Ruling** (every failed check with why/evidence/action, grouped Drift / Stale / Smartness), **Golden Rules** (rulings compiled with provenance, injectable). The dashboard is one of three interfaces (CLI · MCP-in-IDE · dashboard)
- **AI:** Qwen Cloud API via OpenAI-compatible SDK (see table above)
- **Distribution:** BYOK + local-first. No hosted personal-store service is
  advertised for v0.1; public hosting waits for HTTPS, sessions, configured
  CORS, rate limits, and backups.

## License

MIT
