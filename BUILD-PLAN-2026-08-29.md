---
doc: build-plan
project: Mount Helicon
last-touched: 2026-08-29
canonical: true
companion: VISION.md (why) · this file (when + done-when)
---

# Helicon — build plan · Aug 2026

> **VISION.md** is the north star. **This file** turns the five pillars into ordered slices.
> Qwen hackathon shipped the govern loop; these slices grow Continuity, Direction, and Reflection.

---

## 📣 PROMISE LINE (rewrite before next venue)

**Promise.** You always know **what your agents decided, what is still true, and what needs your
judgment** — without opening six terminals or trusting a model's done-report.

**Constraint.** Uncertain knowledge stays uncertain. **DEGRADED** is printed, never hidden.

**Named user (P3 — open).** One person besides Oscar runs `helicon demo` and rules one conflict.
Slice 2.

---

## ✅ SLICES (ordered)

### Truth (foundation — mostly shipped)

- [x] **T1. Govern loop.** audit → human ruling → verified apply → guard → undo.
  · shipped · `GOLDEN_SUBMISSION.md`
- [ ] **T2. Named stranger rules once.** Not Oscar. One conflict resolved, receipt shows
  `compiled_into_law`.
  · done when: quoted feedback + receipt id in `docs/ADOPTION-RECEIPT.md` · S · **🧑 Oscar invites**
- [ ] **T3. Confidence per belief.** Weak support shown weak in dashboard — not binary stale/fresh.
  · done when: one belief row shows confidence source · M
- [ ] **T4. Meta-review.** Rule the engine's own judgments (exam critiques the examiner).
  · done when: one false-positive from rot exam overturned by meta pass · L

### Continuity (cross-harness context)

- [ ] **C1. Context packet export.** TaskRun/ContextPacket recorder → portable JSON a stranger can
  read.
  · done when: `helicon export <run-id>` prints schema-valid packet · M
- [ ] **C2. Context packet import proof.** One harness **receives** packet and logs "got it" —
  not just candidate file on disk.
  · done when: integration test: export → import → attested field match · L

### Direction (routing with a floor)

- [ ] **D1. Routing receipt.** When route withheld below quality floor, user sees **why**, not silence.
  · done when: CLI prints withheld reason on one real task class · M
- [ ] **D2. Cost vs outcome one-pager.** Yesterday's expensive model vs cheap on same task class —
  the 9am briefing seed.
  · done when: `helicon reflect --yesterday` prints one comparison row · M

### Reflection (after the work)

- [ ] **R1. Morning reflection surface.** Three actions worth attention — not three hundred.
  · done when: `helicon morning` output matches VISION.md north-star paragraph on seeded demo · M
- [ ] **R2. Run ledger browse.** What changed, what it cost, what worked — one command.
  · done when: stranger finds yesterday's runs without asking Oscar · S

### Calm (govern-by-exception — partial)

- [x] **K1. Bulk handled, exceptions escalated.** Rot triage + one-tap ruling.
  · shipped in demo path
- [ ] **K2. 9am briefing wired to real data.** Not fixture-only.
  · done when: K2 runs on Oscar's store without `--demo` · L

---

## 🎯 NOW

**Slice T2 — named user.**

Helicon lost Qwen on P1/P3/P4 (category line, only Oscar as user). Before the next competition or
public push: one stranger rules once.

---

## 🪵 LOG

- 2026-08-29 · BUILD-PLAN created from VISION.md pillar table. No dated plan existed before today.
