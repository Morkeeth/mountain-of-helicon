# EXP-MAGNET-01 — can a zero-token filter find the few skills that fit?

**Preregistered 2026-08-16, before the harness was run.** Predictions below are
written first on purpose: a filter evaluated after its author has seen the output
is a filter tuned to its own test.

## The question

At ~1000 new agent skills a year, pairwise review is O(n²) — about 500,000
comparisons, roughly 250M tokens. MAGNET's bet is that the reduction from 1000 to
a shortlist can be done for **zero tokens**, deterministically, and that pairwise
judgement is then only needed *inside* a gap bucket (a handful of pairs).

The bet fails if the cheap stage drops the good ones. So the only number that
matters at stage 1 is **recall**, not precision.

## Hypothesis

**H1.** A deterministic gap-filter recovers planted good-fit skills from a flood
at recall@20 ≥ 0.80, at zero token cost.

**H0 (what would falsify the design).** Recall@20 < 0.80 — the cheap stage is
losing winners, and no amount of expensive stage-2 review can recover something
that was never shortlisted.

## Method

1. Take a real stack and compute its inventory and gaps.
2. Build a flood of 1000 candidates: **990 noise + 10 planted**.
3. Run `helicon brief magnet` over the flood. Zero model calls.
4. Score recall@20 and precision@3 against the planted set.

## The planted set — designed to include cases that should FAIL

Planting only things the filter already looks for would measure nothing. So the
10 are four kinds, and two kinds are adversarial:

| # | Kind | Expected |
|---|---|---|
| 3 | **Direct** — fills an uncovered capability using the filter's own vocabulary | FOUND (easy) |
| 3 | **Synonym** — fills a real gap using words the filter's list does not contain | **MISSED** — this is the known weakness, measured rather than hidden |
| 2 | **Surface** — targets an empty surface (`agents`) | FOUND |
| 2 | **Duplicate** — a near-copy of an already-installed skill | **DEMOTED, not surfaced** |

## Preregistered predictions

- **P1.** Direct (3/3) surface in the top 20. *Confidence: high — this is the
  filter's own vocabulary and it would be broken if it missed them.*
- **P2.** Synonym recovery ≤ 1/3. **The filter is expected to fail here**, and if
  it does, the finding is that a hand-written capability list cannot generalise —
  the same defect as a hand-written stoplist, one layer up.
- **P3.** Surface (2/2) surface in the top 20.
- **P4.** Duplicates score negative and appear in the bottom half.
- **P5.** Overall recall@20 lands **0.6–0.8**, i.e. *below* H1's threshold,
  because the synonym third is expected to fail.

**P5 means the preregistered expectation is that H1 FAILS as currently built.**
That is stated in advance so a poor result cannot be re-narrated afterwards as
the intended outcome.

## What each result would mean

| Outcome | Reading |
|---|---|
| recall ≥ 0.8 | the cheap stage holds; build stage 2 |
| 0.6–0.8 | the design holds, the *vocabulary* is the bottleneck → tags must be declared-and-verified, not guessed by a central list |
| < 0.6 | lexical gap-matching is not a viable stage 1; the filter needs behavioural input (what actually fires, what is redone by hand) before it is worth anything |

## Limits, stated in advance

- One stack. A result here does not generalise to other people's setups.
- The noise is synthetic and may be easier to reject than real directory entries.
- **The author of the filter also wrote the planted set.** The synonym arm is the
  partial mitigation — it is planted specifically to defeat the filter — but this
  is not an independent test and must not be reported as one.
