# Mountain of Helicon — agent brief

## What this repo is

**Mountain of Helicon** is the external product: a governance and memory-integrity layer for AI agents.

It is **not** Mount Helicon. `MorkeethHQ/mount-helicon` is a **frozen hackathon submission** under judging until 2026-08-17 — a separate repository, write-blocked at GitHub. Never push to it, never open a PR against it, never assume the two share code state. "Helicon V2" and "helicon-v2" are dead names for this repo; use **Mountain of Helicon**.

## How to verify your work

The test suite is **self-contained** — no config file, no seeded database, no API keys required. It creates what it needs in temp fixtures.

```bash
python3 -m pytest -q
```

**Baseline as of 2026-07-28: 464 passed, 1 failed.**

The one known failure is `tests/test_watch.py::test_alias_drift_flips_r4` — pre-existing, unrelated to any new work, and tracked. If your change makes it pass, say so explicitly. If you introduce a *new* failure, the work is not done.

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

## The web build is a build artifact — never commit it

`web/dist/` is gitignored. It is generated, not source. PRs are **source-only**: edit `web/src/**`, never `web/dist/**`. Rebuild locally when you need the backend to serve the compiled dashboard:

```bash
cd web && npm ci && npm run build   # writes web/dist/ (untracked)
```

The FastAPI backend serves `web/dist/` when present and otherwise falls back to the SPA route, so a missing `web/dist/` only means the prebuilt UI is not served — run `npm run dev` (Vite on :5173, proxies `/api`) for live frontend work. Deployment/CI is responsible for building `web/dist/`; a committed copy only drifts from source.
