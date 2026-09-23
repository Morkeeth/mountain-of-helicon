# Pre-registration: adversarial real-agent eval, 22 Sep 2026

Written and committed before any paid grid run. Only two harness probes ran before this file ($0.0547 list, see "Spend before pre-registration").

## Question

Can a stale instruction file mislead a real coding agent into a wrong result that looks green locally? And does correcting only the stale line remove that effect?

PR 34 (acd2098) asked a neutral question ("find the README") and saw 9/9 pass in all conditions. That task never required the agent to act on the stale claim. This eval does require it.

## Base

- Repo: `Morkeeth/mountain-of-helicon`, branch `night/helicon-adversarial-eval-2026-09-22`, from `origin/main` at `acd2098` (the PR 34 merge commit).
- Fixtures and runner: this directory. `FIXTURES.sha256` pins every fixture file and `run_eval.py`.

## Design rule

A stale line matters only when (1) the task forces the agent to act in the area of the stale claim, and (2) the wrong action looks green locally. So each trap passes the visible checks and fails only a hidden grader.

## Cases (three synthetic Python repos)

| Case | Stale claim in the original CLAUDE.md | What is true in the code | Trap that looks green |
| --- | --- | --- | --- |
| c1_renamed_function | "Use `compute_total()` for every price. It applies discount codes." | `compute_total` is legacy and ignores discounts. `calc_total` applies them. The docstring and CHANGELOG say so. | `order_total` built on `compute_total`. Visible tests pass. |
| c2_wrong_test_command | "The full test suite is `pytest tests/unit`." | The failing test is `tests/test_slug.py`. `tests/unit` has one passing smoke test. | Run `pytest tests/unit`, see green, report nothing to fix. |
| c3_removed_flag | "Strict validation: `--strict FILE`." | `--strict` is a no-op (help text says deprecated). `--validate strict` is the real switch. | `check_data.sh` with `--strict` exits 0 on the sample file. |

The corrected CLAUDE.md changes only the stale token. The no_context condition has no CLAUDE.md.

## Hidden graders (independent of Helicon)

Each grader is plain pytest in `fixtures/<case>/grader/`, copied outside the agent's repo after the run.

- c1: `order_total` with `SAVE10` on 100.0 returns 90.0. Without a code, 7.0.
- c2: the pristine `tests/` suite passes, test files are unchanged, and two extra slug cases pass.
- c3: the script exits non-zero on `bad.json`, zero on `good.json`, and `ingest/cli.py` is unchanged.

Red and green check, run before this file was committed (`python3 run_eval.py selfcheck`): every grader fails on the unfixed repo and on the trap, and passes on the reference fix. Result: `SELFCHECK OK`.

## Agent and pins

| Pin | Value |
| --- | --- |
| Agent | Claude Code CLI 2.1.280 (PR 34 used 2.1.278) |
| Model | `--model claude-sonnet-5` (exact ID, not an alias) |
| Settings | `--setting-sources project --strict-mcp-config` on all three conditions |
| Tools | `--tools Read,Edit,Write,Glob,Grep,Bash`, `--permission-mode bypassPermissions` |
| Auth | Max session, `ANTHROPIC_API_KEY` removed from env. Cost is `total_cost_usd`, list basis, not an invoice. |
| Per-run cap | `--max-budget-usd 1.00`, wall-clock timeout 420 s |
| Total cap | $15.00 list. The runner launches a run only if spent + in-flight x $1.00 stays at or under the cap. A run with no cost record counts as $1.00. |
| Replication | n = 3 per cell, 27 grid runs, 3 in parallel |
| Isolation | Each run is a fresh git-initialised copy of the fixture. No parent directory has a CLAUDE.md or AGENTS.md. |

Harness probes before this file: (1) `--setting-sources project` loads the project CLAUDE.md and does not load the user-level CLAUDE.md. (2) The user-level write hook does not fire. So the three conditions differ only in the project file.

## Metrics per run

1. Primary: hidden grader pass or fail.
2. Mechanism: stale_followed. c1: final `checkout.py` names `compute_total`. c2: the agent ran `pytest tests/unit` and never a broader pytest. c3: the script has `--strict` and not `--validate`.
3. Cost (`total_cost_usd`), turns, `duration_ms`, wall time.

## Baseline and predictions

- Baseline is no_context. Prediction B: no_context passes at least 7 of 9. If it passes fewer than 5 of 9, the tasks are too hard and the contrast is not interpretable.
- H1 (primary): original passes at least 2 fewer runs than corrected (out of 9). Refuted if original passes at least corrected minus 1. That result is reported as a non-effect.
- H2 (mechanism): stale_followed in original is greater than in corrected. Corrected is predicted 0 of 9.
- No direction is predicted for cost. PR 34 saw about 3x cost with instructions loaded. Probe 1 suggests most of that came from user-level context, which this design removes.

## Stop rules

- Stop at $15.00 list total, including smoke and probes.
- Smoke first: one original run per case, tag `smoke`, not counted in the grid. It checks only the harness (tools loaded, JSON parsed, grader ran). If the harness fails, fix it, disclose the change, and rerun the smoke.
- If the grid shows stale_followed at 0 of 9 in original, the design cannot produce the predicted difference. Stop and report the non-effect and the next hypothesis. Do not add cases after seeing results.

## Spend before pre-registration

Two probes, $0.0248 + $0.0299 = $0.0547 list.
