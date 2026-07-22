# Codex final arbiter — Mount Helicon V2.3

**Target:** `~/CODE/helicon-v2-night-run-2026-07-21`, branch
`night-run/2026-07-21-helicon-v2`, including the uncommitted V2.3 working tree.
`main` at `0eef89f` is a frozen submission. Do not touch, merge, push, deploy, or
write to it. This is a review, not a build task.

**Read first:**

1. `~/CODE/helicon-product-vision-v2.md` — especially *the three-tier spine*,
   *meta-review*, *valuation problem*, and *two loops*.
2. `NIGHTRUN-2026-07-22.md` — the honest V2.2 receipt.
3. `CODEX-REVIEW-PROMPT.md` — historical context only. Its claims and old base
   do not override the V2.3 working tree.

## Paste into Codex

```
You are the final independent arbiter for Mount Helicon V2.3. Review the
working tree, not just the committed branch. This is a read-only code and
product audit: do not edit, push, deploy, or use the operator's live database.

Mount Helicon's actual ambition is not a prettier memory audit. It is a
memory-governance cockpit for one operator running many agents:

  real work begins with a frozen objective, acceptance contract, and eligible
  context → the agent runs → Helicon captures the real artifact and context
  delivered → the operator judges the outcome → only accepted learning improves
  the next run. Most mechanical noise is handled automatically; the human sees
  genuine exceptions and can correct the engine itself.

Do not adopt the author's framing or treat passing tests as proof. A green
suite has missed real failures in this project. Separate mechanism evidence,
product truth, and unverified claims. Comments in the code are claims to attack.

Your review has TWO required parts, in this order.

=== PART 1 — NORTH-STAR ARBITRATION ===

First answer this before reviewing implementation details:

Does V2.3 materially move the product toward the governed real-work loop above,
or is it mainly polishing the old memory-audit queue?

Trace one concrete operator day from a real Claude Code prompt through:

1. objective and acceptance frozen BEFORE execution;
2. exact context actually delivered to that session;
3. real artifact, model/harness, time/tokens/cost captured;
4. deterministic → model → operator review of the outcome;
5. an accepted ruling changing the next agent's context or reusable prompt;
6. a receipt that distinguishes recorded, delivered, and obeyed.

For every step, label it IMPLEMENTED AND PROVEN, IMPLEMENTED BUT UNPROVEN,
DESIGNED ONLY, or ABSENT. Do not let an imported retrospective capture count as
forward governance. Do not let a database write count as delivery or obedience.

Then give a direct verdict:
- `NORTH STAR: ADVANCES` only if the working product makes a real operator's
  next agent run measurably safer or better.
- `NORTH STAR: MAINTENANCE ONLY` if V2.3 mostly reduces queue volume or changes
  navigation without closing the real-work loop.
- `NORTH STAR: REGRESSES` if it creates false trust or hides information.

If the answer is not ADVANCES, name the one smallest ambitious slice that would
make it advance. Do not propose feature accumulation or a generic roadmap.

=== PART 2 — V2.3 TRUST AUDIT ===

Now attack the actual V2.3 changes.

### A. Valuation gate

Files: `helicon/valuation.py`, `helicon/db.py`,
`helicon/api/findings.py`, `helicon/cli.py`, `tests/test_valuation.py`.

The gate claims a finding earns human attention only if its target has
consequence, still needs a human, and remains true. On a copy of the real store
it claims to reduce 335 open findings to roughly 90.

Find any real finding it can silently eat. Prioritize:

1. Whether `killed` or `superseded` genuinely means unreachable across EVERY
   retrieval, ContextPacket, consolidation, prompt, portrait, and agent path.
   Check `embeddings._load_all_embeddings`, `db.search_cubes`, `taskrun`, and
   every divergent status predicate. A status is terminal only if all consumers
   agree.
2. Whether `_normalize()` can collapse two different findings into a dismissed
   precedent. Treat the test's `scout` versus `track` example as a claim to
   interrogate, not a valid precedent by default.
3. Whether machine decisions can influence Golden Rules, triage rules, utility
   learning, or any human-decision-only path. Check `gold.py`, review APIs,
   utility, undo, and all `audit_log` readers.
4. Whether the main Findings API is the only queue consumer. Find any Brief,
   CLI, MCP, Cockpit, or log view that still treats a machine-retired finding as
   human-pending, or makes a machine retirement invisible.
5. Whether not using `retrieval_log` is the correct safety choice given sparse
   coverage. Do not recommend using missing usage data to auto-retire findings.
6. Whether `_still_true()` is an honest safety rail or merely decorative.

The gate must default toward surfacing ambiguity, never toward silently hiding
it. State plainly whether it is safe to apply to the real 9,081-memory store.

### B. Navigation subtraction

Files: `web/src/App.tsx`, `web/vite.config.ts`.

The top navigation went from 19 tabs to five. Verify actual user reachability,
not merely whether component branches remain in source. Test deep links,
keyboard paths, and whether any removed surface was the sole entry to an
operational flow or receipt. Generated `web/dist` is deployment output: inspect
source first, then verify the build matches it; do not count generated churn as
independent scope.

### C. Governed Run / hook truth

Independently assess whether these must be fixed before any new slice:

- `helicon run open` writes a TaskRun that `/api/run/list` and `/api/run/detail`
  cannot display because they begin at `run_captures`.
- The hook records a real delivery event, but Cockpit reports
  `delivered_to_live_run: false`.
- The installed `helicon` command may resolve to another checkout lacking
  `run` and `hook`, while `--print-config` tells Claude Code to invoke it.

Rank their severity by the actual operator failure, not by code neatness.

=== REPRODUCTION RULES ===

Never run `--apply` against the live store. Create a transactionally safe SQLite
backup first, configure Helicon to use only that copy, and verify state before
and after apply/undo. Count equality alone is not enough: compare grouped
`human_decision` and `machine_decision` states before and after.

Do not claim the frontend builds unless it builds using the repository's normal,
pinned developer runtime. If no runtime is pinned and the default fails, call
that a reproducibility defect even if an alternate local Node version succeeds.

=== REQUIRED DELIVERABLE ===

Return, in this exact order:

1. `NORTH STAR: ADVANCES | MAINTENANCE ONLY | REGRESSES`, with the six-step
   real-work-loop scorecard.
2. A ranked defect list, each item containing severity, exact `file:line`, a
   concrete failure scenario, and whether it blocks real-store application,
   slice 3, or deployment.
3. `REAL-STORE GATE: PASS | FAIL` and why.
4. `SLICE-3 GATE: PROCEED | STOP` and why.
5. The single highest-leverage next change. It must either close the most
   dangerous trust gap or create the smallest real forward-governance loop.
   Do not reward incremental queue polishing as product progress.

Be blunt. Pitfalls, omissions, and false claims matter more than reassurance.
```

