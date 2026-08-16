# EXP-MAGNET-01 — results

Run 2026-08-16 against `~/.claude`. Reproduce: `python3 bench/magnet-experiment/run.py`.
Seeded, deterministic, **zero model calls**. Predictions in `PREREGISTRATION.md`
were written before the harness ran.

## Headline

**H1 is FALSIFIED. recall@20 = 0.625, below the 0.80 threshold.**
**All five preregistered predictions were correct, including the one that said H1 would fail.**

| | value |
|---|---|
| flood | 1000 (990 noise + 10 planted) |
| token cost | **0** |
| recall@20 | **0.625** (5 of 8 that should surface) |
| precision@3 | **1.000** (no noise in the top 3) |
| unranked (no signal) | 993 of 1000 |

By arm:

| arm | result | predicted |
|---|---|---|
| direct | **3/3** | 3/3 ✅ |
| surface | **2/2** | 2/2 ✅ |
| synonym | **0/3** | ≤1/3 ✅ |
| duplicate | both at −4, demoted | negative ✅ |

## The first run was wrong, and preregistration is the only reason we know

The first run reported **recall@20 = 0.875 — a pass.** It was an artifact.

All three synonym candidates scored **0, identical to all 990 noise items.** Two
of them still appeared at rank 5 and 6, because the ranker broke ties by name and
`code-surgeon` and `fault-localiser` sort before `noise-000`. `postmortem-pilot`
sorts after `noise-` and landed at 997. Same score, same evidence, 991 places
apart — decided by the alphabet.

Without a preregistered prediction that the synonym arm should FAIL, 0.875 would
have been read as a pass and shipped.

**The fix is in the product, not the harness.** `helicon.magnet.rank` no longer
orders items with no positive signal at all. They are returned as a count —
"993 showed none and are not ranked" — because a ranking that cannot say *no
evidence* will always invent one. Re-run after the fix: 0.625.

## What it means, read off the preregistered table

The 0.6–0.8 band was written in advance to mean: **the design holds and the
vocabulary is the bottleneck.**

- **The cheap stage is viable.** 993 of 1000 discarded for zero tokens, precision@3
  of 1.0, and both planted duplicates demoted below everything. Against ~500,000
  pairwise comparisons (~250M tokens) for a full order, this is the reduction the
  whole design was betting on.
- **A hand-written capability list cannot generalise.** `fault-localiser`
  ("narrow a misbehaving program to the smallest failing input") is a debugging
  skill and the filter saw nothing, because the word `debug` is absent. Same
  defect as a hand-written stoplist, one layer up, and the fourth time this class
  has appeared in this codebase in one day.
- **So the tag vocabulary cannot be a central guess.** The skill must declare its
  own capabilities and the tagger must VERIFY the declaration against the skill's
  text — cheap, decentralised, and it makes an overclaim detectable instead of
  making a missing keyword fatal.

## Limits — restated, because they still hold

- **One stack.** Nothing here generalises to another person's setup.
- **Synthetic noise.** Real directory entries are harder to reject than
  "practise flashcards with spaced repetition".
- **The filter's author wrote the planted set.** The synonym arm is planted
  specifically to defeat the filter and it did, which is some mitigation — but
  this is not an independent test and must not be reported as one.
- **The clean precision was partly luck, and a unit test caught it.** Capability
  terms were matched as SUBSTRINGS, so `"ui"` matched inside `"g-ui-tar"` and
  "tune a guitar by ear" — an item in this experiment's own noise set — scored as
  a DESIGN skill. It did not corrupt the result only because `design` was already
  covered on this stack and so was never one of the uncovered capabilities being
  matched. On a stack without a design skill, that noise item would have entered
  the shortlist. Fixed to word-boundary matching; the numbers above are the
  post-fix run and are unchanged. **The precision of 1.0 is therefore conditional
  on which capabilities happened to be uncovered here, and the caveat stands even
  after the fix.**
- **The `duplicate` arm is easy by construction.** Both planted duplicates were
  written by paraphrasing installed skills, so a lexical overlap test was always
  going to catch them. A duplicate expressed in different words would not be.
