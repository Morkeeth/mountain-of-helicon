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

## Cursor Cloud specific instructions

Dependencies are refreshed automatically on VM startup (`pip install -e .`, `pip install pytest`, and `npm ci` in `web/`). Standard dev commands live in `CLAUDE.md` (§ Dev Commands) and `web/package.json`. Non-obvious caveats only:

- **CLI is on `~/.local/bin`.** `pip install -e .` installs the `helicon` entry point there, which is not on `PATH` by default. Run `export PATH="$HOME/.local/bin:$PATH"` (or invoke via `python3 -m helicon.cli`).
- **Test suite: run with `TMPDIR` outside `/tmp`.** Two tests in `tests/test_stackwatch.py` (`test_dead_path_is_a_finding_ephemeral_is_not`, `test_stack_scan_files_once`) hard-code the ephemeral prefix `('/tmp/',)`. Pytest's default `tmp_path` lives under `/tmp/pytest-of-…`, so those tests see every fixture path as "ephemeral" and file 0 findings → 2 spurious failures. Run `TMPDIR="$HOME/pytmp" python3 -m pytest -q` for a fully green suite (**465 passed** here). With a proper TMPDIR the `test_watch.py::test_alias_drift_flips_r4` failure noted above does not reproduce.
- **`helicon demo` is blocked by the config gate.** `demo` is not in the `SELF_CONFIGURING` allowlist in `helicon/cli.py`, so with no `config.json` it prints "No config at …" and exits instead of seeding. To run the dashboard keyless: `python3 scripts/demo_seed.py` (seeds `data/helicon-demo.db` + writes `config-demo.json`), then `HELICON_CONFIG=config-demo.json helicon serve` (backend + prebuilt SPA on :8420). This is the working keyless path despite the one-liner in the docs.
- **Frontend dev server.** `cd web && npm run dev` serves Vite on :5173 and proxies `/api` → `http://127.0.0.1:8420` (override with `HELICON_API`). It needs the backend (above) running for data; `web/dist` is committed so the backend alone also serves the UI.
- Live connectors, Qwen model calls, and embeddings still require the author's `config.json` / API keys and cannot run in this VM (see above).
