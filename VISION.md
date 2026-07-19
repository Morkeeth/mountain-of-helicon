# Mount Helicon — Product Vision

**Mount Helicon is the control plane for agentic work.**

## Origin

It began as a second brain. The real problem arrived when it became a second
*workforce*: multiple harnesses, models, projects, and half-finished threads. You
could always ask for one more improvement — but you lost the ability to answer the
questions that actually matter:

- **What did we decide?**
- **What is true now?**
- **What did the agent actually ship?**
- **What should I do next?**

That is the problem Helicon exists for. Not "I built memory tooling" — *I lost
orientation over my own agentic work, and built the layer that gives it back.*

## What it is

As people work across Claude Code, Cursor, Codex, local models, and cloud agents,
their context fragments. Decisions drift, old facts return as if current, expensive
models are used by habit, and a long night of "one more prompt" can leave you with
more output but less clarity about what actually changed.

Helicon gives one person or team a **calm, inspectable system of record.** It
connects to the tools where work happens, preserves portable context and decisions,
checks memory for rot, and makes the state of agent work legible: what is trusted,
what is unresolved, what changed, what it cost, and what needs a human ruling.

Over time it becomes a **model- and harness-neutral operating layer**:

- choose the right model and harness for the job;
- move verified context safely between them;
- coordinate specialist agents without losing accountability;
- measure outcomes, cost, and reliability after the work is done;
- turn validated decisions into durable policy, while letting uncertain knowledge
  stay uncertain.

The goal is not an agent that does more work. It is a system that lets humans direct
**more agentic work without losing truth, judgment, or peace of mind.**

## The critical distinction

- **Super app** = where you *run* agents.
- **Helicon** = how you *stay oriented*, govern memory, and improve how those agents
  work.

We do not try to replace every harness. Helicon is the layer people open **before**
work to set direction, **during** work to provide trusted context and guardrails, and
**after** work to review outcomes and improve the next run.

## The five pillars (and where each stands today)

| Pillar | The promise | Shipped today | Next |
|---|---|---|---|
| **Truth** | What does the system currently believe, why, and how confident? | The 12-class rot exam; contradictions escalated to a human; rulings compiled into an enforceable guard; honest **DEGRADED** self-report | Confidence surfaced per belief; the meta-review (rule the engine's own judgments) |
| **Continuity** | Carry verified context, policies, and project state across models and harnesses | Multi-source read-only ingest; the tested TaskRun/ContextPacket recorder (objective ↔ frozen context ↔ artifact ↔ attested outcome), default-deny privacy | Move a verified context packet *into* a real agent run (proven received, not just candidate) |
| **Direction** | Decide which agent/model/harness should take which work, human-approved where stakes are high | Verified-outcome ledger; routing **withheld below a quality floor** (no coin-flip routes) | Evidence-backed recommendations once the causal signal exists |
| **Reflection** | Show what was produced, what changed, what worked, and what it cost | Run/outcome records; cost tracking; the receipt after every ruling | The morning reflection surface across a real day of runs |
| **Calm** | Replace infinite prompting with a finite review loop | Govern-by-exception: the machine handles the bulk, only genuine exceptions reach you; one-tap ruling → enforced → receipt → undo | The 9am briefing below |

## Honest language (a commitment, not a caveat)

We never say "absolute truth" or "optimal" — those are impossible promises. We say
**"the best-supported current operating truth"** and **"evidence-backed
recommendations."** It is both more honest and more compelling, and it is the same
discipline the product enforces on itself: a fact with weak support is shown as
weak, a route below the floor is withheld, uncertain knowledge is allowed to stay
uncertain.

## The north-star experience

> It is 9am. Helicon tells you: two memories are no longer trustworthy, one project
> is waiting on a decision, yesterday's expensive model did not outperform the
> cheaper one for this task class, and these are the three next actions worth your
> attention.

That is the whole product in one screen: **Truth** (two memories no longer
trustworthy), **Direction** (the expensive model didn't earn its cost here),
**Reflection** (what changed yesterday), and **Calm** (three things worth your
judgment — not three hundred).

## Where the current build sits

The shipped hackathon submission is the **govern half of Truth + Calm**: audit →
human ruling → verified apply → enforced guard → undo, with Qwen judging
contradictions and grounding, on a seeded high-stakes store, tested end to end. It
is the foundation the rest of this vision is built on — real, honest, and small on
purpose. Continuity, Direction, and Reflection have honest seeds (the recorder, the
floored router, the run ledger) and grow from here.

We push this until it's reality.
