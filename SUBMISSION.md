# Mount Helicon: Qwen Cloud Global AI Hackathon (Track: MemoryAgent)

**Deadline:** Jul 20, 2026, 2:00 PM PDT (verified at the Devpost source Jul 16; the "Jul 8" on early posts was the original date, extended). **Prize:** $7K cash + $3K Alibaba Cloud credits per track.

**Position: a Qwen-powered governance layer for agent memory** — a memory control
plane, not another memory store. A local-first command center (dashboard + CLI + MCP)
where the machine handles routine rot, the human rules only genuine contradictions,
and every ruling becomes an enforceable rule with a receipt and a reversible undo.
The reproducible judge demo (`helicon demo`, seeded, keyless, no personal data) and
the sub-3-minute walkthrough are in **[`docs/archive/GOLDEN_SUBMISSION.md`](docs/archive/GOLDEN_SUBMISSION.md)**;
the honest inventory is in **[`docs/archive/HELICON_OS_FEATURE_MAP.md`](docs/archive/HELICON_OS_FEATURE_MAP.md)**.

> **Real now vs. roadmap (strict).** *Real:* the governed-memory loop — audit →
> human ruling → verified apply (receipt) → enforced guard → undo, tested at the
> HTTP boundary; live Qwen contradiction/grounding judging with an honest DEGRADED
> verdict; a localhost-safe, no-personal-data demo; and a **tested, read-only
> TaskRun/ContextPacket provenance recorder** (objective, frozen candidate context,
> artifact, attested outcome) that **does not yet drive retrieval, routing, or
> learning**. *Roadmap (not claimed working):* feeding that recorder into a *causal*
> context/routing decision, a read-only MCP retrieve path, and evidence-backed
> context recommendations. Helicon is the **govern** half — shipped and tested — and
> does not pretend to be a complete "memory OS."

The sections below are the *evidence* — run against the author's own real store —
that the govern half works on real memory, not a fixture.

Mount Helicon is the **exam a memory store never runs on itself**: it audits a live memory for rot, checks what agents *claimed* against reality, lets a human rule a contradiction once, compiles that ruling into law the agent obeys before it writes, and **re-alarms the instant the ruled-wrong value returns**. Memory stores keep the write path. Helicon is the verification layer on top of it.

And verification is not the point, it is the precondition. **Memory you have not verified is memory you cannot safely move.** Rot is why context does not port between harnesses, so the same exam that catches the rot is what lets memory cross from Claude Code to Cursor without carrying it along, and what turns "which model should I trust" into a query instead of a vibe.

Everything below runs on the author's real store: **~7,800 memories, ~4,200 live as of 2026-07-17**, from real Claude Code transcripts, a real Obsidian vault, and real git history. That count is stamped rather than stated because it is a fast fact: it grew by 270 during the writing of this document, and `helicon doctor` prints today's. (A count with a shelf life is exactly the class `helicon move` holds back at the border, below. The rule applies to this file too.) Every number here was re-run the day it was written. The one synthetic fixture in the repo is labelled as such, in the section that uses it.

---

## Hero 1: Qwen finds the one real fork in my own memory, and kills three lookalikes

Not a fixture. This is the author's live store, scanned from real Claude Code transcripts, a real Obsidian vault, and real git history.

R11 asks a question a memory store never asks: *do two sources disagree about what a thing IS?* On the real store it finds four candidates. Only one is real, and **this is where Qwen becomes load-bearing rather than decorative.**

The gate used to be embedding cosine. Measured live on 2026-07-17:

| Entity | Definition A | Definition B | cosine | cosine says | **Qwen says** | truth |
|---|---|---|---|---|---|---|
| `yieldbound` | a treasury where agents spend yield | a wallet tracker | 0.354 | fork | **fork** | real |
| `qwen` | the verification brain | a measurably good memory judge | 0.367 | fork | **clean** | artifact |
| `litmus` | a layer | the verification layer | 0.390 | fork | **clean** | artifact |

