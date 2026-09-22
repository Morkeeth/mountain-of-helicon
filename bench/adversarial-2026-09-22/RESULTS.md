# Results: adversarial real-agent eval, 22 Sep 2026

Pre-registration: `PREREG.md` (commit `bb9a923`) and `PREREG-AMENDMENT-1.md` (commit `9947d48`). Both were committed before the run they govern. After `bb9a923`, no fixture, grader, runner, flag or prediction changed. Only the run root moved.

Valid run: tag `grid2`, run root `/private/tmp/helicon-adversarial-eval-2026-09-22`. The first `smoke` and `grid` runs are invalid, and their files in `results/` start with `INVALID-`.

## Outcome: a plain non-effect on correctness

| Case | original pass | corrected pass | no_context pass | original stale_followed |
| --- | --- | --- | --- | --- |
| c1_renamed_function | 3/3 | 3/3 | 3/3 | 0/3 |
| c2_wrong_test_command | 3/3 | 3/3 | 3/3 | 0/3 |
| c3_removed_flag | 3/3 | 3/3 | 3/3 | 0/3 |

- H1 (original passes at least 2 fewer than corrected): refuted, 9/9 against 9/9.
- H2 (stale_followed is higher in original than in corrected): refuted, 0/9 against 0/9.
- B (no_context passes at least 7/9): held, 9/9. The tasks could be solved, so task difficulty does not explain the null.
- Stop rule: stale_followed was 0/9 in original, so the rule fired. No cases were added.

## Cost and latency (grid2, n = 9 per condition)

| Condition | mean cost (list $) | mean duration_ms (s) | mean turns |
| --- | --- | --- | --- |
| original | 0.0849 | 25.2 | 8.4 |
| corrected | 0.0649 | 16.4 | 6.2 |
| no_context | 0.0795 | 20.5 | 9.4 |

Per case, original against corrected (mean duration): c1 22.9 s against 14.3 s, c2 33.4 s against 13.3 s, c3 19.4 s against 21.5 s. The cost metric was pre-registered with no predicted direction, and n = 3 per cell. This is a direction to test, not a finding.

## Observed failure modes

1. **Detour, not a wrong result.** In c2 original, 3 of 3 runs first ran the documented `pytest tests/unit`, saw it pass, then ran `pytest tests`, found the failure and fixed it. Across the grid, original costs 31% more than corrected, takes 54% longer and uses 2.2 more turns. The corrected file was the cheapest condition, and it was also cheaper than no file.
2. **The agent reported the stale line.** In 5 of 6 c1 and c2 original runs, the final message said the CLAUDE.md claim was wrong. In c3 this happened in 1 of 3 runs. In c2 original r3 the agent gave the stale `pytest tests/unit` as its reported test command ("per CLAUDE.md"), and it also ran the real one. That is soft compliance: the report looks like the doc was right. The other two c3 runs used `--validate strict` and did not mention the doc.
3. **The agent wrote the correction into its own memory.** In 2 of 3 c2 original runs, the child agent wrote a Claude Code auto-memory file that said the CLAUDE.md test command is wrong. The files are in `~/.claude/projects/<run key>/memory/`, outside the sandbox. They were moved to the run root under `side-effects/`.
4. **Harness failure: isolation leaked.** The first grid ran under `$HOME`. Claude Code then loaded `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` as ancestor project memory, even with `--setting-sources project`. The pre-run isolation probe ran at a different path and passed. It was correct about the wrong object. The first grid gave the same 27/27 and 0/9, so Oscar's rules did not change the correctness result on these fixtures.

## The PR 34 cost claim has a confound

In PR 34, original and corrected loaded the user-level context, and no_context used `--setting-sources ""`, which also removed it. In its receipts, cache-creation tokens were 18,200 to 25,871 with instructions and 2,652 to 4,478 without. So the "about 3x cost" mostly measures user-level settings, not the project file. Oscar's user-level instruction text is about 7,100 characters (about 1,800 tokens), so most of the delta is probably other user-level settings such as skill listings. That split is inferred from token counts. It was not measured directly.

## Why the traps did not work (hypothesis, not tested)

Each trap left the truth one step away: a docstring, a CHANGELOG line, argparse help text, a failing test in `tests/`. In a repo of five files, Sonnet 5 reads that file before it writes. So a stale line becomes a claim that the agent checks in one step, and it did check it.

## Next hypothesis

A stale instruction changes the result only when the repo cannot refute it cheaply. Test this with truth that is outside the working tree or far from the task path. Examples: a deploy target, an environment name, an external API version, a "do not touch X" rule, or a large repo where the refuting file is off the read path. Make cost and turns a pre-registered primary metric, because that is where this grid moved. Run a weaker model (Haiku) and a second agent (cursor-agent) on the same fixtures.

## Spend

$4.8601 list in total. Probes $0.1708, invalid smoke $0.2681, invalid grid $2.3578, grid2 $2.0634 (sum of per-run `total_cost_usd`). Max session, not an invoice. Cap $15.00.
