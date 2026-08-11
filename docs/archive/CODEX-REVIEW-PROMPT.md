# Codex review handover — Mount Helicon V2 Cockpit

**Repo:** `~/CODE/helicon-v2-night-run-2026-07-21` (a git worktree of `~/CODE/helicon`)
**Branch:** `night-run/2026-07-21-helicon-v2` (base `0eef89f`, **local only — not pushed**). Run Codex locally against this worktree. `main` is a frozen submission — do not touch it. If you want Codex remote, push the *branch* only (never main).

**Start by reading:** `NIGHTRUN-2026-07-21.md` (what was built + verified), then `mount-helicon-v2.1-vision-2026-07-21.md` in the vault (the intended product).

---

## The paste for Codex

```
You are reviewing Mount Helicon V2 — a "review-and-context control plane for
agentic work." Tonight's build added a Cockpit that reviews agent output across
terminals, grounds each claim against git/tests, lets a human rule keep/revise/
reject, propagates the correction into the next agent's context, and proves the
next agent can retrieve it.

Review it with your OWN criteria and find the errors and pitfalls. Do not adopt
my framing. Two hard rules:
1. The 402 passing tests are NOT evidence the product is correct or useful — a
   green suite proved nothing here (this project has shipped bugs past green
   suites before). Judge the running behavior and the code, not the test count.
2. Separate "the mechanism runs" from "this is product truth." Tell me which of
   my claims are actually true, which are overstated, and which are unverified.

Files to focus on:
- helicon/cockpit.py, helicon/api/cockpit.py   (the new engine + endpoints)
- helicon/review_terminals.py                   (the claim-vs-reality verifier it reuses)
- helicon/compiler.py inject_into_claude_code    (the write-back, now sandbox-able)
- web/src/components/Cockpit.tsx, ArtifactView.tsx (the UI)

Adversarially stress these specific pitfalls:
1. TRUTH GROUNDING: is "claim vs git/tests" actually sound? Where does it produce
   a false verdict — a wrongly-"contradicted" honest closeout, or a "verified"
   claim that is really false? Attack the ship/test/endpoint/url extractors.
2. PRIVACY: the cockpit relies on a SAFE_TERMINALS allowlist + a hard-private
   path regex. Find any path where a trading/wallet/journal repo, or private
   content inside a safe repo, could still surface via /api/cockpit or
   /api/cockpit/artifact (path traversal, symlink, label spoofing).
3. WRITE-BACK: inject_into_claude_code now takes output_dir for a sandbox. Find
   any path where a ruling could write to the real ~/.claude/skills without the
   explicit gate, or where the sandbox proof (contains_correction) could be
   faked/true-but-meaningless.
4. CONTINUITY HONESTY: the product claims the next agent "receives" a correction
   via a retrieval-path proof and a write-back file. Is the include-vs-obey
   distinction actually honest, or does the UI imply propagation from a DB write
   alone? Is the retrieval proof robust or does it only work on a seeded store?
5. THE OUTCOME GAP (most important): the vision says "steer by outcome, not
   mechanical staleness/drift." But this build grounds CLAIMS against git — a
   truth check, not an outcome check. The outcome spine (helicon/taskrun.py:
   objective->acceptance->verified outcome->accepted) is fully built but has
   ZERO callers. Is my admission correct that this is truth-grounded but NOT yet
   outcome-steered? What would it take to wire taskrun so the Cockpit is steered
   by "did the run meet its frozen acceptance test" instead of "is this claim
   consistent"?
6. DEAD / UNWIRED CODE and DAILY-USE FAILURE: what breaks the first week of real
   daily use? Empty states, concurrency on the SQLite store, the git scan cost
   per /api/cockpit call, stale terminal->repo labels, the never-run test path.

Deliver: a ranked list of real defects (most severe first, each with the exact
file:line and a concrete failure scenario), then the single highest-leverage
change. Be blunt. I want the pitfalls, not reassurance.
```

---

## Context for the arbiter (Oscar), not for Codex round 1
Withhold from Codex until after its blind pass (fresh-eyes rule): my own known limits are in `NIGHTRUN-2026-07-21.md` §Honest scorecard — continuity proven pull+write-back but not "obeyed"; `--run` opt-in; native shell unbuilt; multi-modal review (design/copy/tweet) not started. Compare Codex's independent findings against these; the deltas are the signal.
