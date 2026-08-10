# Mountain of Helicon — agent brief

## What this repo is

**Mountain of Helicon** is the external product: a governance and memory-integrity layer for AI agents.

It is **not** Mount Helicon. `MorkeethHQ/mount-helicon` is a **frozen hackathon submission** under judging until 2026-08-17 — a separate repository, write-blocked at GitHub. Never push to it, never open a PR against it, never assume the two share code state. "Helicon V2" and "helicon-v2" are dead names for this repo; use **Mountain of Helicon**.

## How to verify your work

The test suite is **self-contained** — no config file, no seeded database, no API keys required. It creates what it needs in temp fixtures.

```bash
python3 -m pytest -q
```

**Baseline as of 2026-07-29: 526 passed, 0 failed, 1 warning.** If you introduce a failure, the work is not done.

An earlier version of this file claimed `464 passed, 1 failed` and called `tests/test_watch.py::test_alias_drift_flips_r4` "pre-existing, unrelated". That was wrong in a way worth recording, because it would have produced a false report from exactly the cloud VM this file was written for. The test was not flaky and not unrelated: `helicon/aliases.py:code_refs` defaulted to `repos_dir="~/CODE"`, so R4's code arm walked the author's home directory (37 repos, a `git ls-files` each) in production *and* under pytest. On his machine that scan put R4 in `ROT FOUND` before the test's dead-name cube was inserted, so the flip the test asserts could never fire. On a bare VM with no `~/CODE` the same test passes — an agent would have reported the failure "fixed" without touching a line. Proven: `HOME=<empty tmp> pytest tests/test_watch.py::test_alias_drift_flips_r4` → 1 passed in 0.53s; real HOME → FAILED in 6.25s. The arm is now config-declared (`aliases.repos_dir`), unset means unmeasured and says so, and Helicon's own checkout is excluded from its own scan.

**The lesson generalises: a test whose result depends on the machine is not a baseline.** If a failure looks environmental, prove it by changing the environment, not by labelling it.

A green suite is **not** evidence a feature works. Probe the running thing: a 200 is not a render, and pushed is not deployed.

## Building the dashboard

The Python API needs no build. The web dashboard does:

```bash
cd web && npm install && npm run build   # -> web/dist
```

`web/dist` is build output and is **not** committed. It used to be — 52 files,
7.6 MB — because `.gitignore` said `/dist/`, which is root-anchored and never
matched `web/dist/`. The justification was "so a fresh clone renders without a
build step", but the tracked bundle's last commit was 2026-07-23 while `web/src`
had moved to 2026-07-26: a fresh clone served a three-day-old dashboard while
the code claimed it was current. `helicon serve` now returns a 503 naming the
build command when nothing is built, and the API stays up either way.

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
- **Test suite: run with `TMPDIR` outside `/tmp`.** Two tests in `tests/test_stackwatch.py` (`test_dead_path_is_a_finding_ephemeral_is_not`, `test_stack_scan_files_once`) hard-code the ephemeral prefix `('/tmp/',)`. Pytest's default `tmp_path` lives under `/tmp/pytest-of-…`, so those tests see every fixture path as "ephemeral" and file 0 findings → 2 spurious failures. Run `TMPDIR="$HOME/pytmp" python3 -m pytest -q` for a fully green suite (**675 passed** as of 2026-08; run it, do not trust this number — it is the one figure in this file that goes stale fastest). With a proper TMPDIR the `test_watch.py::test_alias_drift_flips_r4` failure noted above does not reproduce.
- **`helicon demo` is the working keyless path.** It is self-configuring, builds `web/dist` on first run when npm is available, seeds 19 labelled planted memories under `~/.helicon/demo`, and opens the Rulings URL on localhost. It never reads personal connectors or writes demo state into the checkout/site-packages.
- **Frontend dev server.** `cd web && npm run dev` serves Vite on :5173 and proxies `/api` → `http://127.0.0.1:8420` (override with `HELICON_API`). It needs the backend (above) running for data. **`web/dist` is NOT committed** (de-tracked in `67310db` — the bundle was three days stale, 52 files / 7.6 MB) and is gitignored, so the backend alone serves nothing: run `cd web && npm run build` first, or use the Vite dev server. Never commit `web/dist`.
- Live connectors, Qwen model calls, and embeddings still require the author's `config.json` / API keys and cannot run in this VM (see above).

## The web build is a build artifact — never commit it

`web/dist/` is gitignored. It is generated, not source. PRs are **source-only**: edit `web/src/**`, never `web/dist/**`. Rebuild locally when you need the backend to serve the compiled dashboard:

```bash
cd web && npm ci && npm run build   # writes web/dist/ (untracked)
```

The FastAPI backend serves `web/dist/` when present and otherwise falls back to the SPA route, so a missing `web/dist/` only means the prebuilt UI is not served — run `npm run dev` (Vite on :5173, proxies `/api`) for live frontend work. Deployment/CI is responsible for building `web/dist/`; a committed copy only drifts from source.
