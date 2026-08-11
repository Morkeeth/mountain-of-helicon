# Mount Helicon — final demo script

**Hard limit:** finish at 2:50 or earlier. Devpost judges are not required to watch
past 3:00.

**Privacy boundary:** use the seeded demo store for every visual finding and ruling.
Never show the real store's findings, Memory → Consistency, Brief, Golden Rules, or
local file paths. Do not open the Qwen Judge tab; its seeded state is intentionally
empty. Use the aggregate real-store report only through `helicon report --llm`.

## Recording path

### 0:00–0:12 — native macOS entry

Show the Mount Helicon mountain/count in the menu bar and open it. The icon is live
and the app opens the local dashboard.

Say:

> This is Mount Helicon, a native control point for the memory my agents use.

### 0:12–0:35 — the dangerous contradiction

On `http://localhost:8420`, show **Start Here** with the seeded Stripe question:

- “Is Stripe in test mode, or live with real money?”
- “Believe the wrong one and your agent charges real customers.”

Say:

> The store remembers two incompatible facts. Similarity search can retrieve both;
> it cannot decide whether both can be true.

### 0:35–1:12 — the terminal audit and safe repair

Run from the repository root:

```bash
cd ~/CODE/helicon
helicon heal --demo --reset
helicon heal --demo --apply
```

Let the before/after gates remain visible. The command operates only on the labelled
demo database and applies routine repairs while leaving human truth decisions visible.

Say:

> Helicon audits twelve ways memory rots. It can repair routine failures, then leaves
> real contradictions for a human ruling.

### 1:12–1:32 — Qwen judges

Paste this as one line:

```bash
HELICON_CONFIG=config-demo.json python3 -c "from helicon.qwen import get_client, complete; from helicon.config import load_config; print(complete(get_client(load_config()), 'Reply CONTRADICTION or CONSISTENT only.', 'A: Stripe is in test mode, charges are simulated. B: Stripe is live, every charge is real money.', model='qwen3.6-flash'))"
```

It must print `CONTRADICTION`.

Say:

> Qwen on Alibaba Model Studio judges the logical conflict directly.

### 1:32–2:02 — rule once, enforce immediately

Return to **Start Here**, choose **live — real money**, and hold on the locked receipt.
Then return to the terminal and run:

```bash
HELICON_CONFIG=config-demo.json helicon guard "Stripe is in test mode, safe to run a checkout"
```

It must print a blocked violation.

Say:

> I choose the current truth once. The ruling compiles into policy, and the guard
> blocks the ruled-wrong fact before another agent can write it.

### 2:02–2:28 — honest system report

From `~/CODE/helicon`, run:

```bash
helicon report --llm
```

Show the aggregate result only: `DEGRADED`, grounding `0.385`, and one broken task.

Say:

> On my full store, Helicon reports its weakness: degraded grounding and one broken
> task. It does not manufacture a green benchmark.

### 2:28–2:45 — Alibaba proof and close

Run:

```bash
curl -s http://47.237.3.97:8420/api/health
```

The endpoint must return `status: ok`. Do not navigate through the public dashboard
during this take; its frontend is current, but its seeded backend state must be
reseeded after recording.

Say:

> The public backend is running on Alibaba Cloud ECS in Singapore. Qwen supplies the
> judgment; the human ruling becomes enforceable memory policy. That is Mount Helicon.

## Preflight

```bash
cd ~/CODE/helicon
curl -s localhost:8420/api/findings | jq '.findings[0] | {title,question,consequence,options}'
curl -s http://47.237.3.97:8420/api/health
```

The local result must begin with `demo-stripe-live`. The public result must contain
`"status":"ok"`.
