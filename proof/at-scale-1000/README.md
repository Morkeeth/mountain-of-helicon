# 1,000 unattended agent runs on frozen public repositories

Run on 18 and 19 Oct 2026. This folder holds the scripts, the frozen list and the per-run results.
You can check every published number with one command:

```bash
python3 proof/at-scale-1000/verify.py      # standard library only, exit 0 when all checks pass
```

## What this proves, and what it does not

The checker under test is **not `helicon review`**. It is a small check for one defect:
a GitHub Action `uses:` reference that is not pinned to a full 40-character commit SHA.
The run tests the evaluation method Helicon uses (a frozen population, code-owned ground truth,
a precision sample, a logged cost per run). It shows that the method runs unattended at 1,000 repositories.
Helicon's own review has not yet run at this scale.

| Number | Value | Source |
|---|---|---|
| Frozen repositories | 1,000 (100 per language, 10 languages) | `repos-frozen.jsonl`, sha256 in `agent-summary.json` |
| Agent runs, unattended | 1,000 of 1,000 | `agent-runs-public.jsonl` |
| Full six-step protocol | 1,000 of 1,000 | same |
| Outcomes | 463 finding, 442 no workflows, 93 clean, 2 error | same |
| Failure rate | 0.2% (one repository removed after the freeze, one needed git-lfs) | `summary.json` |
| Precision and recall, random 50 | 1.0 and 1.0, agent and static check agree | `precision-agent-vs-static.json` |
| API spend | $0. The model ran on a claude.ai subscription. List price proxy $53.53 | `agent-summary.json` |
| Messages sent to repository owners | 0 | `agent-summary.json` `outward_actions` |

The precision sample is 50 runs. The static check and the agent agree on all 50; that measures agreement
with the code-owned rule, not agreement with a human reviewer.

## Files

| File | What it is |
|---|---|
| `run_scale.py` | Freeze the population (`gh search repos`), run the static check, summarise, label |
| `agent_scale.py` | Prepare inputs, run one `claude -p` agent per repository, score |
| `repos-frozen.jsonl` | The frozen list of 1,000 repositories |
| `runs.jsonl` | Static check, one row per repository |
| `agent-runs-public.jsonl` | Agent runs, one row per attempt (1,005 rows; the last row per repository counts) |
| `summary.json`, `agent-summary.json` | Published numbers |
| `precision-sample.json`, `precision-agent-vs-static.json` | The 50-run precision sample |
| `verify.py` | Recomputes the numbers from the rows above |

## Left out on purpose

The full agent traces (`agent-traces/`), the per-run work folders (`agent-inputs/`) and the
fix suggestions stay on the author's machine. They contain local paths. In the public rows,
local paths are rewritten to `./`, and the raw `trace` and `output` fields are dropped.

## Run it again

Re-running writes into this folder and needs network, `gh`, `git` and the `claude` CLI on a subscription.

```bash
python3 run_scale.py freeze        # writes a NEW frozen list; its hash will differ
python3 run_scale.py scan
python3 agent_scale.py prepare
python3 agent_scale.py scan
python3 agent_scale.py score
```

A new freeze picks new repositories, so expect different counts. Use `verify.py` to check this run.
