# Mountain of Helicon launch kit

## One line

**Executable preflight for agent context: check whether the instructions an
agent loads still match repository reality, with the command and stdout behind
every contradiction.**

## Launch post

We ran a frozen corpus of 591 public repos with agent-rules files.

577 current default branches were scoreable; all 14 exclusions are named. After
fixing 18 duplicate projections, dropping 5 rows contradicted by their own
stdout, and hand-verifying all 30 survivors, 6 of 577 repos were TRUE (1.04%);
9 of 30 mechanical rows survived (0.30 finding precision).

So we built Mountain of Helicon — executable preflight for agent context.

Every finding carries the `git` command and stdout that proved it. It warns
before work continues.

Open source: https://github.com/Morkeeth/mountain-of-helicon

## Short post

Agent instructions rot too. In a frozen 591-repo corpus, 577 were scoreable and
6 (1.04%) had a hand-verified path claim their own git tree disproved.

Mountain of Helicon checks before work starts, with executable receipts.

https://github.com/Morkeeth/mountain-of-helicon

## Five-post thread

1. Your coding agent loads `CLAUDE.md` / `AGENTS.md` before it reads the repo.
   What checks whether those instructions are still true?

2. We ran a frozen 591-repo corpus. 577 current default branches were scoreable;
   every one of the 14 exclusions is named.

3. After fixing 18 duplicate projections and 5 self-refuting rows, we
   hand-verified all 30 survivors: 6 of 577 repos were TRUE (1.04%), with 9 of
   30 mechanical rows surviving. Low, real, reproducible.

4. Mountain of Helicon runs the same executable checks as a Claude Code
   preflight. A warning includes the exact claim, command, and stdout. Blocking
   is opt-in.

5. The corpus, exclusions, receipts, and code are public. Run the isolated demo:
   `python3 -m pip install -e . && bash scripts/demo.sh`

## 45-second video script

**0–7s — the finding**

> “Agents trust their instruction files before reading the repo. We ran a frozen
> 591-repo corpus to see whether those instructions still matched reality.”

Show the report headline: 6 / 577 repos, 1.04%; 9 / 30 findings verified.

**7–18s — executable receipt**

Show one `CLAUDE.md` line naming a required path, then:

```text
$ git ls-files -- MASTER_GUIDE.md
(no output)
```

> “Not an LLM opinion. The repo's own git tree disproves the instruction.”

**18–32s — preflight**

Run the isolated doorway demo and show:

```text
⚠ HELICON — running anyway, but your loaded context is wrong.
```

Pause on claim, command, stdout, and fix.

> “Warning is the safe default. Teams can explicitly turn on blocking.”

**32–40s — honest scope**

> “Every mechanical survivor was read in context. Twenty-one of 30 were
> arguable or wrong, so we deleted them. Precision discipline is the product.”

**40–45s — call to action**

> “Mountain of Helicon. Executable preflight for agent context. Open source.”

Show repository URL and `bash scripts/demo.sh`.

## Video alt text

Terminal recording of Mountain of Helicon checking agent instruction files
against repository state. It shows a `CLAUDE.md` claim that tells an agent to
read `MASTER_GUIDE.md`, the command `git ls-files -- MASTER_GUIDE.md`, empty
stdout proving the file is absent, and a preflight warning that names the claim,
evidence, and remediation. No user files are modified.

## Screenshot caption

Mountain of Helicon's planted Rulings queue. A high-stakes Stripe contradiction
is waiting for a human decision; the demo uses labelled synthetic memories and
runs only on localhost.

## FAQ

**Is this another memory store?**  
No. It checks stores and instruction surfaces, records rulings, and exposes
guardrails through CLI/MCP.

**Does it block agents?**  
Not by default. The doorway warns and records evidence. Blocking is explicit
opt-in with `HELICON_GATE_MODE=block`.

**Does it require an LLM key?**  
No for executable and deterministic checks. Qwen is optional for judged
contradiction and grounding checks.

**What is the measured contradiction rate?**
Six of 577 scored repos had a sendable verified path contradiction: 1.04%.
Finding-level precision after the mechanical fixes was 9/30.

**Does the demo read my memory?**  
The terminal demo uses public repos and throwaway settings/store paths. The
visual demo uses 19 labelled planted memories under `~/.helicon/demo`.

**Is the hosted dashboard ready for personal stores?**  
No. The first launch is local-first. Public hosting waits for TLS, sessions,
CSRF protection, configured CORS, rate limiting, and backups.

## Moonshot portfolio

### 1. Agent Context Preflight Standard

**Hypothesis:** every agent harness should support a common preflight contract:
claims, executable probes, evidence, severity, and operator disposition.

**Build:** publish a versioned JSON receipt schema and adapters for Claude Code,
Cursor, GitHub Actions, and generic shell hooks.

**Proof:** the same fixture produces semantically identical receipts in three
independent harnesses; five external repositories run it without custom code.

**Kill criterion:** if hand-verified warning precision cannot exceed 0.70 on
open-world repositories, keep it an expert audit tool rather than a default
preflight.

### 2. Cross-Agent Correction Receipt

**Hypothesis:** a human correction made after agent A fails can measurably
prevent agent B from repeating the same claim.

**Build:** freeze the correction into a context packet, deliver it through MCP,
and verify receipt from the next harness transcript rather than trusting the
sender.

**Proof:** ten real A→human→B cycles with exact receipt evidence; report repeated
error rate before and after, including misses.

**Kill criterion:** if receipt does not change subsequent output behavior, stop
calling this learning and keep it as context transport.

### 3. Context Passport

**Hypothesis:** verified context can move between harnesses without losing
provenance, freshness, or human rulings.

**Build:** a portable signed packet containing source hashes, verification
dates, rulings, budget, and excluded/flagged context.

**Proof:** one packet moves Claude Code → Cursor Cloud → Codex; every harness
reports the same included hashes and honours one ruled-out claim.

**Kill criterion:** if adapters require harness-specific semantics in the core
packet, retain a shared receipt envelope but abandon universal execution
semantics.

### 4. Continuous Agent-Context Observatory

**Hypothesis:** instruction drift is measurable as an ecosystem property, not
just a one-time report.

**Build:** rerun the frozen corpus periodically, retain every executable receipt,
and publish precision-reviewed deltas without ranking or shaming repositories.

**Proof:** distinguish newly introduced, fixed, and unverifiable claims across
three observations; every published rate includes sampled or exhaustive
precision.

**Kill criterion:** if repository churn makes longitudinal identity unreliable,
publish dated snapshots only and do not imply trends.

## Launch sequence

1. Merge launch hardening.
2. Make the repository public.
3. Run `python3 scripts/launch_check.py --online`.
4. Record the 45-second video from a clean clone.
5. Ask Claude for the blind review in `REVIEW_PACKET.md`.
6. Fix only P0 truth/first-run failures.
7. Publish the short post; use the thread only if readers ask for methodology.
