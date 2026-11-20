# PUSH-BLOCKER · 2026-09-01 · `~/CODE/helicon`

**Remote:** `origin` → `https://github.com/MorkeethHQ/mount-helicon.git`  
**Branch:** `cloud/agents-md-2026-08-29` (also `main` +3 vs origin)

## Step 1 — read commands (paste)

```bash
$ git remote -v
origin  https://github.com/MorkeethHQ/mount-helicon.git (fetch)
origin  https://github.com/MorkeethHQ/mount-helicon.git (push)
product https://github.com/Morkeeth/mountain-of-helicon.git (fetch)
product https://github.com/Morkeeth/mountain-of-helicon.git (push)

$ git status
On branch cloud/agents-md-2026-08-29
Your branch is up to date with 'product/cloud/agents-md-2026-08-29'.
nothing to commit, working tree clean

$ git log origin/main..HEAD --oneline
170a193 docs: C1 blocked receipt — mount-helicon FROZEN, cloud cannot push.
e8dc2eb docs: AGENTS.md — MCP vs REST for agent integrators
128de40 Land the working tree: work that existed only on this disk, and ignore the junk.
4921168 Add BUILD-PLAN-2026-08-29 — C1 export stub is cloud lane target.
2e37812 fix: hackathon wins 9 → 10 per prize-ledger.md
```

**5 commits** unpushed to `origin/main`. (Not 40 — that was branch depth; unique delta is 5.)

## Step 2 — personal-data scan

```bash
git diff origin/main..HEAD | rg -i 'journal|finance|wallet|vault'
```

**Result:** prose-only hits in `QUICKSTART.md` and `prize-ledger.md` (examples + “synced from vault …” attribution). **No journal/finance/wallet/vault file paths in the diff.** Safe to push on content grounds.

## Step 3 — push attempt

```bash
git push -u origin cloud/agents-md-2026-08-29
```

```
remote: error: GH013: Repository rule violations found for refs/heads/cloud/agents-md-2026-08-29.
remote: - Cannot create ref due to creations being restricted.
 ! [remote rejected] cloud/agents-md-2026-08-29 -> cloud/agents-md-2026-08-29 (push declined due to repository rule violations)
```

```bash
git push origin main
```

```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - Cannot update this protected ref.
 ! [remote rejected] main -> main (push declined due to repository rule violations)
```

**Blocker:** GitHub rulesets on `MorkeethHQ/mount-helicon` — all branch creation and updates blocked (FROZEN hackathon submission).

## ONE command that clears it

Unfreeze rulesets (Oscar only):

```
open https://github.com/MorkeethHQ/mount-helicon/rules
```

Then:

```bash
cd ~/CODE/helicon && git push -u origin cloud/agents-md-2026-08-29
```

## Already landed (product repo — correct remote)

Work is **not stranded** on the product tree:

| Remote | Branch | Status |
|--------|--------|--------|
| `product` | `cloud/agents-md-2026-08-29` | pushed 2026-09-01 |
| `Morkeeth/mountain-of-helicon` `main` | merged `169a580` | `docs/AGENTS.md` + BUILD-PLAN on main |

**Do not push harness work to `mount-helicon`.** Use `mountain-of-helicon` only.
