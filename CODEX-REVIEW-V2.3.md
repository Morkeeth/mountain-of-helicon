# Codex review handover — Mount Helicon V2.3 (subtraction + the valuation gate)

**Repo:** `~/CODE/helicon-v2-night-run-2026-07-21` (a git worktree of `~/CODE/helicon`)
**Branch:** `night-run/2026-07-21-helicon-v2` (tip `fc88148`, **local only — not pushed**). `main` is a frozen submission — do not touch it.
**State:** V2.3 is **uncommitted working-tree changes** on top of `fc88148`. Review the working tree, not the last commit.

**Read first:** `CODEX-REVIEW-PROMPT.md` (the V2 round — this is its sequel), then `~/CODE/helicon-product-vision-v2.md` §"The three-tier spine" (the product this is trying to become).

---

## The paste for Codex

```
You are reviewing Mount Helicon V2.3, a "memory-governance cockpit for one
operator running many agents." Two changes since the last review, plus three
unfixed defects I want you to rule on.

Review with your OWN criteria. Do not adopt my framing. Three hard rules:
1. The 421 passing tests are NOT evidence of correctness. This project has
   shipped real bugs past a green suite before. Judge the code and the behavior.
2. Separate "the mechanism runs" from "this is product truth." Tell me which of
   my claims are true, which are overstated, and which are simply unverified.
3. I have marked my own reasoning inline in the code. Treat those comments as
   claims to attack, not as documentation to trust.

=== CHANGE 1: the valuation gate (the important one) ===

Files: helicon/valuation.py (new), helicon/db.py (init_db migration),
       helicon/api/findings.py (_audit_findings query), helicon/cli.py (cmd_queue),
       tests/test_valuation.py (new)

The problem: the operator's real store had 335 open findings demanding human
rulings. The vision says tier 2 should be "a handful per day, not hundreds."
Measured: 227 of 335 (68%) were about memories ALREADY KILLED.

The fix: a three-gate filter. A finding reaches a human only if it has
CONSEQUENCE (target memory still live), NEEDS_HUMAN (not already settled by a
rename or a prior dismissal), and STILL_TRUE (re-verifies now). Result on the
real store: 334 considered -> 90 escalated, 244 auto-retired.

Attack these specifically:
1. WHAT REAL FINDING DOES THIS EAT? This is the whole risk. A gate that hides a
   true finding is strictly worse than a long queue, because the operator now
   trusts a queue that lies by omission. Find the case where _consequence,
   _needs_human, or _still_true retires something that mattered. The
   review_status == 'killed' shortcut is the one I am least sure of: is "killed"
   really terminal in this store, or can a killed memory still reach an agent?
   Check against embeddings._load_all_embeddings and db.search_cubes.
2. THE PRECEDENT MATCHER. _normalize() strips quoted subjects and all digits,
   then requires an exact match on the remainder plus the same audit_type. Show
   me a false positive: two genuinely different findings that normalize to the
   same string and so get silently killed by one old dismissal. I think this is
   the weakest code in the change.
3. THE LAW BOUNDARY. gold.py compiles GOLDEN_RULES from
   `audit_log WHERE human_decision IS NOT NULL`. The gate deliberately writes
   machine_decision/machine_reason/machine_decided_at instead, so a machine
   verdict can never forge an operator ruling into the stack's law. Verify that
   boundary actually holds everywhere — including undo(), the API filter, and any
   other reader of audit_log you can find. Is there a path where a machine
   decision influences the compiled law, the triage rules, or the Q-value/utility
   learning?
4. THE GATE I REFUSED TO BUILD. The vision says consequence = "live AND used." I
   did NOT gate on usage: retrieval_log has 28 rows against 9,081 memories, so
   gating on it would retire nearly everything for missing data. Was that the
   right call, or is there a sound usage signal in this store I overlooked?
5. _still_true() only re-checks findings whose text contains "dead path", and
   passes everything else. Is "pass when unsure" the right default here, or does
   it make gate 3 decorative? It fired 0 times on the real store.

=== CHANGE 2: navigation subtraction ===

Files: web/src/App.tsx, web/vite.config.ts

19 tabs -> 5 (Cockpit, Needs Ruling, Golden Rules, Morning Brief, Memory). The
mobile "More" sheet and its component were deleted; the bottom bar is now the
whole nav. Every component and every `tab === '...'` render branch still exists —
this is a navigation cut, not a delete.

Attack: did I cut something load-bearing? Specifically, is any removed tab the
ONLY entry point to a flow that has no other surface (Triage, Consolidation,
Skills audit, Store audit, Volatility, Setup report)? Are there dangling links,
deep links, or keyboard shortcuts that now go nowhere or to the wrong index?

=== CHANGE 3: three defects I found and did NOT fix — rule on them ===

I drove `helicon run` and `helicon hook` end-to-end against a real TaskRun and
found three seams. I want your independent read on severity and on whether the
next slice should proceed before they are fixed.

a) A run opened by `helicon run open` NEVER appears in the UI. cmd_run writes
   task_runs; helicon/api/runs2.py:87 run_list() selects only from run_captures.
   /api/run/detail returns {"ok":false,"error":"run not found"} for a run that
   demonstrably exists. So "govern before work" is terminal-only.
b) The hook DOES deliver (verified: real UserPromptSubmit payload in, rulings
   out, privacy gate refuses non-safe repos, a 'delivered' run_event is written)
   — but helicon/cockpit.py:288 _delivery_state() hardcodes
   delivered_to_live_run: False and never reads those events. The UI tells the
   operator "Not yet delivered to any live run" AFTER a real delivery.
c) The installed `helicon` console script resolves to a DIFFERENT checkout and
   has no `run`/`hook` subcommand. `helicon hook --print-config` emits a
   settings.json snippet telling the user to run `helicon hook userprompt`, which
   would silently no-op forever in a real Claude Code session.

Deliver: a ranked list of real defects (most severe first, each with exact
file:line and a concrete failure scenario), your verdict on whether the
valuation gate is safe to run against the operator's real 9,081-memory store,
and the single highest-leverage next change. Be blunt. Pitfalls, not reassurance.
```