The threshold is 0.45, so cosine keeps all of them. **The real fork sits 0.013 away from an artifact.** No threshold recovers that, and it isn't mis-tuning: cosine measures semantic *distance*, and "verification brain" vs "memory judge" are distant but perfectly compatible. Contradiction is a logical relation, not a distance. `qwen3.6-flash` reads all three correctly, including *why* litmus is fake: **"Item B is a more specific instance of Item A."**

```bash
$ helicon audit                 # cosine gate, free, deterministic
  R11  Identity coherence   ROT FOUND
       4 entity definition(s) forked: machine (tool/loop), yieldbound (treasury/tracker),
       litmus (layer/verificatio) [cosine-only, unjudged]

$ helicon audit --judge         # the Qwen judge decides
  R11  Identity coherence   ROT FOUND
       2 entity definition(s) forked: machine (tool/loop), yieldbound (treasury/tracker)
       (+2 genus candidate(s) dropped by the qwen-judged gate)
```

Then the loop the store cannot run. The fork is real, and the two sides come from two different tools:

```
$ helicon resolve 355

#355  [warning]  filed 2026-07-14T00:47
Identity fork: 'yieldbound' is defined as treasury (2 sources) vs tracker (1 source)

A: treasury   claude-code:session_30d76be2
   | Yieldbound, a treasury where agents spend yield and never touch
B: tracker    obsidian:02 Content/hackathon-continuation-arc.md
   | Yieldbound is a wallet tracker

Decide:  helicon resolve 355 --truth "<the canonical definition>"
   or:   helicon resolve 355 --dismiss "why"
```

A Claude Code session and an Obsidian doc disagree about what my own project *is*, and neither tool can see the other. **You rule it once.** The ruling compiles into `GOLDEN_RULES.md`, the file the agent reads before it writes, and from then on `helicon guard` blocks the losing definition at write time (Hero 2), forever, no matter how recently it is re-asserted.

That last step is the thesis in one screen: **a memory store can represent SUPERSEDED (recency wins); it cannot represent FALSE-and-stays-false.** Helicon can, because a human said so and the ruling is not a memory that can decay.

The judge is greedy (`temperature=0`). A verdict that changes between two identical calls is not a verdict, and this exam has been burned by a non-deterministic remote call once already (see below). `audit --judge` reproduces across runs; `audit` alone stays deterministic, free, and honest about which gate produced its number.

## Hero 2: the ruling BINDS at write time (guard)