## Safe reproduction block

```bash
cd ~/CODE/helicon-v2-night-run-2026-07-21
review_dir=$(mktemp -d /tmp/helicon-final-review.XXXXXX)
export REVIEW_DIR="$review_dir"
python3 - <<'PY'
import json, os, sqlite3
src = sqlite3.connect('/Users/morkeeth/CODE/helicon/data/helicon.db')
dst = sqlite3.connect(os.path.join(os.environ['REVIEW_DIR'], 'copy.db'))
src.backup(dst)
dst.close(); src.close()
with open(os.path.join(os.environ['REVIEW_DIR'], 'config.json'), 'w') as f:
    json.dump({'db_path': os.path.join(os.environ['REVIEW_DIR'], 'copy.db'),
               'connectors': {}}, f)
PY

HELICON_CONFIG="$review_dir/config.json" PYTHONPATH=. python3 -m helicon queue
HELICON_CONFIG="$review_dir/config.json" PYTHONPATH=. python3 -m helicon queue --apply
HELICON_CONFIG="$review_dir/config.json" PYTHONPATH=. python3 -m helicon queue --undo
PYTHONPATH=. python3 -m pytest tests/ -q
```

Do not reveal this file's prior review conclusions to Codex before its blind
round. Compare them only after the independent verdict arrives.
