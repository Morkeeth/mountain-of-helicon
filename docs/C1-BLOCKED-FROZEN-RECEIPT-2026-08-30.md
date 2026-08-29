# C1 + AGENTS.md — blocked by repo freeze

**Date:** 2026-08-30 · **Repo:** `MorkeethHQ/mount-helicon` · **Rulesets:** FROZEN (Devpost + all branches)

## Wrong-object correction

Cloud lanes targeted `mount-helicon@main` while GitHub rulesets block **all writes**. Launching cloud here produces work that cannot land — the same class of error as measuring `mountain-of-helicon` instead of the submitted tag.

## Measured at disk (local branch `cloud/agents-md-2026-08-29`)

| Artifact | Local | Remote `main` |
|----------|-------|---------------|
| `docs/AGENTS.md` (16 MCP tools, MCP vs REST) | ✅ `e8dc2eb` | ❌ 404 |
| `helicon export <run-id>` stub | ❌ not in cli.py | ❌ |
| Push branch `cloud/agents-md-2026-08-29` | — | ❌ branch creation restricted |

## What unblocks the lane (Oscar)

1. Lift **FROZEN** rulesets at https://github.com/MorkeethHQ/mount-helicon/rules — or
2. Retarget harness to a writable repo (explicit ruling; not `mountain-of-helicon` without saying so)

## IDE path (no cloud until unfreeze)

```bash
cd ~/CODE/helicon
git checkout cloud/agents-md-2026-08-29   # has docs/AGENTS.md
# implement C1 export stub per BUILD-PLAN-2026-08-29.md
pytest -q
# push when rules allow
```

Harness: `helicon` mode **blocked** in `zup/shared/cloud-harness.ts` until remote receipt exists.