A ruling that only lives in a file is advisory. Helicon enforces it. A human already ruled `hackathon wins = 9` (finding #281); the value `4` was ruled wrong and set to re-alarm. So:

Verbatim terminal output, run live against the real store at commit `7b3256d`:

```
$ helicon guard "4 hackathon wins"

  BLOCKED — 1 ruling(s) contradict this output:

    [critical] wins for 'hackathon' was ruled '9', but this asserts '4' — ruled wrong (re-alarms if it returns).
        ↳ ruling #281 on 'hackathon' wins at 2026-07-06T08:58:48


$ helicon guard "9 hackathon wins"

  ✓ clean — no ruling contradicts this output.


$ helicon guard "RELAY is live with real money"

  WARN — 1 ruling(s) contradict this output:

    [warning] 'RELAY' is a dead name (renamed to 'FAVOUR' 2026-07-02); use 'FAVOUR'.
        ↳ rebrand executed Jul 2 (decision log)
```

Three deterministic classes, each tracing to a real ruling with provenance: **ruled facts** (a value a human ruled wrong for a topic), **dead names** (renames), and ruled identity (a definition ruled against). Note the severity split: a ruled-wrong fact **blocks**, a dead name **warns**. The guard reads `audit_log`, the adjudication record, not the memory store, so a ruling cannot be eroded by decay or outvoted by newer memory.

The guard is exposed as the `helicon_guard` MCP tool, so any Qwen/Claude agent can consult the law **before** it writes a claim, not get audited after. This is the honesty thesis made true: adjudication that actually binds.

---

## The thesis (one line)

**Memory has no intrinsic quality. It is only as good as the context it surfaces and the output it drives.** The only honest way to evaluate a memory is downstream: does the context it retrieves still pass, and does the output it produces hold up against reality? Staleness and contradiction are early proxies for "this will cause a bad output." A memory whose output is never evaluated is an untested assumption.

Mount Helicon closes that loop: it evaluates memory by its output, attributes a bad output back to the memory that caused it, lets a human rule once, and compiles that ruling into law the agent obeys next time.

## The loop (the architecture)

```
 STORE ─▶ RETRIEVE ─▶ OUTPUT ─▶ ATTRIBUTE ─▶ RULE ─▶ LAW ─┐
 (is it   (is the     (does it   (which       (human   (agent   │
  true?)   context     hold vs    memory       settles  obeys    │
           right?)     reality?)  caused it?)  it)      it)      │
   ▲                                                             │
   └──────────────────  better STORE  ◀─────────────────────────┘
```

| Stage | Question | Helicon command | Status |
|---|---|---|---|
| **Store** | Is memory internally true? | `helicon audit` (12-class rot exam) | solid |
| **Retrieve** | Is the retrieved context right? | `helicon battery` / `helicon snapshot` | solid |
| **Output** | Does the agent's claim hold vs reality? | `helicon review --terminals [--run]` | shipped |
| **Attribute** | Which memory caused the bad output? | `helicon attribute <finding>` | shipped (v1 ranking is deterministic FTS) |
| **Rule** | Human settles it, once | `helicon resolve <id>` | solid |
| **Law** | The agent obeys it next session | `helicon policy --inject` → `GOLDEN_RULES.md`, enforced at write time by `helicon guard` | wired |

Same evaluators point at the other producers of agent behavior: **skills** (`connectors/skills.py`), **routines/crons** (`stackwatch.py`), and the **regret** signal (`regret.py`), which tracks killed memory the output later needed back.

### The OUTPUT stage, which is where the thesis actually earns its keep

Every memory tool grades memory against itself. This one grades it against reality. `review --terminals` reads what agents on this board *claimed* and checks each claim against the world, live:

```
$ helicon review --terminals

  AGENT-OUTPUT REVIEW - 5 claim(s) need you (verified claims hidden)

  ┌─ x-engine  (x-engine · night-run-2026-07-13)
  │ ✗ [contradicted]  The brief's framing is right: post #7 shipped human-written over 6 AI drafts
  │     ↳ claims shipped, but branch 'night-run-2026-07-13' has NO upstream - 15 commit(s) never left this machine
  ┌─ Helicon  (helicon · extra-mile/helicon-2026-07-16)
  │ ? [unverified]  **310 → 344 tests. Every fix mutation-tested.**
  │     ↳ test files present, claimed count NOT re-run - add --run
```

An agent said **shipped**. Git says fifteen commits never left the laptop. That is `published != true` caught on a live claim, on a real board, by a check that cost nothing and asked no model's opinion.

Note the second line too, because it is the harder discipline: a claim it *cannot* check is marked `unverified`, never `pass`. `unverified` is excluded from the pass/fail denominator entirely rather than scored as a win. `--run` actually re-runs the test suite the agent bragged about. **A tool that graded its own homework would have called both of those green.**

## Why the exam is not the product: verified memory is portable memory

On Jul 9, 2026, Sriram Krishnan (a16z) asked for a desktop agent super app: **(1)** switch and multiplex harnesses and models, **(2)** make it easy to move memory and context, **(3)** orchestrate between models, **(4)** retroactively look at usage and optimize for cost and results.

(1) is the commodity, and several tools do it. **(2) is where it collapses**, because each platform stores context in a shape that only maps to its own retrieval logic. But that is only half the reason. The other half is that **you cannot safely move memory you have not verified**, and nobody verifies it. Rot is why memory does not port. That reframes everything above: the exam is not the product, the exam is what makes the move safe. It is the customs check at the border.

```
$ helicon move --from ~/.claude/CLAUDE.md --to cursor

  CONTEXT MOVE — /Users/morkeeth/.claude/CLAUDE.md -> cursor format

  44 item(s): 43 verified -> move, 1 held back

  HELD BACK (not moved, memory does not travel with rot):
    - *Live layer* (00 Dashboard: dashboard, review-queue, opportunities, to   [volatile ('this week')]
```

Point it at your own `CLAUDE.md`, `AGENTS.md`, or `.cursorrules`; it reads what you already have. Run it against **this repo's own** `CLAUDE.md` and it holds back Helicon's own stale stats (`~3,800 live memories of ~6,900 total`, `Composite: ~67 (as of 2026-07-13)`) because a fact with a timestamp in it is a fact with a shelf life. The tool refuses to carry its own drift across the border. `--verify-contradictions` adds the Qwen judge (the same one from Hero 1) so an item that contradicts an already-moved item is held too.

**(3) and (4) are reads of the eval store — deliberately NOT a prescriptive router.** Once agent output is verified against reality, "which model should I trust" becomes a ranked query over outcomes you already have. But today's evidence is thin and confounded (claim-level not task-level; model attributed from git trailers; no task-class control), so Helicon **withholds a route below a quality floor** rather than dressing a coin-flip as a recommendation. Prescriptive routing is the next loop (see the TaskRun/ContextPacket design); it is not claimed as working here:

```
$ helicon route
  ▸ testing:      no model clears the quality floor yet — best Opus 4.8, verified 5/6,
                  Wilson LB 0.436 (< 0.50). No route emitted.
  ▸ api-surface:  insufficient evidence (n=2, need >=5) — no route

$ helicon runs                      # score = verified yield / cost - damage
  when              sess     out      dur   verified   score
  2026-07-16 07:25     4    1.4M   948.8m       9/13    0.42
  2026-07-15 07:06     7    5.9M  1448.8m       8/11    0.06
```

**The honest state of (3) and (4), because the numbers are thin and a judge will find that anyway:** `route` says "only model with evidence" for every task class, because this operator runs one harness, so it can rank but has nothing to route *between* yet. `leaderboard` reads 1,088 attributed commits across 29 repos and 8 models, but finds **0 reverts**, so its survival bound currently ranks sample size rather than quality. Both are real, wired to real evidence, and early. Neither is a demo.

What makes any of it possible is the same thing throughout: **an output verified against reality is the only ground truth in the building.** Everything else here is a read of it.

## Qwen + Alibaba Cloud (backend dependency, not decoration)

~22 modules call Qwen: contradiction and identity judging, consolidation synthesis, portrait narration, next-move generation, volatility scoring. Embeddings run on Alibaba **DashScope** (`text-embedding-v4`); inference on Alibaba **Model Studio / MaaS** (`token-plan.ap-southeast-1.maas.aliyuncs.com`). Kill the key and half the intelligence layer goes dark — that is the live Alibaba dependency, and it runs on every command. The dashboard/API is **deployed and running on Alibaba Cloud ECS (Singapore / ap-southeast-1): http://47.237.3.97:8420** (verified live — `GET /api/health` returns `{"status":"ok",...}`; serves the seeded demo, no personal data), and is also container-ready for Function Compute (`fc/s.yaml` + `Dockerfile`).

**Code files demonstrating use of Alibaba Cloud services and APIs** (the rule asks for a link to a code file, so here are the three that matter):

| File | Alibaba Cloud service | What it does |
|---|---|---|
| [`helicon/qwen.py`](https://github.com/MorkeethHQ/mount-helicon/blob/main/helicon/qwen.py#L28-L36) | **Model Studio / MaaS** (`dashscope-intl.aliyuncs.com`, `token-plan.ap-southeast-1.maas.aliyuncs.com`) | Builds the Qwen client and drives every LLM call (`qwen3.6-flash` / `qwen3.6-plus` / `qwen3.7-max`) via the OpenAI-compatible SDK, with tier routing and a token-cost log |
| [`helicon/embeddings.py`](https://github.com/MorkeethHQ/mount-helicon/blob/main/helicon/embeddings.py#L81-L118) | **DashScope** (`text-embedding-v4`, 1024-dim) | `_embed_provider()` / `embed_batch()`: the whole retrieval stack is Qwen-native. 4,214 memories embedded on DashScope, hybrid-searched against FTS5 |
| [`scripts/cloudshell-run.sh`](https://github.com/MorkeethHQ/mount-helicon/blob/main/scripts/cloudshell-run.sh) + `fc/s.yaml` | **ECS** (live) + Function Compute (config) | The backend that is **deployed and running on Alibaba Cloud ECS** at **http://47.237.3.97:8420** (Singapore); same boot script, container-ready for FC |

Verify the dependency in one line, no reading required:

```bash
$ python3 -c "import json; c=json.load(open('config.json')); print(c['qwen_base_url']); print(c['embeddings']['base_url'], c['embeddings']['model'])"
https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
https://dashscope-intl.aliyuncs.com/compatible-mode/v1 text-embedding-v4
```

## What `helicon report` says about itself right now: DEGRADED (live)

Run it with `--llm`, which is the **full** exam (all six context tests, not just the four deterministic ones). It prints **DEGRADED**, and that is the most honest thirty seconds of the submission:

```
$ helicon report --llm

Overall: DEGRADED   (battery: 2 healthy / 10 degraded / 1 broken of 13 tasks; scan freshness printed live)

1. Efficient storage & retrieval          HEALTHY
   P@3 0.615  MRR 0.596  (n=13, small internal benchmark, one label per query)
   ingest dedup rate 1.0, 17 consolidations
2. Timely forgetting                      HEALTHY
   decay predicts human kills: rank-AUC 0.781; freshness pass rate 0.923
3. Recall under limited context windows   HEALTHY
   thinness pass 1.0, redundancy pass 0.923, ~1016 tokens/query (top-5)
4. Cross-session accuracy                 DEGRADED
   snapshots: 2 regressed of 13; contradiction pass 0.846, grounding pass 0.385
   cross-source pairing: 8 live conflict(s), 3 open finding(s)
```

**Read the battery split honestly: 2 healthy, not 7.** Plain `helicon report` prints `7 healthy / 5 degraded / 1 broken`, because without `--llm` the Contradiction and Grounding tests never run and 7 tasks are counted healthy on a partial exam. Worse, it printed `(LLM tests off: no key)` on a machine with a working key, blaming the environment for a missing flag. Both were fixed while preparing this submission: the headline now says `deterministic-only` when it is, and the message names the flag instead of guessing at the cause. The flattering number was one command away from being the number in this document, which is precisely the failure mode the tool exists to catch.

**What holds the verdict at DEGRADED**, all of it real and none of it papered over: **grounding pass 0.385** (the Qwen judge finds fewer than half the retrieved contexts specific and verifiable), plus any live cross-source conflicts and retrieval regressions the run surfaces (counts printed live, not memorized). A system that reports its own degradation is the product; one that hides it behind a green light is just another benchmark.

### The broken task, diagnosed rather than hidden

One of the 13 benchmark tasks (`Content Strategy`) fails the **critical Freshness** test (the exact count varies per run; the failure mode does not), and the diagnosis is worth more than a green number would be:

```
[BROKEN] Content Strategy
   FAIL Freshness (critical)  1 retrieved memories killed/decayed: ['Edited: dashboard.md']
   FAIL Expiry               2 decayed below 0.15: ['Edited: dashboard.md (conf 0.00, 49d)',
                                                    'Content Strategy - May 2026 (conf 0.04, 19d)']
```

`Edited: dashboard.md` is not a memory. It is a **raw diff hunk** scraped from a Claude Code transcript (`File: <path>` plus a truncated `-`/`+` fragment). It decayed to confidence 0.0014 and **still ranks into the top 5**. Three findings sit underneath that, all verified live:

1. **Forgetting does not reach retrieval.** `hybrid_search` fuses semantic rank and FTS rank via Reciprocal Rank Fusion. Confidence is carried into the result and **never scored**. Helicon computes a decay signal it validates at rank-AUC 0.781, then ignores it when choosing what to serve. Dead memory outranks live memory because nothing tells retrieval it is dead.
2. **Approved memory is immortal.** `apply_decay` runs on `review_status IN ('pending','revised')`. It never touches `approved`, so the servable set and the decaying set are not the same set. Reviewing a cube already sets `last_reinforced = now` and bumps `review_count`, which extends the half-life (`eta * (1 + 0.5 * review_count)`). The model already honors a human's blessing by extending stability, so exempting `approved` from decay grants a second, unintended immortality on top of it. The pathology it produces: `Content Strategy - May 2026` was approved *while already decayed to 0.0*, so it is pinned at dead-zero forever and can never be reinforced back. The human's approval was silently discarded.
3. **The corpus is mostly exhaust.** 5,408 of 7,529 cubes (**72%**) are `Edited:`/`Created:` file-edit records; 2,933 are still servable. The single retrieval regression is the same story: task `Search` dropped `Created: search.py` and gained `Edited: data.py`, which is exhaust displacing exhaust.

**Why this is not fixed in this submission, stated plainly:** every route to 0 broken is a core change (decay scope, retrieval ranking, or ingest policy) with system-wide blast radius, and the honest thing three days from a deadline is to name it, not to ship it untested. One route was prototyped and rejected on evidence: widening `apply_decay` to include `approved` would decay the **rulings** (`Resolved: Hackathon wins = 9` from 1.0 to 0.64), which are settled facts that time should not erode. The guard survives that (it reads `audit_log`, not `helicon_cubes`), but the retrieval surface for settled facts would not. The correct fix is type-aware: rulings are overturned by a newer ruling, never by forgetting. That is the next commit, not this one.

This is the thesis pointed at its own author. The exam returns **red on the store of the person who wrote it**, and the red is specific enough to fix.

The retrieval-regression number has a history worth telling: on 2026-07-15 it read **12 of 13 regressed**, and it was wrong. `regressed` meant "anything changed at all", so it counted the loop *working* as a failure (16 of 17 missing baseline memories were missing because Helicon had correctly killed them as rot, and a better memory took each vacated slot). A regression is now only what it should always have been: a memory still live and no longer retrieved. 12 → 1. The same day the exam also could not reproduce its own verdict (11/12/11 across three runs) because retrieval called a non-deterministic remote reranker; fixed with stable tie-breaks and a memoized rerank (reproducible answer, honestly not a deterministic model).

An earlier draft of this section claimed that number had reached **0 of 13** and that "the 0 is real." It is not, and the correction belongs in the document rather than in a git history nobody reads. It currently reads **1**, and `data/watch.log` shows it flipping across the last three scheduled scans:

```
R8 Retrieval regression: ROT FOUND -> CLEAN
R8 Retrieval regression: CLEAN -> ROT FOUND
R8 Retrieval regression: ROT FOUND -> CLEAN
```

The single regression is task `Search` dropping `Created: search.py` and gaining `Edited: data.py`. All three are file-edit exhaust, so what the metric is measuring at the 0↔1 boundary is exhaust displacing exhaust, which is churn rather than signal. A one-of-thirteen metric that flaps between two adjacent values is not a number to quote proudly; it is a threshold sitting exactly where the corpus is noisiest. Named here rather than discovered by a judge.

The remaining 8 conflicts are the claim selector, and some are the same both-poles shape `GOLDEN_RULES` already carries dismissals for. Named here rather than discovered by a judge.

## Differentiation: why this is not another memory agent

The field the judges will see most of: **Mem0, Zep/Graphiti, Cognee.** They are memory *stores* with automatic contradiction handling. That automatic resolution is exactly the gap.

- **Mem0** stores/retrieves; add/update/delete is an LLM decision at write. Contradiction = the LLM chooses to replace. No human authority, no binding, no re-alarm.
- **Zep / Graphiti** ship a bi-temporal knowledge graph; a contradicted edge gets a `t_invalid` and recency wins. That represents **SUPERSEDED**, never **FALSE**. The same wrong value can win again the next time it's asserted more recently.
- **Cognee** reweights by popularity; **Anthropic's memory tool** is LRU; **OpenAI** ships "treat memories as guidance only." None can say *"a human decided this, and it stays decided."*

Helicon's wedge is three things none of them have:

1. **Human ruling is the authority, not an LLM guess.** Ground truth = the operator's verdict, stored with provenance. The way individuals have historically broken open this space is "construct independent ground truth, then catch a model lying". Here the operator *is* the oracle, and the ruling is the held-out key.
2. **The ruling BINDS.** It compiles into `GOLDEN_RULES` the agent reads before it writes, and `helicon guard` blocks a ruled-wrong value at write time (Hero 2). Enforced, not advisory.
3. **Never-twice / re-alarm.** A ruled-wrong value re-alarms the instant it returns in newer memory, at audit time *and* write time. Recency cannot overturn a ruling. Mem0/Zep would silently accept the re-assertion (Hero 1, phase 4).

And the framing that disarms "yet another store": Helicon runs **on** Mem0 (read-only), Alibaba's own recommended Qwen memory backend. Alibaba's Model Studio docs recommend Mem0 (with AnalyticDB) for Qwen agents; Mem0 stores and retrieves, and its docs never mention contradiction, decay, or a fork in what an entity *is*. Helicon is not a competitor to the store the judges' stack recommends. It is the exam that store never runs on itself.

```bash
MEM0_API_KEY=m0-... python3 scripts/demo_mem0_audit.py   # audits YOUR real Mem0 store, read-only
python3 scripts/demo_mem0_audit.py --mock                # synthetic fixture, no account needed
```

**On `--mock`, stated plainly rather than left for a judge to notice:** the bundled store is *invented* (an "Aurora" defined two ways). It exists so the mechanism is legible in thirty seconds without a Mem0 account, and for no other reason. It is a fixture, not a result, and it is not the hero of this submission. Hero 1 is the same mechanism on a real store with real memories, which is the only version that proves anything. This repo's rule is zero fake data, and a synthetic fixture that is labelled is not a violation of it; a synthetic fixture presented as a finding would be.

One result that proves LLM-judged contradiction is not enough: in the model bake-off, **every model (Qwen, Claude, GPT) missed unit-drift** (points counted as dollars). A class of rot only a deterministic exam catches, never an LLM judge grading its own context.

## How the loop answers the judging criteria

- **Technical + engineering innovation (30%):** a closed evaluate→attribute→rule→law loop over memory, a deterministic 12-class exam, Qwen-judged contradiction, and a write-time guard that binds rulings. All read-only on the source store.
- **Creative AI implementation + architecture (30%):** the thesis is to evaluate memory by its output, not in isolation, with human rulings that compile into obeyed, write-time-enforced law. Nobody ships that.
- **Real-world relevance + market (25%):** runs on a real store of **~7,800 memories (~4,200 live) as of 2026-07-17** across ~15 live projects, scanned from Claude Code, git, Obsidian and agent skill files; the store grows on every scan, so `helicon doctor` prints today's count rather than this one. The field (Mem0's own 2026 report; Memora's "64% of errors = failure to forget") now agrees memory maintenance is the bottleneck, and the surviving gap is real in-the-wild data with a human-labeled key, which is exactly what this is.
- **Presentation + docs (15%):** this architecture, a sub-3-min demo, and hero demos that are one command each and run on real data (`helicon audit --judge`, `helicon resolve 355`, `helicon guard`, `helicon move`, `helicon review --terminals`).

---

## Demo video narration (draft — Oscar to flavor)

> **DRAFT, voice pass pending.** Spoken lines are a scaffold, not final phrasing; the
> first-person "my own system failing my own threshold" beats are yours to voice.
> **Before recording: `set -a && source .env && set +a && helicon report --llm` and
> read whatever verdict it prints.** The numbers below drift between runs (last full
> exam: DEGRADED, 2 healthy / 10 degraded / 1 broken, grounding 0.385, P@3 0.615), so
> speak the live number, never a memorized one. The verdict that matters is the word
> DEGRADED, and it has held every run. **Never say "0 broken."** ~3 min, hard cap 3:00.

**Cold open (0:00–0:20) — the system blocking its own drift, on camera.**
Terminal, live. Type `helicon guard "4 hackathon wins"`. It prints `BLOCKED — ruling #281`.
Line: *"This is my memory system refusing to let me state a number about myself that a
human already ruled wrong. Nine wins, not four. It re-alarms every time the wrong value
comes back. Let me show you why a store needs this."*

**What it is (0:20–0:40).** *"Mount Helicon is the exam a memory store never runs on
itself. It audits a live memory for rot, checks what an agent claimed against reality,
lets me rule a contradiction once, and compiles that ruling into law the agent obeys
before it writes. Everything you'll see runs on my real store: roughly 7,800 memories
from real Claude Code transcripts, a real Obsidian vault, real git history."*

**Hero 1 — the one real fork (0:40–1:20).** Run `helicon audit --judge`. *"Cosine
similarity flags four forked definitions in my own memory. Only one is real. The real
fork sits thirteen thousandths away from a false alarm, and no threshold recovers that,
because contradiction is a logical relation, not a distance. Qwen reads all three
correctly."* Run `helicon resolve 355`. *"A Claude Code session and an Obsidian doc
disagree about what my own project is. Neither tool can see the other. I rule it once."*

**Hero 2 — the ruling binds (1:20–1:45).** Back to the cold-open guard, now framed:
*"That ruling compiled into GOLDEN_RULES, the file the agent reads before it writes. A
store can say SUPERSEDED, recency wins. It cannot say FALSE and stays false. Helicon can,
because a human said so and a ruling is not a memory that decays."*

**Output stage — published is not true (1:45–2:20).** Run `helicon review --terminals`.
*"Every memory tool grades memory against itself. This one grades it against reality. An
agent on my board said 'shipped.' Git says fifteen commits never left the laptop. Caught
live, by a check that asked no model's opinion."*

**Honesty beat (2:20–2:45) — the red on my own store.** Run `helicon report --llm`.
*"Here's the part most demos hide. Pointed at my own store, my own exam returns
DEGRADED. [Read the live split.] Grounding is under-strength, there are open cross-source
conflicts, and file-edit exhaust still outranks live memory. A system that reports its
own degradation is the product. One that hides it behind a green light is just another
benchmark. The red is specific enough to fix, and I name every piece of it in the doc."*

**Close (2:45–3:00) — live on Alibaba Cloud.** Cut to the terminal: run one command
that fires a real Qwen judgment, then tail the token-cost log so the call to
`dashscope-intl.aliyuncs.com` lands on screen. *"Every judgment you just watched ran on
Qwen — Model Studio for inference, DashScope for embeddings. Kill the key and half of
this goes dark. That's the dependency. Verify it, then move your memory — because verified
memory is the only memory you can safely port."*

**Shot list:** (1) guard BLOCKED on a ruled-wrong claim — the hero, open AND close on it;
(2) `audit --judge` + `resolve`; (3) `review --terminals` contradiction line; (4)
`report --llm` DEGRADED verdict, live; (5) a live Qwen call landing on DashScope (tail the
token-cost log). Screen-record the terminal at a legible font size. The Alibaba proof is the live
ECS deployment at `http://47.237.3.97:8420` plus the running Qwen/DashScope API calls and the
linked code files (`qwen.py`, `embeddings.py`). The full timed 3-minute
script is in `docs/archive/DEMO-SCRIPT.md`.
