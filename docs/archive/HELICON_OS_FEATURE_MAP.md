# Mount Helicon — Memory OS Feature Map (brutally factual)

Position: **a Qwen-powered governance layer for agent memory** (a memory control
plane) — a local-first command center where the machine handles routine rot, the
human rules only genuine contradictions, and each ruling becomes an enforceable rule.
"Memory OS" is the long-term horizon, not today's claim. This map is the honest
inventory: what a skeptical judge can see work today vs. what is claim-only.

Legend: **[SHIP]** real + demonstrable now · **[HIDDEN]** works but invisible/
unintegrated · **[DESIGN]** designed, not built · **[REQ]** required for submission
· **[CUT]** remove from claims.

| Capability (module) | Product organ | User flow | Proof path | Status / gap |
|---|---|---|---|---|
| One-command seeded demo (`helicon demo`, `demo.py`) | First run | clone → `pip install -e .` → `helicon demo` → populated dashboard | `judge-check.sh`; `test_demo_golden` | **[SHIP][REQ]** |
| Govern-batch loop (`api/govern.py`, `FocusReview`) | Governance surface | rule exceptions → stage → one Apply → receipt w/ proof → undo | `test_govern_batch`, `test_govern_api_boundary` | **[SHIP][REQ]** real, tested |
| 12-class rot exam (`rot.py`, `consistency.py`, `identity.py`, `relations.py`) | Machine review / detection | the exam surfaces decay, contradictions, forks, staleness | dashboard "The Exam"; unit tests | **[SHIP]** |
| Auto-managed lane (`findings.py` `_AMBIENT_KINDS`) | Machine review | phantom/stale/mechanical resolved without a human | demo queue check | **[SHIP]** just corrected |
| Compiled law + guard (`gold.py`, `guard.py`) | Governance → protection | ruling → GOLDEN_RULES → guard blocks a ruled-wrong claim | `test_guard`; receipt `compiled_into_law` | **[SHIP]** |
| Qwen contradiction/grounding judge (`qwen.py`, `battery.py`, `eval.py`) | Evaluation | the battery scores retrieval; Qwen judges contradiction/grounding → DEGRADED, grounding 0.385 | **live call proved**: "vegetarian vs chicken → CONTRADICTION" 4.0s | **[SHIP][REQ]** Qwen load-bearing |
| Model routing (`route.py`, `leaderboard.py`, `runs.py`) | Evaluation / comparison | verified-outcome ledger; route **withheld below a quality floor** | `test_route_floor`; `helicon route` | **[HIDDEN]** real but thin/confounded; honestly labelled roadmap |
| Auto-triage (`triage.py`) | Machine review | keep/kill learned from *human* rulings only (no echo) | unit tests | **[HIDDEN]** works, not surfaced in the day |
| Routine/skill health (`stackwatch.py`, `watch.py`, `scripts/nightly.sh`, `integrity.py`) | Nightly improvement | nightly liveness + skill-drift; degraded/never-ran states | `stackwatch` tests; doctor | **[HIDDEN]** exists; not a first-class governed surface |
| MCP server, 16 tools (`mcp_server.py`) | Agent interface | agent retrieves context / checks guard / flags | tool list | **[HIDDEN][REQ]** works; `helicon_context` mutates retrieval state on lookup (needs a read-only mode) |
| Multi-source ingest (`connectors/`) | Memory intake | Claude Code, git, Obsidian, skills, Mem0 — read-only | scan tests | **[SHIP]** (off in demo, by design) |
| Alibaba Cloud: Model Studio + DashScope + **Cloud Shell run** (`qwen.py`, `embeddings.py`, `scripts/cloudshell-run.sh`) | Runs on Alibaba Cloud | Qwen judging + embeddings live; full backend booted in Alibaba Cloud Shell | live Qwen call; `cloudshell-run.sh` | **[SHIP][REQ]** backend runs live on Alibaba Cloud ECS at **http://47.237.3.97:8420** (Singapore) + Cloud Shell; local-first by default |
| TaskRun / ContextPacket recorder (`taskrun.py`, `context_policy.py`) | Provenance recorder | open → freeze packet → attach artifact → **attested** outcome | `test_taskrun` (6 tests) | **[SHIP]** tested, read-only; **does NOT yet drive retrieval, routing, or learning** |
| "Context OS" framing, autonomous optimization, write-back, agent-comparison-as-proof | — | — | — | **[CUT]** until a demo proves each |

## What the operator-day demo can honestly show today

Real spine, in order: **machine review** (exam auto-manages the bulk) → **human
review** (the exception queue: the vegetarian/chicken contradiction, an identity
fork) → **one governed Apply** (stage → apply → receipt: compiled into GOLDEN_RULES,
guard now blocks it, undo) → **Qwen load-bearing** (it judged that contradiction
live; the battery returns an honest DEGRADED with grounding under half) → **nightly
health** (routine/skill liveness with degraded/never-ran states, via stackwatch).

The **task surface (TaskRun)** and a **reproducible A/B comparison** are the two
places the "OS" promise outruns the build. They are labelled roadmap, not shown as
working.
