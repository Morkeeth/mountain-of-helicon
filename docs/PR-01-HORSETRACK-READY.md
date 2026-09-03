# PR-01 · HorseTrack — paste-ready (do not open from agent)

**Target:** https://github.com/hoangtruong01/HorseTrack  
**Base tip re-verified:** `3ee8c1ffd60cefeabc1e019f532d3d64543c2f49` (default `main`, cloned 2026-09-03)  
**Opener:** Oscar only. This file is a draft. The cloud agent must not open the PR.

---

## Title (paste)

```
docs(agents): stop pointing CLAUDE.md/AGENTS.md at files this repo does not have
```

## Body (paste)

````markdown
## Why

`CLAUDE.md` and `AGENTS.md` tell agents this tree is an `ai-workflows/` repo whose
source of truth lives in `MASTER_GUIDE.md`, `PORTABILITY.md`, `shared/skills/`,
`.roomodes`, `roo/.roo/rules/`, stub agent dirs, and
`docs/verification-matrix.md`.

None of those paths are in this repository at `3ee8c1f`.

An agent that trusts the files walks into dead ends before the first real edit.

## Evidence (re-runnable, no API key)

```bash
git clone https://github.com/hoangtruong01/HorseTrack && cd HorseTrack
git rev-parse HEAD   # expect 3ee8c1f… while tip is unchanged

git ls-files -- MASTER_GUIDE.md PORTABILITY.md
# (no output)

git ls-files -- shared/skills .roomodes 'roo/.roo/rules' \
  'claude/.claude/agents' 'Codex/.Codex/agents' docs/verification-matrix.md
# (no output)

# Optional, same findings with receipts:
pip install mountain-of-helicon   # or: pip install -e /path/to/mountain-of-helicon
helicon review .
# GRADE F · 18 references checked, 16 broken
```

Exact lines (both files mirror each other):

| File:line | Claim | `git ls-files` |
|-----------|-------|----------------|
| `CLAUDE.md:3` / `AGENTS.md:3` | this is an `ai-workflows/` repo | empty |
| `CLAUDE.md:9` / `AGENTS.md:9` | Read `MASTER_GUIDE.md` | empty |
| `CLAUDE.md:11` / `AGENTS.md:11` | Read `PORTABILITY.md` | empty |
| `CLAUDE.md:12` / `AGENTS.md:12` | Treat `shared/skills/` as canonical | empty |
| `CLAUDE.md:13` / `AGENTS.md:13` | Treat `.roomodes` as Roo mode source | empty |
| `CLAUDE.md:14` / `AGENTS.md:14` | Treat `roo/.roo/rules/` as rules | empty |
| `CLAUDE.md:15` | Treat `claude/.claude/agents/` as stubs | empty |
| `AGENTS.md:15` | Treat `Codex/.Codex/agents/` as stubs | empty |
| `CLAUDE.md:86` / `AGENTS.md:86` | Use `docs/verification-matrix.md` | empty |

`AGENTS.md` self-reference on line 10 resolves; that is not a finding.

## Proposed change

Pick one (maintainer's call):

1. **Restore** the missing guides / dirs this adapter was written for, or
2. **Rewrite** the Source of Truth + Verification sections to name paths that
   actually exist in HorseTrack (or delete the borrowed `ai-workflows/` adapter
   text if this repo is not that product).

I am not attaching a speculative rewrite of your operating model — only the
evidence that the current pointers do not resolve.

## How this was found

Ran [Mountain of Helicon](https://github.com/Morkeeth/mountain-of-helicon)'s
keyless reviewer (`helicon review .`) against a fresh clone, then re-checked
every path with `git ls-files`. A naive backtick→`ls-files` script found the
same 16 broken pointers.

Happy to close if those files live on another branch / submodule you intend —
point me at it and I will re-run.
````

## Local patch sketch (optional; Oscar decides whether to include)

If opening as a code PR rather than an issue-shaped PR, the minimal honest edit is
to replace the Source of Truth bullets with paths that `git ls-files` returns, or
to delete the adapter block until the guides exist. Do **not** invent
`MASTER_GUIDE.md` content for them.

---

## Next stranger PRs (ambitious spine — Oscar clicks)

Re-verify each at **current** default HEAD before pasting. August TRUE rows that
are still the strongest sendables after hand review:

| # | Repo | Claim to re-probe | First command |
|---|------|-------------------|---------------|
| PR-02 | `Strategic-Cowork-Consulting/confidence-routed-extraction` | `CLAUDE.md:136` → `api/exceptions.py` | `git ls-files -- api/exceptions.py` |
| PR-03 | `jorgejr568/organizze-mcp` | `AGENTS.md:198` → `openapi.yaml` | `git ls-files -- openapi.yaml` |
| PR-04 | `myadmin-plugins/mail-module` | `CLAUDE.md:109` → `CALIBER_LEARNINGS.md` | `git ls-files -- CALIBER_LEARNINGS.md` |
| PR-05 | `pvieito/CodeSignKit` + `pvieito/XCTestKit` | `CLAUDE.md:9` → `README.md` (symlink / missing) | `git ls-files -- README.md` |

Do not open these from an agent. Clone → `helicon review .` → hand-check every
row → paste. If Helicon disagrees with a two-hour naive backtick baseline, treat
that as our bug (it did on HorseTrack tonight before the negation fix).

## Agent checklist

- [x] Draft only — no `gh pr create` against HorseTrack
- [x] SHA and `git ls-files` re-derived on a fresh clone
- [x] Numbers not copied from `docs/agent-context-verification-2026-08-09.md` without re-run
