# `helicon score-runs` / `helicon runs` — scoring whole runs

## The thesis (why this is the same loop, one level up)

`review --terminals` verifies a terminal's output against reality. A **run** is that one level up and made cost-aware: a burst of agent work has a real **yield** (verified output) and a real **cost** (time + tokens), so it can be *scored* instead of vibed:

```
score = verified yield / cost - damage
```

Every term traces to a real source. Nothing is invented, and where evidence is thin the surface says so rather than guessing.

## Where each term comes from

| Term | Source | Honesty rule |
|---|---|---|
| **cost** | `~/.claude/projects/.../*.jsonl` transcript `usage` (output tokens) x wall-clock hours | Top-level usage only, not the double-counting `iterations`. A file with no assistant usage yields no record (never a fabricated zero-cost run). |
| **yield** | `route_evidence` (the `review --terminals` verdicts): verified / (verified + contradicted) | `unverified` (uncheckable) is excluded from the ratio, never counted as a failure. |
| **damage** | an incident flag (e.g. the Jul-14 RAM freeze) | A disclosed penalty term. The incident is real; the magnitude is a stated parameter. |

## Run identity

Sessions are clustered into runs by **start burst**: sessions that kick off within a gap (default 5h) are one run; the next run begins after a quiet gap. Clustering on start time, not activity span, so a long session left open cannot bridge two days into one blob. On the real board, 83 sessions cluster into 33 day-scale runs matching the god-mode narrative (a "3-terminal morning run" shows up as one run of parallel sessions).

## A real run card

```
RUN CARD  run-2026-07-14T07:40
span      2026-07-14 07:40 -> 09:50  (130.6m, 6 session(s))
model     opus-4-8
cost      1.83M output tokens x 2.18h  =  3.975 Mtok-h
yield     4/6 verified (ratio 0.667; uncheckable excluded)
score     4 verified / 3.975 cost = 1.01  -  damage 0.3  ->  SCORE 0.71
```

The freeze that killed the machine mid-run is the 0.3 damage term, so the score docks the run that cost the afternoon. The yield carries an earlier honesty catch: 2 of the 6 checkable claims were false on re-verification.

**Scope, stated honestly:** the yield reads `route_evidence`, which reflects CURRENT repo state, so it is valid for the LATEST/active run (its output IS the current state). A run's card is cut and persisted while it is current (`runs --close`), which stamps the yield as-of that moment. Per-run *historical* re-verification (checking each run's commit window at that time) is future work, flagged in code, not faked. A card for the active run also shifts as the run grows; it stabilizes once the run is over.

## Suggestions (read off real history)

`runs --suggest` produces only what the history supports:
- **shape**: average score for focused runs (<=2 sessions) vs fleet runs (3+), once there are >=3 scored cards; below that it says insufficient rather than compare on one data point.
- **model / route**: the top recommendation from the `route` read of the eval store.
- **next run**: flagged as roadmap. Ranking the highest-leverage next run needs an open-next-steps source (the dashboard/todo); it is not wired to one yet and is not faked.

## Commands

```bash
helicon score-runs                       # runs, start-clustered (default view)
helicon score-runs --sessions            # raw per-session cost table
helicon score-runs --card [--damage D]   # one full run card for the latest run
helicon score-runs --card --persist      # cut + save the card to run_cards
helicon runs                             # Latest: the scored run-card history
helicon runs --suggest                   # + suggestions read off the history
helicon runs --close [--run] [--damage D]  # closeout hook: refresh evidence + persist the current card
```

The closeout hook (`runs --close`) is meant to be called at end of session by a flow or cron, so the run ledger compounds over time. It is a single process (no new parallelism), which respects the local RAM ceiling. Evidence is never downgraded: a fast close (no `--run`) will not overwrite a prior `--run` sweep's verified/contradicted verdicts with `unverified`.