---

## Reproduce the numbers yourself (do not trust mine)

```bash
cd ~/CODE/helicon-v2-night-run-2026-07-21
cp ~/CODE/helicon/data/helicon.db /tmp/copy.db          # never review against the live store
echo '{"db_path":"/tmp/copy.db","connectors":{}}' > /tmp/qcfg.json
HELICON_CONFIG=/tmp/qcfg.json PYTHONPATH=. python3 -m helicon queue        # dry run
HELICON_CONFIG=/tmp/qcfg.json PYTHONPATH=. python3 -m helicon queue --apply
HELICON_CONFIG=/tmp/qcfg.json PYTHONPATH=. python3 -m helicon queue --undo # must restore all 244
PYTHONPATH=. python3 -m pytest tests/ -q                                    # 421
```

---

## Context for the arbiter (Oscar) — withhold from Codex round 1

Fresh-eyes rule: Codex uses its own criteria first. My own known limits, for
comparison against whatever it finds independently — the deltas are the signal:

- **Gate 3 is nearly decorative.** `_still_true` fired 0 times on the real store.
  It only handles "dead path" findings and passes everything else.
- **The precedent matcher is crude.** Normalized-exact-match on finding text. I
  expect this to be Codex's top finding, and it should be.
- **90 is not "a handful."** The vision's target is single digits per day. What
  remains (50 dead-path, 27 temporal, 13 routine) is a genuine unworked backlog,
  and no further gating fixes that — only working it does.
- **The nav cut is reversible but unvalidated by use.** I removed 14 tabs on
  evidence of low data volume, not on evidence Oscar never needs them.
- **`web/dist` churn** in the diff is a side effect of my verification build; it
  now matches the 5-tab source, which is correct for the ECS deploy but makes the
  diff look far larger than the change.
- **Nothing was applied to the real store.** Every number above came from a copy.
