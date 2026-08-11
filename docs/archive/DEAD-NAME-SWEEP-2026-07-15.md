# Dead-name -> live-consequence sweep

**Date:** 2026-07-15
**Scope:** every git repo under `~/CODE` (27 repos). `~/CODE/recall` excluded by hand (journal, hard boundary).
**Method:** R4 (`helicon rot`) for leads, then live surfaces R4 structurally cannot see: env var names, untracked config, launchd plists, registry lookups, published registries, and production API state.
**Status:** not committed. Read-only throughout. No push, no deploy, no writes to any repo but this one.

---

## Headline: the premise is wrong, and the wrong premise mis-fixes the bug

The brief says `agent:relay` is a dead name (RELAY->FAVOUR, renamed 2026-07-02) that silently
blacked out the 8-agent layer for 13 days.

The blackout is real and is still live in production right now. **The rename did not cause it.**

`"relay"` was never a key in `AGENT_REGISTRY`. Not on 2026-07-02, not before it, not in any commit
in the entire history of `src/lib/agents.ts`:

```
$ cd ~/CODE/world-relay && for c in $(git log --format=%h --follow -- src/lib/agents.ts); do
    git show "${c}:src/lib/agents.ts" | grep -qE 'id:[[:space:]]*"relay"' && echo "$c HAS id:relay"; done
  NO commit in the entire history of agents.ts ever defined id:"relay"

first commit 1f5eb77: id:"pricehawk" id:"freshmap" id:"queuewatch" id:"accessmap" id:"plugcheck"
                      id:"shelfsight" id:"greenaudit" id:"bikenet" id:"claimseye" id:"listingtruth"
current HEAD:         id:"shelfwatch" id:"freshmap" id:"queuepulse" id:"propertycheck"
                      id:"dropscout" id:"openclaw" id:"hermes" id:"claudecode"
```

Production confirms the timeline. Of the 41 agent-posted tasks live on the board, 12 were created
**before** the rename, while `relay` was still the correct, current, live name. They are broken
identically to the 29 created after it:

```
$ curl -s https://world-relay.vercel.app/api/tasks   # HTTP 200, 95 tasks
RELAY->FAVOUR rename date: 2026-07-02

agent:relay tasks created BEFORE the rename : 12  (agent null: 12)
agent:relay tasks created AFTER  the rename : 29   (agent null: 29)
```

And the dead-name fix does not fix it. Executing the real registry:

```
$ node proof.mjs   # keys parsed out of the live src/lib/agents.ts
AGENT_REGISTRY keys actually defined: [ 'shelfwatch','freshmap','queuepulse','propertycheck',
                                        'dropscout','openclaw','hermes','claudecode' ]
getAgent("relay")      -> null
getAgent("favour")     -> null      <-- the "fix" is also null
getAgent("shelfwatch") -> { id: 'shelfwatch' }
```

`s/relay/favour/` produces exactly the same outage under a live name, where nobody would think to
look for it again.

**The real class is not "a dead name in a code path". It is "an unvalidated string default feeding a
lookup with no error path".** The name being dead was cosmetic coincidence. `"relay"` was a *project*
name used as an *agent id*, a category error that was already broken on day one. The rename made a
day-one bug look like a rename bug, which is worse than either, because it points the fix at the
wrong line.

This also explains why R4 could never have caught it. R4 greps for **names**. The bug lives at the
**lookup**, on a line that contains neither name (`store.ts:104`). R4 found the symptom's spelling
and missed the mechanism.

---

## Live production state (ground truth, read-only)

```
$ curl -s https://world-relay.vercel.app/api/tasks     -> HTTP 200, 158002 bytes, 95 tasks
tasks posted by an agent identity : 41
agent id in poster string         : {'relay': 41}
of those, agent field resolved    : 0
of those, agent field NULL        : 41
human/wallet-posted (agent null is CORRECT): 54
```

Adversarial checks on that claim, all survived:

| Hostile challenge | Result |
|---|---|
| `agent` is simply never serialized, so null proves nothing | `'agent' in task` -> **True**, value `None`. The key is emitted. |
| Some task somewhere resolves, so it's partial | non-null agent count across all 95: **0** |
| These are stale pre-fix rows | 29 of 41 created **after** the rename; earliest 2026-06-26, latest 2026-07-06 |

100% of the agent-posted board is blacked out. 8 named agents, 0 attributions.

---

## Ranked by blast radius

