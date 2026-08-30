# EXP-MAGNET-01-S1 — declared-and-verified tags

Run 2026-08-16, after S1 was built. Reproduce: `python3 bench/magnet-experiment/run-s1.py`.
Same 1000-candidate flood as EXP-MAGNET-01, same seed, **zero model calls** — the
only change is that the three synonym planted items now carry a declared
`capabilities` field, as a real skill author would write.

## What S1 answers

EXP-MAGNET-01 found the filter is **deaf, not gullible**: primary recall 0.625,
every miss a synonym, zero noise admitted. S1 lets a skill DECLARE its
capabilities and VERIFIES the declaration against its own text.

## Result

| | pre-S1 | S1 |
|---|---|---|
| recall, **trustable primary tier** | 0.625 | **0.625** |
| recall, **with author-claims tier** | — | **1.000** |
| precision@3 | 1.0 | 1.0 |
| noise in primary | 0 | **0** |
| synonym arm | 0/3 | recovered into the claims tier, 3/3 |

**The primary number did not move, and that is the honest result.** A
deterministic filter cannot confirm that "narrow a misbehaving program to the
smallest failing input" is a debugging skill — only that its author says so. So
the synonyms are recovered into a SEPARATE, clearly-labelled *author-claims*
tier, at lower confidence, never into the trustable shortlist. A human reviewing
both tiers recovers 1.0; a human trusting only the top tier is exactly as safe as
before S1.

## The gaming hole the first S1 build opened, and how it was closed

The first cut let a claim add to the score. Re-running the adversarial case
immediately exposed it: a wine-pairing skill declaring `[debug, refactor,
security]` scored **4 and OUTRANKED an honest synonym scoring 2**. Declaring more
lies bought a higher rank — the precise inversion of what the tool is for.

Two rules closed it, both now locked by tests:

1. **A claim adds nothing to the score.** The primary ranked list is text-verified
   evidence only, so it is exactly as trustable as it was before declarations
   existed. A liar can never enter it.
2. **The author-claims tier is ordered by name, never by claim count.** A tier
   ordered by a number the author controls is a tier the author games. The
   wine-spammer lands in the claims tier, flagged, and its three declared lies
   buy it nothing over an honest one-tag synonym.

## What this settles for the build plan

- **S1 works, with the honest caveat stated.** Declarations recover the synonym
  case that inference is structurally deaf to — but only into a lower-confidence
  tier, because deterministic verification can flag a claim, not confirm it.
- **The verified/claimed split is the trust mechanism.** An author's declaration
  is a signal, not a fact; the split makes the difference visible on the card.
  This is the same declare-and-verify shape the trust discussion landed on: tag
  centrally, match locally, and never trust a claim you cannot check.
- **What would raise primary recall is a JUDGE on the claimed tier** — the
  `claimed` → `verified` promotion is where an LLM earns its cost, on a handful of
  candidates, not on the flood. That is the natural stage 2, and it is exactly
  where the token budget the whole design saved should be spent.

## Limits, still holding

- Same synthetic flood, same single stack, same author-wrote-the-planted-set
  caveat as EXP-MAGNET-01. S1 does not touch S4 (independent replication).
- The synonym recovery is only as good as the author's honesty in declaring, and
  the claims tier is where dishonesty is quarantined rather than eliminated.
