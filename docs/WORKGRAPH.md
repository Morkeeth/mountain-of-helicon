# Agentic Work Graph initiative

Tracking: [GitHub issue #1](https://github.com/MorkeethHQ/mount-helicon/issues/1)

Mount Helicon is the measurement and control plane for agentic work. The
**Agentic Work Graph** joins the things every coding-agent stack currently leaves
fragmented: what the system believed, what context it gave an agent, what skills
and policies were available, what the agent ran, what it produced, what the human
ruled, and what changed in reality.

Accountable output is one loop inside that larger system. A completed agent task
is activity; it becomes valuable output only when it advances a declared human
goal and carries evidence for that change.

## Product wager

```text
memory + skills + policy
        ↓
goal → work card → next move → prompt + frozen context → run + artifact + cost
     → outcome evidence → human ruling → next move
        ↓
memory / context / skill / routing learning
```

A **Work Card** (implemented internally as a `Wager`) is opened before execution
and freezes five things:

- intent — the outcome being pursued;
- beneficiary — who receives the value;
- observable change — what will be different in the world;
- evidence contract — the proof required to claim that change;
- kill condition — when to stop investing.

Execution evidence (a diff, test result, deploy, or artifact) is necessary but
does not prove an outcome. `unproven` is therefore a first-class result, never a
hidden pass.

## What Helicon measures

| Organ | The questions it answers |
|---|---|
| Memory | What does the system believe, why, and what is stale or contradictory? |
| Context | What reached a specific agent run; what was missing, redundant, unsafe, or drifted? |
| Skills | Which instructions/tools were available and used; which are stale, conflicting, or linked to rework? |
| Runs | What did each harness/model do, cost, produce, and survive? |
| Work | What human outcome was pursued; what remains unproven; where is work spinning? |
| Policy | What did the human rule, where is it enforced, and did it recur? |

The graph is the join. It must preserve evidence and abstain where it lacks it;
model or harness recommendations are withheld until verified outcomes support them.

## Build plan

### 1. Unified event graph — active now

Give every work record stable provenance: `TaskRun`, `ContextPacket`, context
items/memories, skills, artifacts, Work Cards, evidence, human rulings, and next
moves. The first trace is read-only and must show the complete chain without
inventing causal claims.

### 2. Cross-layer measurement

Compute and surface memory freshness/contradictions, context packet quality and
drift, skill health/use, run cost/rework/verification, and outcome status. Every
metric cites the records it used.

### 3. Control plane

Use that graph before and during work: trusted context packets, policy guard,
skill review, and the Prompt Gate. The gate is one control, never the whole
product.

### 4. Calm command surface

The dashboard and macOS app render the same cross-layer brief: the few
interventions worth a human decision, with drill-down into Memory, Context,
Skills, Runs, Work, and Policy.

### 5. Evidence-backed learning

Only after real connected records accumulate: recommend a harness, model, skill,
or next move above an explicit evidence floor; otherwise say insufficient
evidence.

## Implemented first vertical: dogfooded work contract

The first vertical is local-first and manual by design. It extends the existing
`TaskRun` / `ContextPacket` recorder without pretending that every harness is
already instrumented.

1. Open a Wager before work.
2. Optionally link it to a `TaskRun`.
3. Attach read-only evidence after work.
4. Resolve it as `proven`, `disproven`, or `unproven`.
5. Record the next human-approved action separately.

The loop now has an explicit repair path: a Work Card opened before execution
can be linked to its real `TaskRun` later, but never inferred. A `proven` or
`disproven` outcome requires both a human ruling and at least one outcome
evidence receipt; `unproven` remains available when the world has not answered.

The **attention queue** is the first calm control surface over the graph. It
reports only missing record edges: no linked run, no frozen context packet,
an executing run with no artifact, an unverified artifact, verified execution
without outcome evidence, or an open card with no next move. It is not a model
score or a generated task list.

Missing edges are independent: a zero-context warning never suppresses the
separate warning that a verified run still lacks beneficiary/world outcome
evidence. The queue is ordered by urgency, not truncated to the first defect.

Each Work Card trace also renders a chronological local record: card opening,
approved moves, run opening, frozen context, artifact attachment, verification,
skill review, receipts, and eventual human outcome ruling. It orders existing
timestamps only; it does not infer causality or manufacture a narrative between
events.

## Local capture adapter — implemented

`helicon capture` is the first real bridge from a local coding-agent workflow
to the graph. It never starts an agent or runs a test on the operator's behalf.
It records the facts available at each boundary:

```text
helicon capture launch
  Work Card → TaskRun → frozen, privacy-filtered ContextPacket

agent works locally

helicon capture close
  local artifact bytes → SHA-256 manifest → human verification receipt → Work Card evidence
```

Launch requires the Work Card and its acceptance test before execution. Close
requires readable local artifact files, an explicit `verified`, `contradicted`,
or `unverified` result, and a human evidence string. It hashes bytes locally;
it does not trust a path, timestamp, or agent closeout claim. The Work Card
still needs a separate human outcome ruling—execution verification is evidence,
not a claimed user outcome.

The graph preserves the distinction in its receipts. Test, artifact, context
decision, and TaskRun-verification receipts are execution evidence. A `proven`
or `disproven` human outcome additionally requires an explicitly outcome-facing
receipt: `user-feedback`, `human-observation`, `business-metric`, or an
`outcome-*` kind. A passing test alone cannot resolve a Work Card.

Closeout also records a local wall-clock interval from the frozen packet to the
artifact attachment. It is labelled wall elapsed time, not active work time.
Harness token counts are recorded only when both observed input and output
counts are supplied; otherwise token usage is explicitly `unknown`. Dashboard
and macOS coverage report those two measurement edges separately.

The same boundary is available to connected coding agents through MCP:
`helicon_capture_launch` first verifies the accepted Work Card through the
Prompt Gate, then freezes the run. `helicon_capture_closeout` accepts only
readable local artifact paths plus an explicit verification receipt. This gives
Claude Code, Cursor, and Codex the same local capture protocol without a
harness-specific cloud integration.

For Claude Code, the existing global Stop-hook chain now invokes the
project-scoped `scripts/claude-capture-reminder.sh`. It emits a non-blocking
closeout reminder only when a Helicon `agentic-work` run is still `executing`
or `artifact_attached`. The hook never creates, closes, verifies, or resolves
a record; it preserves the human verification boundary.

The coverage chain is now emitted by the canonical Morning Brief, under
Continuity: linked run, frozen context, context containing eligible memory,
declared skills, artifact-bearing run, verified run, and outcome-evidence
receipt. The surface reports these as separate facts; a frozen-but-empty packet
is explicitly different from useful carried context.

Declared skill names are not treated as evidence of their instructions. For each
declared version, `helicon wager review-skill` or
`helicon_workgraph_review_skill` records a SHA-256 snapshot of the exact local
instruction file that was inspected. Missing snapshots become a factual Work
Graph intervention. This is provenance, not a quality verdict: the existing
Skills audit continues to diagnose duplicate, colliding, or thin skills.

## Cursor Cloud handoff — implemented

Cursor Cloud Agents cannot rely on local hooks or reach the local Helicon
database. The bridge is a declarative manifest rather than a remote write:

1. Locally call `helicon capture manifest --task-run <id>` after a captured
   launch; hand that JSON contract to the Cloud agent.
2. The Cloud agent writes its artifact paths, SHA-256 values, and actual test
   receipt into the manifest alongside the synced repo changes.
3. Locally call `helicon capture ingest --manifest <file> --repo <repo>`.

Ingest constrains every path to the repo, re-hashes the local synced bytes, and
rejects mismatches before it records the closeout. A Cloud manifest is a claim,
not evidence, until that local check passes.

## Evidence-backed learning — implemented, intentionally thin

`GET /api/workgraph/learning` and `helicon_workgraph_learning` group only
resolved, run-linked Work Cards by harness, model, and declared skill. Each
group must have at least five resolved cards before it is even described as an
observation with sufficient evidence. Until then the dashboard, Brief, and MCP
all say recommendations are withheld. A diff, test receipt, or a single proven
card never becomes a routing recommendation.

The first usable **Prompt Gate** compiles an execution prompt only for an accepted
`BUILD` or `REPAIR` move. It abstains for `ASK`, `DECIDE`, `INVESTIGATE`, and
`KILL`, rather than laundering a human decision into another agent task.

This produces the Work node needed to join existing memory, context, skill, and
run records. It does not displace them. Until real resolved Work Cards exist,
Helicon must withhold optimization claims.

## First dogfood

The Workgraph itself is the first Wager: help an agent-heavy solo builder reject
maintenance theatre and choose the next action worth sending. Its proof is real
usage on active Helicon work, including explicit rejected tasks—not a seeded demo.

## Surface plan

The product IA stays broad. The existing dashboard should expose **Memory**,
**Context**, **Skills**, **Runs**, **Work**, and **Policy** as connected organs.
Work lives within Next Moves first, rather than becoming the whole navbar. The
macOS sentry exposes the same priority count; the cockpit and Morning Brief show
the corresponding work/context/skill evidence.