### 1. `seed/route.ts` writes the dead name and bypasses the observability fix (LIVE, SILENT)

- `src/app/api/seed/route.ts:68` sets `const agentId = ... ? t.agentId : "relay";`
- `src/app/api/seed/route.ts:11,12,13`: three hardcoded `agentId: "relay"` seed tasks
- `src/lib/store.ts:104` runs `const agent = input.agentId ? getAgent(input.agentId) : null;`

`store.ts:104` is the silent null. No log, no throw, no error path. `getAgent` returns `null` and
`createTask` writes `agent: null`.

The fix that landed today went to `/api/tasks` only. That path now calls `resolvePostingPrivilege`
and logs `[agents] UNKNOWN agentId=`. **`/api/seed` never calls it**. It imports `createTask`
straight from `@/lib/store`:

```
$ grep -n "resolvePostingPrivilege\|createTask" src/app/api/seed/route.ts
2:import { createTask } from "@/lib/store";
69:      const task = await createTask({
```

Two write paths, one fix. The seeder still mints `agent:null` tasks and still does it silently.

Executing the real resolver confirms both the miss and that the rename is irrelevant to it:

```
$ npx tsx rp-probe.ts
poster="agent:relay"      -> {"agentId":null,"unknownAgentId":"relay","isAdmin":true,"legacyExemptionUsed":true}
poster="agent:favour"     -> {"agentId":null,"unknownAgentId":"favour","isAdmin":true,"legacyExemptionUsed":true}
poster="agent:shelfwatch" -> {"agentId":"shelfwatch","unknownAgentId":null,"isAdmin":true,"legacyExemptionUsed":true}
```

**Failure scenario:** Oscar seeds the board. Every task defaults to an agent id that has never
existed. `getAgent` returns null silently. The task persists with `agent: null`. The public board
shows no agent attribution, agent analytics see nothing, and the 8-agent layer that is the product's
whole premise renders as anonymous tasks. No error anywhere.
**Blast radius:** 41/41 agent-posted tasks live in production. The entire agent surface. Silent.
**Write path is gated** by `ADMIN_SECRET` (`seed/route.ts:17,23`), so only Oscar can produce these,
but the read side is the public board.

### 2. `verify-proof.ts` silently degrades AI verification on real-USDC tasks (LIVE, SILENT)

- `src/lib/verify-proof.ts:105` and `:364` run `const agent = AGENT_REGISTRY[agentId.toLowerCase()];`
  then `if (agent?.verificationPrompt)`

