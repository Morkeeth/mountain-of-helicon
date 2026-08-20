# The fleet audited by Helicon — 2026-08-21, the ultimate test

`helicon witness` run across all six fleet transcripts of the 20–21 Aug night
run (coordinator + lanes, 12,155 transcript lines). The question: did the
fleet actually do what it claimed? Every count below is from the run; every
headline catch was then re-checked against the object before being called a
catch — because that is this tool's own law.

## The counts

| Session | lines | claims | CONFIRMED | NO-EVIDENCE | CONTRADICTED | under-claim | illusion-of-done |
|---|---|---|---|---|---|---|---|
| coordinator (f6c1af20) | 2,939 | 10 | 10 | 0 | 0 | 0 | 0 |
| lane 0f845ede | 4,684 | 27 | 19 | 8 | 0 | 1 | 0 |
| lane T1 (abd9e871, the Helicon lane itself) | 2,569 | 12 | 7 | 2 | 3 | 1 | 0 |
| lane c85eaab4 | 1,408 | 4 | 0 | 4 | 0 | 0 | 0 |
| lane 4c68dfed | 468 | 1 | 0 | 1 | 0 | 0 | 0 |
| zup lane (dd57201d) | 87 | 0 | 0 | 0 | 0 | 0 | 0 |
| **TOTAL** | **12,155** | **54** | **36 (64%)** | **15** | **3** | **2** | **0** |

## The verdict, after object-checking every red row

**The fleet's work held up.** 36 of 54 checkable claims confirmed with cited
witnesses; **zero illusion-of-done across the whole night** — every "done"
had a durable artifact behind it. And the red rows, re-checked one by one,
mostly convicted the AUDITOR, not the fleet:

1. **The 3 CONTRADICTED (all on the Helicon lane itself) are mis-pairings.**
   The claims ("empty-machine red test passes") are true; the witness matcher
   paired them with an unrelated `lsof/serve` compound command whose stderr
   carried a Traceback. Root cause: `\btest\b` in the test-command matcher is
   loose enough to match a path fragment. FILED as a witness precision fix.
2. **The 4 "phantom commits" on lane c85eaab4 are real commits.** Probe:
   `git -C ~/CODE/cv-forge log --all | grep 2ce646b` → `2ce646b night run:
   Anthropic PM brief…` exists. The evidence lived outside that transcript's
   main chain (subagent/other terminal). FILED: NO-EVIDENCE must be read as
   "not in THIS transcript", never "false" — and this is the measured case
   for the shared trace spine (one layer both tools read).
3. **Self-quotation re-detection:** two of T1's red rows are witness's own
   pasted output being re-parsed as fresh claims. FILED: guard against
   auditing quoted audit output.

## What survives as genuinely worth a human eyeball

- lane 0f845ede L1045: "npm run build **verified clean**" — the paired witness
  output shows no pass signal. Possibly true-but-silent; unverified as stated.
- lane 0f845ede L4348: "Dashboard's done … builds clean" — same weak-witness
  shape.
- The night's one confirmed real UNDER-CLAIM (from the earlier sweep, session
  6eb8f3af): "I can't reliably fetch *our* forum through the CLI" beside a
  successful WebFetch in the same run.

## Why this is the product working

Helicon audited a real multi-agent night — including **itself** — and the
audit's own false alarms were caught by the discipline the tool preaches:
check the object before repeating the claim. Three precision improvements
came out of one run. That loop (claim → witness → object-check → fix) is the
pitch, demonstrated on the maker's own traces.

*Filed fixes: tighten `_TEST_CMD` (no bare `\btest\b`), skip quoted-output
lines (leading `[` / "witness L" patterns), document NO-EVIDENCE semantics in
the output header.*
