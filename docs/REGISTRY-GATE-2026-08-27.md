# The registry gate, and the file-duplication check one level down

**T4, 2026-08-27.** Part one built and tested. Part two designed, not built.

## What shipped

`helicon registry` — the consistency gate pointed one level out. There the index is a `MEMORY.md`
and the population is a directory of notes; here the index is the vault's registry table and the
population is what Oscar owns: GitHub repos and `~/CODE` directories.

**Measured on the real registry:** 67 rows · 67 live repos · 108 dirs in `~/CODE` · 13 archived and
8 forks excluded → **32 repos with no row**, 2 mentioned in prose only, 2 rows pointing at a repo
that is not there.

Three design calls, each of which the check dies without:

**Three strengths of evidence, not two.** Registry prose names other repos constantly, so a naive
"is this string in the file" marks nearly everything covered — a green light that means the matcher
is broken. `ROW` (named in the Initiative column) / `PROSE` (mentioned but owns no row, counted, not
flagged) / `NONE` (the gap).

**Containment matching with a floor.** Row 056 reads `THE AGENT WORK RECORD WITNESS`; the repo is
`agent-work-record-witness-ata`. Exact equality reports a false gap on a row somebody just wrote.
The floor is 8 characters, because over-matching *hides* gaps and that is the failure that matters
more here.

**The reverse drift had to be narrowed to survive.** "Rows with no repo" was 39 of 67 — `Journaling
+ scrapbook`, `Wave Radio`, `Job hunt` own no repo and never should. That is the wall that gets a
morning check closed on day two. A row now only drifts when it *points at* a repo — `~/CODE/x` or
`Morkeeth/x` written into the row — that resolves to nothing. 39 → 2.

**A control that had never been watched firing.** The ghost check returned 0 on the real registry
and that zero was a **false negative**: the row regex captured only the Initiative column, and repo
pointers live in the prose column. The red-light test caught it. Nobody audits a check that says no.

---

## Part two — the same shape one level down, designed only

The brief said `magnet.py` exists in four places with no owner. **At the object it is five files,
four distinct hashes**, and the count conflates three different problems:

```
  66  6494a1f7  measurement-bench/magnet.py
 385  4fbf4013  mountain-of-helicon-main/helicon/magnet.py
  86  f0e59b50  agent-bench/science/magnet.py
 499  db801efa  mountain-of-helicon/helicon/magnet.py
 385  4fbf4013  mountain-of-helicon-main/build/lib/helicon/magnet.py
```

1. ~~**A diverged second checkout.** `mountain-of-helicon` and `mountain-of-helicon-main` are the
   same repo, 499 lines against 385. **This is the finding.**~~ **WRONG, corrected when the check
   was built.** `mountain-of-helicon-main` is a git **worktree** of `mountain-of-helicon` —
   `git rev-parse --git-dir` there returns
   `…/mountain-of-helicon/.git/worktrees/mountain-of-helicon-main`. A worktree at another commit is
   the fleet's intended workflow, not drift. Same for `zup-swiftui-glass`. I inferred "two checkouts"
   from a line count and a shared name without asking git what the directory was.

   **The real finding, measured:** `Morkeeth/Loop` has **three independent clones** — `Loop`,
   `loop-labs`, `loop-labs-main` — all on `main`, at three different commits, one with uncommitted
   changes. That is the case the check exists for, and no filename comparison would have surfaced it.
2. **A build artifact.** `build/lib/...` is byte-identical to its source. Reporting it is noise.
3. **Two unrelated files that share a name.** 66 and 86 lines, different projects. Not duplication
   at all — a name collision.

**So a filename-based duplicate check would report four findings, of which one is real, one is
noise, and two are false.** The useful check is not "same name" but **same repo, two checkouts,
different content**:

```
helicon checkouts     # for each git remote, every working copy on this disk,
                      # flagged when their HEADs diverge
```

Cheap and deterministic: walk `~/CODE` one level, read `git remote get-url origin` and
`git rev-parse HEAD` per directory, group by remote, flag any group with more than one distinct
HEAD. No content hashing, no heuristics, no model. **Built 2026-08-27.** Two things the design
above missed, both found by running it: a repo with no remote must never be grouped (21 of them
would collapse under one `(none)` key — the loudest available false positive), and a git worktree
must be told apart from a clone via `--git-common-dir`, because it is a second checkout on purpose. It answers "am I about to edit the stale copy",
which is the question the filename count was reaching for.

**Do not build the filename version.** It produces a wall with a 25% hit rate, which is the exact
failure mode this lane just spent its effort avoiding.

---

*Local commits only. `~/CODE/mountain-of-helicon` is public and on PyPI; nothing pushed.*