Optional chaining swallows the miss. When the agent does not resolve, `agentSection` stays `""` and
`systemPrompt` is the generic `SYSTEM_PROMPT`. Each agent's `verificationPrompt` carries its
specific anti-fabrication criteria (ShelfWatch: *"Verify that the human tested the specific thing the
AI could not... Flag responses that could be fabricated without actual testing."*). None of it applies.

**Failure scenario:** a human submits proof on one of the 41 tasks. `agentId` is `"relay"` (or is
null on the stored row). The registry lookup misses. The verification LLM runs with the generic
prompt and never receives the agent-specific fabrication checks. A weaker verdict accepts a proof it
should have flagged, and escrow pays real USDC on it. Nothing logs that the criteria were dropped.
**Blast radius:** every task whose agentId does not resolve, on the verification path that gates
payout. Money-adjacent, silent, and the degradation is invisible in the output. The verdict looks
normal.

*Honesty:* I did not execute this path against a live submission (it needs an API key and a real
proof, and would be a write). The code path and the silent-drop are read-confirmed; the payout
consequence is reasoned, not observed. Ranked #2 on severity-if-true, not on evidence strength.

### 3. `ai-chat.ts` drops agent personality (LIVE, SILENT, COSMETIC)

`src/lib/ai-chat.ts:74,105` use the same `agent?.personality` shape. Briefings lose the agent voice.
Product-quality only, no money, no data loss.

### 4. `agent/[id]` is CORRECT, no action

`src/app/agent/[id]/page.tsx:43` -> `if (!agent) notFound()` (loud 404).
`layout.tsx:5` -> `agent ? ... : "Agent Not Found"`. Both handle the miss explicitly. This is what
the other call sites should look like.

---

## Dead names that are load-bearing AND CORRECT (fixing these causes the outage)

The sweep's most useful negative result. These are live, executable, dead-named, and must not be touched:

| Surface | Proof | Why it must stay |
|---|---|---|
| `mcp-server/package.json` name `relay-favours-mcp` | `curl registry.npmjs.org/relay-favours-mcp` -> **HTTP 200** | Genuinely published. Renaming breaks every installed agent. |
| `api/agent/route.ts:172` `npx -y relay-favours-mcp` | matches the published name above | Correct install instruction. |
| `world-relay.vercel.app` | `/api/health` -> **HTTP 200** `{"status":"ok","service":"relay"}` | The live deployment. `world-favour.vercel.app` -> **HTTP 404 DEPLOYMENT_NOT_FOUND**. |
| launchd `com.favour.*` -> `$HOME/CODE/world-relay/...` | `launchctl list` -> exit 0 for ops/watch/nightshift | Label renamed, path still `world-relay`, path exists. Correct. |

A rename-driven sweep that "cleaned" these would take the product down. This is the argument for
leads-not-verdicts.

---

## Separate live bug found in passing (NOT a rename issue)

`api/agent/route.ts` advertises a Python SDK that does not exist on PyPI:

```
$ curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/relay-favours/json
404
```

The route serves `install: "pip install relay-favours"` to every agent that reads the onboarding
endpoint. It fails loudly, for anyone following the documented Python path. `favour-favours` is also
404, so this is a publish gap, not a naming gap. Flagging because it is a live consequence on a live
surface; it is out of this sweep's thesis.

---

## False-positive accounting

R4 reported **20 IN CODE** for relay->favour, **0** for glaze->helicon. Honest classification:

| Verdict | Count | Detail |
|---|---|---|
| **Load-bearing and broken** | **4** | `seed/route.ts:11,12,13,68` |
| Load-bearing and correct (do not fix) | 3 | `agent/route.ts:172`, `mcp-server/package.json:22`, `health/route.ts:6` |
| Self-consistent sentinel (writer+reader agree) | 3 | `relay-bot` in `dispute:37`, `followup:36`, `useWorldUser.ts:66` |
| Self-consistent vocabulary | 3 | `helicon/claude_code.py:232,233`, `helicon/eval.py:58` |
| Display-only / dead config | 3 | `people-radar/config.json:20,100,110` |
| Metadata keywords | 2 | `pyproject.toml:15`, `mcp-server/package.json` |
| Archived project copy | 1 | `bagelHQ/.../layout.tsx:17` |
| **R4 flagging its own docstring** | **1** | `helicon/aliases.py:70` |

**Precision on "load-bearing and broken": 4/20 = 20%.** Better than 358 prose mentions, not good.

Two of those buckets deserve their own note:

- **`helicon/aliases.py:70` is R4 flagging its own explanatory docstring.** `_COMMENT_RX` skips lines
  that *open* a comment; line 70 *closes* a docstring, whose final characters are `sentence."""`, so it survives the filter. The function's comment says a dead name in a comment
  "executes nothing" and then reports itself. Cosmetic, but it is the check failing its own rule.
- **`people-radar/config.json:20` is doubly inert.** `priority_tags` is read by nothing:
  ```
  $ grep -rn "priority_tags" ~/CODE/people-radar --exclude-dir=.git
  config.json:16:  "priority_tags": [
  ```
  Dead config, not a dead name. The contact tags at `:100,:110` are only `", ".join(tags)` for
  display (`radar.py:1088`), never compared to a literal.

**What R4 missed entirely:** `store.ts:104` and `verify-proof.ts:105,364`, the actual mechanism.
Neither line contains "relay" or "favour". R4 cannot see them by construction. Recall on the class
that matters is the number I cannot compute, and that is the honest finding about R4.

---

## Surfaces swept clean (negative results)

- **env var names:** no `RELAY_*`/`GLAZE_*` mismatch. `mcp-server` reads `RELAY_API_KEY`/`RELAY_BASE_URL`
  in both `src/` and `dist/`, and nothing anywhere sets `FAVOUR_*`. Consistent dead name = cosmetic.
  (The `FAVOUR_*` hits in `proof-of-favour.ts` are economy constants, unrelated.)
- **`.env` files (untracked, R4-blind):** 20 found, none define a dead-named var.
- **API route paths on disk:** `find -type d -name relay -o -name glaze` -> none.
- **launchd/cron:** 22 plists + 3 crontab lines. Labels already `com.favour.*`; every path resolves; all exit 0.
- **live MCP registrations:** no relay/favour MCP server registered in `~/.claude.json`.
- **glaze->helicon:** 0 code leads, 1 legacy test. Clean. The only `GLAZE_*` hits are vault prose in
  `vault-mirror` describing the old `GLAZE_PASSWORD`, which is history, not a claim.

---

## Boundary finding: R4 walks `~/CODE/recall`

`aliases.code_refs()` iterates every dir in `~/CODE` containing `.git` and greps tracked code files.
`~/CODE/recall/.git` exists, so **R4 reads Oscar's 2013-2025 journal repo on every `helicon rot` run.**

It only opens `_CODE_EXT` files and only emits `file:line` + a 120-char snippet, so journal prose in
`.md` is not in scope today. But nothing in the code enforces that boundary. It is incidental to the
extension filter, and one added extension or one `.json` corpus file turns a rot check into a journal
reader that prints snippets into audit findings.

I excluded `recall` from every sweep in this document by hand. I did not read it, grep it, or list its
files. **Recommend an explicit deny-list in `code_refs`, not a filter that happens to hold.**

---

## Recommended fixes (not applied)

1. **`store.ts:104`**: make the miss loud. `getAgent` returning null on a non-null `agentId` is a
   caller bug; log or throw. This is the fix that generalizes, and it is one line.
2. **`seed/route.ts:68`**: delete the `"relay"` default. There is no correct house-agent string;
   `getAgent("favour")` is null too. Default to `null`, or validate against `AGENT_REGISTRY` at the
   boundary and reject unknown ids.
3. **`seed/route.ts:11,12,13`**: assign a real registry key or `null`.
4. **`/api/seed`**: route it through `resolvePostingPrivilege` so both write paths share the audit.
5. **`verify-proof.ts:105,364`**: `agent?.verificationPrompt` on the payout path should log when it
   drops criteria. Silent degradation of a money gate is the worst shape in this file.
6. **R4**: the check should follow the *lookup*, not the *name*: flag string literals that reach a
   registry index with no error path, dead-named or not. That check finds `store.ts:104` on day one,
   and it finds the next one under a live name.
7. **`code_refs`**: explicit `recall` deny-list.

---

## Failure inventory: what I did NOT verify, and what is most likely wrong

**Most likely wrong:** finding #2 (`verify-proof.ts`). I read the code path and confirmed the silent
drop, but I never executed it against a real submission and never observed a verdict change. The claim
"weaker verification -> bad proof accepted -> USDC paid" is a reasoned chain, not an observed one. It
is plausible the generic `SYSTEM_PROMPT` is strict enough that the agent section changes nothing
measurable. Ranked on severity-if-true. Treat as a lead.

Also not verified:

- **Whether the 41 tasks' stored `agentId` column is `"relay"` or null.** I read the public API,
  which exposes the resolved `agent` object, not the raw column. The repair shape depends on which,
  and I did not touch the DB.
- **Whether `/api/seed` has run since the `/api/tasks` fix deployed.** I proved the seeder still
  *contains* the bug and that production still *shows* it. I did not prove a seed ran post-fix. It is
  possible the seeder is dormant and the 41 rows are all pre-fix, which lowers #1's urgency without
  touching its correctness.
- **`relay-bot` liveness.** Writer and reader agree across 10 sites, so it is self-consistent. But
  `useWorldUser.ts:66` renders the literal dead brand `"RELAY"` to users, and the production payload
  contains 0 occurrences of `relay-bot` and no `messages` array, so I could not confirm whether that
  label ever reaches a screen. Unverified, low stakes.
- **`health/route.ts:6` `service:"relay"`.** I called it cosmetic. If any external monitor matches on
  that string, it is load-bearing and correct. I did not enumerate monitors.
- **Recall on the real class.** I swept for silent-null registry lookups and the grep leaked into
  minified `dist/` bundles; I filtered by hand and read the world-relay hits. I did not exhaustively
  sweep all 27 repos for the *lookup* pattern, only for the *name*. There are almost certainly more
  `X[key] || null` sites I never saw. **"Find the next agent:relay" is answered for world-relay and
  unanswered for the other 26 repos.**
- **`bagelHQ/projects/world-build-relay/`**: assumed to be an archived copy from its path. Not confirmed deployed or not.
- **The 12 pre-rename tasks** are my strongest evidence and rest on the API's `createdAt` being
  creation time, not a mutable updated-at. I did not verify that field's semantics against the writer.
