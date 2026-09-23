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

Mean with instruction files loaded (original + corrected): **$0.1201**. Mean no_context: **$0.0399**. The dollar ratio is 3.01. It does not measure the project instruction file. See "Correction, 23 Sep 2026" below.

## Invalid first pass (discarded)

A first neutral pass ran all nine cells with `--setting-sources ""` on every condition. That suppressed project `CLAUDE.md` / `AGENTS.md` even for original and corrected, so original vs corrected was not a real contrast. Cost of that pass: $0.8215 list. It is not in the causal table.

Harness rule for any rerun: load project instructions on original and corrected; only strip them for no_context. Do not use `claude --bare` on Max OAuth (it requires an API key).

## Finding

On this neutral "find the main guide/README and how to start" task, false pointers in the instruction files **did not mislead** Claude Code Sonnet on these three repositories: every original cell still opened `README.md` with a grounded start line. Corrected and no_context also passed, so correcting the contradiction was not uniquely helpful here. The original and corrected runs cost 3.01 times as much as no_context in list dollars for the same success. Most of that gap is user-level context and cache-write pricing, not the project instruction file (next section).

## Correction, 23 Sep 2026: where the 3x came from

The first version of this note said that loading the instruction files cost about 3x. The dollar ratio is right. The attribution was wrong. Two checks found it.

**1. no_context removed more than the project file.** no_context used `--setting-sources ""`. That also removed the user-level context (user CLAUDE.md, user rules, skill listing and other user settings). original and corrected loaded it. So the contrast is "project file plus user-level context" against "neither".

**2. The extra tokens are cache writes on two-turn runs.** Source: the nine v2 result files (`usage`, `total_cost_usd`). The per-run numbers are in `docs/real-agent-pilot-2026-09-22-usage.json`.

| Mean per run | with instruction files (6 runs) | no_context (3 runs) | ratio |
| --- | --- | --- | --- |
| list dollars | $0.1201 | $0.0399 | 3.01 |
| all input tokens (input + cache write + cache read) | 171,726 | 120,642 | 1.42 |
| cache-write tokens | 21,534 | 3,519 | 6.12 |

- A least-squares fit of the nine runs gives cache writes at $4.00 per million tokens, cache reads at $0.20 and output at $10.00. The fit reproduces every run cost to within $0.0001. A cache write costs 20 times a cache read.
- The extra 18,015 cache-write tokens cost $0.0721. That is 90% of the $0.0801 gap. Eight of nine runs had two turns, so a written prefix was read back only once and never paid for itself.
- So the files add 1.42 times the input tokens, and cache-write pricing turns that into 3.01 times the dollars.

**3. The project file is the smaller part (inferred, not measured directly).** The project instruction file each run loaded was 3,669, 10,163 and 19,553 bytes (HorseTrack, confidence, organizze with its `@AGENTS.md` import). Its extra cache-write tokens against no_context were 15,548 to 21,393. A linear fit of those six deltas against file size gives about 0.32 tokens per byte plus a constant of about 14,400 tokens that does not change with the file. So the project file accounts for about 1,200 to 6,300 tokens of the gap. The constant, about 14,400 tokens, matches what `--setting-sources ""` also removed: the user-level context. This split rests on three file sizes. It was not measured by a run that loads the project file alone.

**4. A run that isolates the project file agrees.** The adversarial eval of 22 Sep (`bench/adversarial-2026-09-22/RESULTS.md`) used `--setting-sources project` in every condition, so only the project file differed. Mean cost: original $0.0849, corrected $0.0649, no_context $0.0795. With the user-level context held constant, no project file was not the cheapest condition.

Corrected claim: on this task, the extra cost came mostly from user-level context and cache-write pricing on two-turn runs, not from the project instruction file.

## Limits

- Three cases only.
- One model (`claude-sonnet-5` via Claude Code).
- One task type (neutral README / operating-guide discovery with a grounded start line).
- Not a Helicon product scorecard, not a prevalence estimate, and not proof that false pointers never hurt. A task that requires opening the path named in the instructions can still fail when that path is absent (as the earlier circular dry run showed by construction).

## Related

- Scripted (non-LLM) pilot return: day-run `CURSOR-HELICON-PILOT-RETURN.md` (21 Sep 2026).
- August hand verification: `docs/agent-context-report-2026-08.md`, `docs/agent-context-verification-2026-08-09.md`.
