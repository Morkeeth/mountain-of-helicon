# `helicon route` — a model-routing recommendation as a read of the eval store

## The thesis (why this falls out of Helicon, not bolted on)

Sriram Krishnan publicly asked for the app that picks the right model/harness for a given task. The usual instinct is to build a new benchmark. Helicon already has the harder half: it **verifies agent output against reality** (`helicon review --terminals` — is the "tests green" real, is the endpoint grounded, did the branch actually ship). Once you have verified outcomes attributed to the model that produced them, *"which model should I route this task to"* is not a new capability. **It is a ranked read of outcomes you already trust.**

That is the whole idea: routing is a *query over the eval store*, not a new oracle. A memory system that evaluates its agents' output by reality can answer "who is good at what" without ever running a synthetic benchmark, because every real task already left a verified receipt.

## How it works

```
review --terminals          route --record                    route
 (verify output vs      →    tag each verdict with       →     rank models by
  reality: tests,            model + harness + task-class      Wilson-scored
  endpoints, ship)           into route_evidence               verified-rate / class
```

Three honesty rules are enforced in code (`helicon/route.py`), not just documented:

1. **Outcome is a real reality-check, never a guess.** `verified` = pass, `contradicted` = fail. `unverified` (couldn't check) is *excluded from the denominator entirely* — it is never silently counted as a failure.
2. **The model is attributed from evidence.** It comes from the git `Co-authored-by` trailer of the commits that produced the output (the dominant model across the branch). No trailer → `unknown`, never invented. The harness is inferred from the commit signature (`Claude … <noreply@anthropic.com>` = Claude Code; Cursor/Codex sign differently).
3. **Ranking discounts small samples.** Models are ranked by the **Wilson score lower bound** of the verified-rate, so a lucky `1/1` (LB 0.21) never outranks a solid `9/10` (LB 0.59). Sample size and confidence travel *with* every recommendation. Below `--min-n` (default 5) it returns **insufficient evidence**, never a fabricated number; between a floor and the threshold it returns a clearly-labeled **provisional lean** with the raw counts attached.

No new verification engine: `route --record` reuses `review_terminals` (discover → ingest → extract → verify) as the single source of ground truth.

## The real numbers it produces today

Recorded from one live sweep of the real board (`helicon route --record --run`), 6 checkable outcomes, **all authored by `Opus 4.8 (1M context)` under Claude Code** (that homogeneity is itself the finding — see roadmap):

```
▸ testing:      insufficient evidence  (best: Opus 4.8 (1M context) 2/4, need n≥5)
▸ api-surface:  leaning  Opus 4.8 (1M context)  (verified 2/2)  — provisional, n<5, not a firm route
                Wilson LB 0.342 · raw rate 1.0 · need 3 more sample(s) to confirm
```

Two things worth stating plainly:

- **The router refuses to over-claim on its own board.** With `min_n=5`, no task-class has a firm cross-model pick, and it says so. That is the anti-fabrication guarantee working on real data, not a bug.
- **The `testing` 2/4 is a real signal.** Two of four "tests green" closeout claims (KYA/OKX, Taste Machine) *failed re-verification* — the suites did not actually pass as claimed. That 50% over-claim rate on test assertions is exactly why routing on *verified* outcomes (not self-reported ones) matters.

### What is roadmap, and why (honest)

A firm *"route X to model A over model B"* needs (a) ≥ `min_n` verified samples in a class and (b) more than one model in that class. Today's board is single-model (Opus 4.8) because that is what actually authored the work this week — so the cross-model comparison is **documented as roadmap, not faked**. The ledger is additive and idempotent per claim: it grows every sweep, and the moment a second model accumulates evidence in a class, `route` emits a real head-to-head (proven by `tests/test_route.py::test_ranks_models_by_wilson_and_makes_a_pick`). Nothing about the pipeline changes — only the evidence count.

## The 3-line version (for the Qwen demo / submission)

> Helicon verifies agent output against reality. Attribute each verified verdict to the model that produced it (git trailer) and you get a routing recommendation for free — ranked by Wilson-scored pass-rate per task-class, with sample size attached. On my real board it already flags that 2 of 4 "tests-green" claims were false, leans a model where evidence is positive, and says *insufficient evidence* everywhere it hasn't earned a pick — a router that refuses to fabricate confidence.

## A next reply to Sriram (draft)

> The model-picker you described falls out of output-verification. I built a memory system that checks each agent's output against reality — did the tests actually pass, is the endpoint real, did it ship. Attribute every verified outcome to the model that produced it and "which model for this task" is just a ranked read of that store: Wilson-scored pass-rate per task-class, sample size and confidence attached, "insufficient evidence" wherever it hasn't earned a call. Running on my own board it already catches that half my "tests green" claims didn't survive re-verification. The interesting part isn't the routing table — it's that the router won't recommend until reality has voted enough times.

## Commands

```bash
helicon route --record --run        # verify output across terminals, record evidence (runs test suites)
helicon route --record              # fast checks only (ship/endpoint/url; tests left unverified)
helicon route                       # rank from existing evidence
helicon route --task testing        # one task-class
helicon route --min-n 8             # stricter firm-pick threshold
```

Evidence lives in the `route_evidence` table (model, harness, task_class, verdict, receipt, per-claim idempotent). It is additive across sweeps.
