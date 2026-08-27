# Which of your skills are earning their place

**Design, not a build.** Written against the object 2026-08-27 by T4. Every number below was
measured on this machine today; nothing is estimated.

Oscar's framing: *"mount helicon should review skill usage, what skills are good and should be
improved, benchmark your own agentic usage and setup. That is the onboarding and profile. It should
use transcripts, the biggest complaints, found files. Maybe even verifying claims, find rot,
optimise memory."*

---

## The one number that makes this a product

```
installed in ~/.claude/skills : 33
distinct skills ever fired    : 36        (17 of them plugin/built-in, not in the folder)
total firings, all transcripts: 364
NEVER FIRED                   : 14 of 33  —  42% of the library
```

Never fired once, ever: `board` · `codebase-design` · `domain-modeling` · `eyes` · `prototype` ·
`recon` · `research` · `wayfinder` · and the six `okx-*` skills.

**42% of an installed skill library has never run.** That is not a ranking problem and it is not a
discovery problem — it is the same shape as an index that does not match its directory, which is
what this product already is. A skill that never fires is memory that was never retrieved.

The corpus this reads: **2,710 transcript files, 1.3 GB**, at `~/.claude/projects/*/*.jsonl`.

---

## What already exists to stand on

| Piece | Where | What it gives |
|---|---|---|
| Skills as auditable memory | `helicon/connectors/skills.py` | Each SKILL.md is already a cube, so the battery — redundancy, thinness, contradiction — already applies to skills. **The quality half is largely built.** |
| Gap ranking | `helicon/magnet.py` | INVENTORY / GAPS / RANKED across five surfaces, deterministic, no model. Answers "what am I missing"; this answers "what am I carrying that does nothing". |
| The firing signal | transcripts | A skill invocation is a `tool_use` named `Skill` with `input.skill`. **Verified: 364 of them.** |
| Authorship gate | `fleet/human.py::is_human_turn` (hack-fleet-ata) | 46% of `type: user` turns are not the operator. Without this the denominator is fiction. |
| Survival proxy | transcripto's coach | Did the work outlast the session — committed and not reverted. |
| The index gate | `helicon/consistency.py` | Same question one level up: does the library match what claims to describe it. |

**What is missing is the join.** Nothing today connects *skill fired* → *session* → *what happened
next*. Every piece of that chain exists in a different module and none of them share a key.

---

## The constraint that decides the shape

**A benchmark can be won by a stub.** The skill-lift work proved it. So any number that claims a
skill is *good* has to carry two others beside it or it means nothing:

- **Firing rate** — how often it ran. Cheap, and measured above.
- **Discrimination rate** — did it fire when it should *and stay quiet when it should not*. A skill
  with a greedy description that fires on everything scores identically to a good one on firing
  rate alone.

Discrimination needs labelled opportunities: sessions where the skill *should* have fired. **Nothing
on this machine has those labels.** So the honest first slice does not emit a quality score at all.
It emits `UNMEASURED` where it is unmeasured, which is the same rule the rest of this product runs
on, and it is the reason the first slice is small.

---

## Slice 1 — `helicon skills`, an inventory joined to firing

**One command. No score. Worst-first.**

```
  SKILL                 FIRED   LAST         SESSIONS   QUALITY
  design-taste            46    2026-08-26      31       —
  sesh                    36    2026-08-27      28       —
  …
  research                 0    never            0       —
  recon                    0    never            0       —
  okx-defi                 0    never            0       —

  14 of 33 installed skills have never fired.
  QUALITY is UNMEASURED for every row: it needs labelled opportunities, and this
  machine has none. Firing count is not quality — a skill can fire constantly
  because its description is greedy.
```

Three columns, one join, and a refusal. It ships because:

- it needs **no model and no labels** — `os.listdir` on the skill roots, a grep-shaped pass over the
  transcripts, and a left join;
- **never-fired is actionable on its own.** Fourteen rows is a morning's decision: delete, rewrite
  the description, or admit the skill was aspirational;
- it makes the denominator visible, which is this product's whole thesis applied to itself.

**Cost:** the transcript pass is the only real work. Pre-filter with a literal string match before
parsing JSON — the full-corpus firing count above took seconds that way, versus minutes parsing
every line of 1.3 GB.

## Slice 2 — did firing change anything

Join each firing to its session's outcome using the survival proxy. Reports **firings that preceded
surviving work** versus **firings that preceded reverted or abandoned work**. Still not a quality
score: it is an association, the n is small per skill, and it must print its own n so nobody reads
one firing as a trend.

## Slice 3 — the description is the trigger

The skill that never fires usually has a description problem, not a content problem — Oscar's own
`skill_description_binds_early` note says a description framed as a closing step gets deferred.
`connectors/skills.py` already parses descriptions and the battery already scores thinness. Slice 3
points those at the 14 never-fired rows and proposes rewrites. **This is where the product stops
reporting and starts improving**, and it should not be attempted before slice 1 has been lived with.

## Not in scope yet, and why

**Discrimination**, until there is a labelled set. Building it from Oscar's own transcripts is
circular — the labels would come from the same sessions being scored.

---

## Honest limits, stated now rather than discovered later

1. **`Skill` tool_use is the primary firing signal, not the only one.** 160 `<command-name>` blocks
   also exist in the corpus; most are `/clear` and `/model`, but `/deep-research`, `/sesh` and
   `/frame` appear there too. Slice 1 must count both shapes or state which it counts.
2. **36 distinct skills fired but only 33 are installed** in `~/.claude/skills`. Seventeen fired
   names are plugin or built-in and live elsewhere. An inventory keyed only on that folder will
   show phantom zeroes and miss real usage — the roots have to be enumerated the way the harness
   enumerates them.
3. **A firing count is retrospective.** A skill installed yesterday and a skill ignored for five
   weeks both read zero. The row needs an install date or the number libels new skills.
4. **The corpus is one operator.** Everything here describes Oscar's machine. Nothing in it
   generalises to a population without a second machine, and the count should never be presented as
   though it did.

---

*T4. Design only — nothing built, nothing pushed. `~/CODE/mountain-of-helicon` is public and on
PyPI; every commit in this lane is local.*
