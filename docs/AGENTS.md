# Agents — integrate with Mount Helicon

**For:** coding agents (Cursor, Claude Code, etc.) · **Not for:** human dashboard REST clients

---

## Which surface to use

| Surface | Command / URL | Purpose |
|---------|---------------|---------|
| **MCP (agents)** | `helicon mcp` | **Primary integration.** 16 tools on stdio JSON-RPC. |
| **CLI (humans/scripts)** | `helicon …` | Audit, govern, export, morning briefing. |
| **CI** | `helicon ci` | PR gate on committed rules files — separate from MCP. |
| **Dashboard REST** | `http://127.0.0.1:8420/docs` | **Human UI backend only** (~125 routes). Do not point agents at OpenAPI REST for memory ops — use MCP. |

If you are an agent reading this: **run MCP**, not HTTP calls to `:8420`.

---

## MCP setup

```bash
helicon mcp   # stdio server — wire into Cursor MCP config or Claude Code
```

Transport: newline-delimited JSON-RPC on stdin/stdout (not LSP framing).

---

## Tools (16)

| Tool | Use when |
|------|----------|
| `helicon_health` | Overall memory score, counts, decay stats |
| `helicon_stale` | Items below confidence threshold — review candidates |
| `helicon_search` | Full-text lookup across memories |
| `helicon_contradictions` | Audit findings that conflict |
| `helicon_recent_reviews` | Human approve/kill pattern |
| `helicon_patterns` | Active rot patterns |
| `helicon_flag` | Correct a memory at point of use |
| `helicon_guard` | Block a claim that violates compiled law |
| `helicon_context` | Pull memory **with provenance** for this turn |
| `helicon_ask` | Natural-language query over store |
| `helicon_brief` | Compact context packet for a task class |
| `helicon_playbook` | Run a named playbook |
| `helicon_compile` | Compile rulings into law |
| `helicon_triage` | Auto-triage rot candidates |
| `helicon_consolidate` | Merge redundant memories |
| `helicon_portrait` | User/agent portrait summary |

Typical agent loop: `helicon_context` → work → `helicon_flag` if wrong · `helicon_guard` before asserting facts.

---

## Example session flow

1. **`helicon_context`** — load provenance-backed memories for the task.
2. Do the work; if the user corrects you, **`helicon_flag`** immediately.
3. Before stating a ruled fact, **`helicon_guard`** — if blocked, print the refusal; do not paraphrase around it.
4. End of session: optional **`helicon_health`** to log score delta.

---

## What not to do

- Do not scrape `:8420/docs` REST from an agent — wrong layer, wrong auth model.
- Do not treat dashboard JSON as MCP responses.
- Do not skip `helicon_guard` on claims that appear in `GOLDEN_RULES` or recent rulings.

---

## Further reading

- `README.md` — product overview
- `BUILD-PLAN-2026-08-29.md` — C1 export · T2 named user (Oscar gate)
- `helicon/mcp_server.py` — tool schemas (source of truth)
