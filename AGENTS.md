# Mountain of Helicon — agent brief

## What this repo is

**Mountain of Helicon** is the external product: a governance and memory-integrity layer for AI agents.

It is **not** Mount Helicon. `MorkeethHQ/mount-helicon` is a **frozen hackathon submission** under judging until 2026-08-17 — a separate repository, write-blocked at GitHub. Never push to it, never open a PR against it, never assume the two share code state. "Helicon V2" and "helicon-v2" are dead names for this repo; use **Mountain of Helicon**.

## How to verify your work

The test suite is **self-contained** — no config file, no seeded database, no API keys required. It creates what it needs in temp fixtures.

```bash
python3 -m pytest -q
```

**Baseline as of 2026-07-28: 470 passed, 0 failed.** If you introduce a failure, the work is not done.

An earlier version of this file claimed `464 passed, 1 failed` and called `tests/test_watch.py::test_alias_drift_flips_r4` "pre-existing, unrelated". That was wrong in a way worth recording, because it would have produced a false report from exactly the cloud VM this file was written for. The test was not flaky and not unrelated: `helicon/aliases.py:code_refs` defaulted to `repos_dir="~/CODE"`, so R4's code arm walked the author's home directory (37 repos, a `git ls-files` each) in production *and* under pytest. On his machine that scan put R4 in `ROT FOUND` before the test's dead-name cube was inserted, so the flip the test asserts could never fire. On a bare VM with no `~/CODE` the same test passes — an agent would have reported the failure "fixed" without touching a line. Proven: `HOME=<empty tmp> pytest tests/test_watch.py::test_alias_drift_flips_r4` → 1 passed in 0.53s; real HOME → FAILED in 6.25s. The arm is now config-declared (`aliases.repos_dir`), unset means unmeasured and says so, and Helicon's own checkout is excluded from its own scan.

**The lesson generalises: a test whose result depends on the machine is not a baseline.** If a failure looks environmental, prove it by changing the environment, not by labelling it.

A green suite is **not** evidence a feature works. Probe the running thing: a 200 is not a render, and pushed is not deployed.

## What needs real credentials (and therefore cannot be verified in this VM)

- `config.json` is gitignored and absent here. Anything reading it — live connectors, Qwen model calls, embeddings — cannot run.
- The real memory store (~47 MB) lives only on the author's machine.

If a task depends on either, **stop and say so** rather than mocking it and reporting success. Claiming a verified result that was never probed is the single worst failure mode in this repo.

## Conventions

- Never `git add -A`. Stage the files you actually changed, by name.
- Check `git branch --show-current` before branching, and branch from an explicit base.
- No secrets in code, ever. This repo is gitleaks-clean across all 326 commits; keep it that way.
- Python ≥3.10. Web is Vite + React in `web/`.
