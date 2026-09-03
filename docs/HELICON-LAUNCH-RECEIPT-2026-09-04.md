# Helicon launch receipt · 4 Sep 2026

**Repo:** `Morkeeth/mountain-of-helicon` · branch `cursor/verify-first-receipt-ecdd`  
**Wave:** Verify-first + HorseTrack spine  
**Constraint:** no PyPI upload · no foreign PR opened · outward acts = Oscar's click

## Done-when (each box names the command that was RUN)

### Verify group first

```bash
$ helicon --help | head -25
```

```text
usage: helicon [-h] <command> ...

Find out which of your agent's documents are lying — with evidence, before the
work starts.

Verify:
  truth Point it at ANY agent memory/notes store (Claude Code / Cursor /
  Cline / an Obsidian vault) -> ranked, evidence-cited staleness+rot report.
  No config, no DB, no key, no LLM.

  witness Claim-witness ledger: agent claims in prose vs the tool evidence
  in the trace (keyless, local)

  review Review a repo's agent setup: does its CLAUDE.md/AGENTS.md lie to
  the agent?

  ci CI for agent memory: scan this repo's rules files + run the rot exam
  (GitHub annotations, exit 1 on rot)

  doctor Health check: PATH, config, Qwen key, DB, last scan

Lab:
  demo Seed a demo store and open the dashboard (one command, no key, no
  personal data)
```

- [x] Verify group first; `truth` listed first under Verify  
  Command: `helicon --help | head -25` (2026-09-03 night, this VM). Already on `main` from S2 (`5260fe9`); re-confirmed, not re-implemented.

### Launch contract green

```bash
$ python3 scripts/launch_check.py
READY: source-controlled gates pass.

$ TMPDIR="$HOME/pytmp" python3 -m pytest tests/test_launch_contract.py -q
........                                                                 [100%]
8 passed in 0.31s
```

- [x] `launch_check.py` → READY  
  Command: `python3 scripts/launch_check.py`  
  **Before fix:** BLOCKED on `package-metadata` — `"Mountain of Helicon"` missing from `pyproject.toml` since `747a550`. Detail string still said "distribution name remains a founder decision" even though `LAUNCH_ROADMAP.md` already settled `mountain-of-helicon`.  
  **After fix:** description restored; gate detail now prints the distribution name when green.

- [x] `tests/test_launch_contract.py` → 8 passed  
  Command: `TMPDIR="$HOME/pytmp" python3 -m pytest tests/test_launch_contract.py -q`

### Pointer precision (HorseTrack-driven)

```bash
$ TMPDIR="$HOME/pytmp" python3 -m pytest tests/test_pointers.py tests/test_pointers_precision.py -q
..............................                                           [100%]
30 passed
```

- [x] Pointer suite green after negation + dotfile fix  
  Command above.

## HorseTrack at the object (not the August ledger)

```bash
$ git clone --depth 1 https://github.com/hoangtruong01/HorseTrack /tmp/HorseTrack
$ cd /tmp/HorseTrack && git rev-parse HEAD
3ee8c1ffd60cefeabc1e019f532d3d64543c2f49
```

Same tip SHA as the 2026-08-09 ledger. Re-derived at the clone, not carried.

### Evidence commands (every broken path)

```bash
$ for f in MASTER_GUIDE.md PORTABILITY.md shared/skills .roomodes \
    'roo/.roo/rules' 'claude/.claude/agents' 'Codex/.Codex/agents' \
    docs/verification-matrix.md ai-workflows; do
    echo -n "git ls-files -- $f -> "; git ls-files -- "$f" | wc -l
  done
```

All returned `0`.

### Product arm vs naive baseline

| Arm | Command | Broken pointers |
|-----|---------|-----------------|
| **Naive (2-hour floor)** | extract `` `path` `` from CLAUDE.md/AGENTS.md → `git ls-files` / disk | **16** |
| **Helicon before tonight's fix** | `helicon review .` on this checkout | **12** (lost to naive) |
| **Helicon after fix** | `helicon review .` | **16** (ties naive) |

```bash
$ helicon review .
# GRADE F · 18 references checked, 16 broken
```

**What beat us:** bare `\bnot\b` in the absence filter matched "not the primary architecture" and silently dropped `claude/.claude/agents/` + `Codex/.Codex/agents/`. Dotfile `.roomodes` was never path-shaped (no slash, no code ext). Fixed in `helicon/pointers.py`; fixtures in `tests/test_pointers_precision.py`.

**Still true after the fix:** Helicon does not beat the naive arm on this repo — it matches it. The product value on HorseTrack tonight is grade + file:line receipts + exit 1 for CI, not a higher recall count.

## Artifacts this receipt points at

| Path | Role |
|------|------|
| `docs/PR-01-HORSETRACK-READY.md` | Paste body for Oscar — **do not open from this agent** |
| `hack.md` | WAVE 2026-09-04 contract + LOG |

## Oscar gates (not run)

```bash
# DO NOT RUN from this agent
python3 -m twine upload dist/*
# DO NOT open https://github.com/hoangtruong01/HorseTrack/compare/...
```

## Verdict

✅ Verify-first help confirmed at object · ✅ launch_contract READY (8 passed) · ✅ HorseTrack re-verified at `3ee8c1f` · ✅ paste draft ready · ⚠️ Helicon lost to naive baseline until the negation/dotfile fix · ⚠️ full-suite count re-derived separately in the PR body
