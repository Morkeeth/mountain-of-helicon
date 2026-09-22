# Real-agent pilot · 22 Sep 2026

An honest negative on one narrow question. Three cases, one model, one task type. Not a Helicon scorecard, not a prevalence claim.

## Question

Do contradictions in agent instruction files change task success for a real AI coding agent, and does correcting only those contradictions help?

## Pins

| Object | Value |
| --- | --- |
| Cases | Three hand-verified TRUE rows from `docs/agent-context-report-2026-08.md` (same trio as the 21 Sep scripted pilot) |
| Report sha256 | `5c9345a57f80b3462442a315973478252eb0b1e4c0b6e654c4a65df647f81de7` |
| Verification sha256 | `5f62f355a4fbd6351b7b23e7c8794caf52d2d26bb994295b81526e62f94a2580` |
| Helicon SHA at pilot design | `327e4671f8da4b541eb82a4c4635684a4c3b701b` |
| HorseTrack clone | `3ee8c1ffd60cefeabc1e019f532d3d64543c2f49` |
| confidence-routed-extraction clone | `178a7c35e2a5431f3b9f9e744ad2405cedf09d29` |
| organizze-mcp clone | `bde178eb5a7411a870a3627ecb6049434127defb` |
| Agent | Claude Code CLI 2.1.278 |
| Model | `--model sonnet` → `claude-sonnet-5` |
| Auth | claude.ai Max session via `env -u ANTHROPIC_API_KEY` (invalid API key otherwise overrides login) |
| Cap | `--max-budget-usd 0.50` per run; Read tool only |

Machine receipts (outside this repo): `~/.local/state/day-run/2026-09-22/helicon-real-pilot-neutral/summary-v2.json` and `CURSOR-HELICON-REAL-PILOT-RETURN.md`.

## Neutral prompt

A circular prompt ("open the operating guide named by repository agent instructions") makes a false pointer fail by construction. The causal table used this neutral task instead:

> Find this project's main operating guide or README and tell me in one line how to start it. Reply OPENED:\<path\> then the line.

Success (independent of Helicon): the path exists and is readable, and the start line is grounded in that file (command fragments or distinctive tokens present in the doc).

Conditions per case:

- **original:** stock `CLAUDE.md` or `AGENTS.md` (contains the known false path).
- **corrected:** that false path rewritten to the night-pilot corrected target.
- **no_context:** instruction files removed; `--setting-sources ""` so nothing else reloads them.

## 3×3 table (causal)

List-basis dollars from Claude Code JSON `total_cost_usd` (`costBasis: list`). Subscription use; not a separate invoice.

| Case | original | corrected | no_context |
| --- | --- | --- | --- |
| HorseTrack | pass · `README.md` · $0.1029 | pass · `README.md` · $0.1014 | pass · `README.md` · $0.0361 |
| confidence | pass · `README.md` · $0.1127 | pass · `README.md` · $0.1180 | pass · `README.md` · $0.0394 |
| organizze | pass · `README.md` · $0.1299 | pass · `README.md` · $0.1555 | pass · `README.md` · $0.0443 |

9/9 pass. Causal total: **$0.8402** list.

Mean with instruction files loaded (original + corrected): about **$0.12**. Mean no_context: about **$0.04**. Ratio about **3×** for the same success on this task.

## Invalid first pass (discarded)

A first neutral pass ran all nine cells with `--setting-sources ""` on every condition. That suppressed project `CLAUDE.md` / `AGENTS.md` even for original and corrected, so original vs corrected was not a real contrast. Cost of that pass: $0.8215 list. It is not in the causal table.

Harness rule for any rerun: load project instructions on original and corrected; only strip them for no_context. Do not use `claude --bare` on Max OAuth (it requires an API key).

## Finding

On this neutral "find the main guide/README and how to start" task, false pointers in the instruction files **did not mislead** Claude Code Sonnet on these three repositories: every original cell still opened `README.md` with a grounded start line. Corrected and no_context also passed, so correcting the contradiction was not uniquely helpful here. Loading the instruction files cost about **3×** more (roughly $0.10 to $0.13 vs $0.04 per run) for the same success.

## Limits

- Three cases only.
- One model (`claude-sonnet-5` via Claude Code).
- One task type (neutral README / operating-guide discovery with a grounded start line).
- Not a Helicon product scorecard, not a prevalence estimate, and not proof that false pointers never hurt. A task that requires opening the path named in the instructions can still fail when that path is absent (as the earlier circular dry run showed by construction).

## Related

- Scripted (non-LLM) pilot return: day-run `CURSOR-HELICON-PILOT-RETURN.md` (21 Sep 2026).
- August hand verification: `docs/agent-context-report-2026-08.md`, `docs/agent-context-verification-2026-08-09.md`.
