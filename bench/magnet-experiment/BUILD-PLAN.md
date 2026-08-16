# MAGNET — build plan, written off EXP-MAGNET-01

The experiment settled three things, so the plan starts from evidence rather than
from a guess:

1. **The zero-token stage is viable.** 993 of 1000 discarded, precision 1.0 at
   every cutoff, 0 of 990 noise items admitted.
2. **It is deaf, not gullible.** recall@20 = 0.625; all three misses were the
   synonym arm.
3. **So the next build is a vocabulary, not a better score.** Tuning weights
   cannot recover a candidate whose signal was never detected.

Ordered by what the evidence says is binding. Each slice names the check that
would prove it worked, because a slice without one is a hope.

---

## S1 · Declared tags, verified — the recall fix

**The finding it answers:** `fault-localiser` is a debugging skill and scored 0
because the word `debug` is absent from its description.

A skill declares its own capabilities in frontmatter. The tagger's job is not to
guess them, it is to **verify the declaration against the skill's own text** —
which is cheap, decentralised, and turns an overclaim into a caught defect instead
of a missing keyword into a silent drop.

- Tag vocabulary is published and versioned, like `STACK_TARGET`.
- A tag carries the **content hash** it was computed from. Skill changes → hash
  mismatch → tag is stale and recomputes. Without this a tag silently describes a
  version nobody runs.
- A declared tag the text does not support is reported as **UNSUPPORTED**, not
  silently dropped and not silently trusted.

**Done when:** re-running EXP-MAGNET-01 with declared tags on the planted set
lifts synonym recall from 0/3, and the number is reported whatever it is.

## S2 · Behavioural gaps — replace the author's guess

**The finding it answers:** the gap list is currently `CAPABILITIES`, a dict its
own author wrote. It is a claim about Oscar with no evidence behind it.

Gaps derived from what actually happens:

- **what fires** — which of 30 installed skills are ever invoked. A stack with 30
  skills and 6 in use has a very different problem from one with a missing
  capability, and today MAGNET cannot tell those apart.
- **what is redone by hand** — repeated manual sequences across 2,425 transcripts.
- **what was already rejected** — a candidate considered and declined must not
  return every week.

**Done when:** the gap list is derived, and the derived list is diffed against the
hand-written one in public. If they agree, the hand list was fine and that is
worth knowing; if they disagree, the hand list was fiction.

**Overlaps feature E deliberately.** Both read transcripts. Build the reader once.

## S3 · The prediction record — the only real label

Every shortlisted candidate makes a checkable claim: *this fills gap X*. Record
the claim at adoption, check it at the next weekly reading.

- ADOPTED → KEPT at 30d → **FIRES** → the manual work it replaced stops appearing.
- The verdict says `coincident, not attributed` unless the displacement is
  measured. A skill installed in a week when a number moved did not necessarily
  move it.
- Cold start is 0 labels and the surface says **unmeasured**, never a default.

**Done when:** one adoption has a recorded prediction and a checked outcome,
including if the outcome is "nothing moved".

## S4 · Independent replication — the limit the experiment named itself

EXP-MAGNET-01's stated limit: *the filter's author wrote the planted set.* Until
that is broken, the numbers are indicative and not evidence.

- Run against a stack that is not Oscar's.
- Have the planted set built by someone, or something, that did not write the
  filter.
- Use real directory entries as noise, not synthetic ("practise flashcards with
  spaced repetition" is easier to reject than anything a real feed carries).

**Done when:** EXP-MAGNET-02 reports recall and precision on a stack and a planted
set the filter's author did not construct.

## S5 · Feed intake — last, and smallest

MAGNET reads `--candidates <file.jsonl>` and deliberately does not crawl. Several
directories already index this corpus and the coverage race is theirs. Intake is
a shim from whatever feed already exists.

**Done when:** the real feed's output flows in with no transformation written by
hand.

---

## Not doing, and why

- **Pairwise ranking of the flood.** ~500,000 comparisons, ~250M tokens, and the
  experiment shows a per-item test does the reduction for zero. Pairwise is for
  the handful of candidates inside one gap bucket, and only there.
- **A quality score.** The filter is lexical and deterministic; it cannot judge
  whether a skill is any good and must not pretend to. Fit is the claim; quality
  is the human's.
- **Auto-install.** Adoption is a ruling.
- **Rebuilding a directory.** Coverage is a scraping problem that is already
  solved twice over.
