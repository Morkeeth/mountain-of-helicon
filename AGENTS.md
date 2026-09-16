<!-- STATE:start -->
## SHARED WORK STATE · revision f9668a635a34 · rendered 2026-09-16 · scope repo mountain-of-helicon
This repo's rows of the one shared work state. Authorities: todo.md (human), TASKS.yaml (ids), board clocks, Oscar's rulings (local only). Views such as GLANCE, SLASK and ZUP are adapters over the same revision.
**A CLOSED task stays closed. Do not requeue, re-verify or re-poll it.**
Before acting, record that you read this revision, exact session and exact rev: `python3 ~/CODE/fleet-ops/state/state.py ack --session <your session id> --consumer <claude|codex|cursor> --rev f9668a635a34`. In a cloud sandbox instead append `{"session":"<your session id>","consumer":"<claude|codex|cursor>","rev":"f9668a635a34","ts":"<iso>","stage":"acknowledged"}` to `.fleet/ACK.jsonl` in this repo and commit it.

### CLOSED. Not open work.
- **HELICON-DISTRIBUTION-NAME** · Helicon: rule the distribution name · **COMPLETED**. by Oscar's ruling (held local-only)

### OPEN
- **SEP15-QUEUE-HELICON** · Sep15 Helicon correction transfer (queued) · owner agent · `mountain-of-helicon` · due 2026-09-15T20:00
  - next: Reuse existing correction owners after weirdMD or free slot.
- **HELICON-FIX-DELTA-2026-09-07** · Helicon, learn from the fix delta · owner agent · `mountain-of-helicon`
  - next: Build one real draft → sent event: show the word delta, inferred reason, confidence, authority, and proposed change to the next similar draft.
- **HELICON-NEXT** · Helicon, next ship slice · owner agent · `mountain-of-helicon`
  - next: Continue truth/rot work on main; merge or discard stale cursor/verify-first-receipt if still useful

### RULINGS AND FACTS, each with the object it was read from
- Merge conflicts resolve toward the latest decision, never back to a stale branch. Order by merge time and Oscar's most recent word, not by which lane opened first. Applied 16 Sep: PR 30 deliberate audience choice kept over PR 26 default private. · Oscar in Claude terminal 2026-09-16 10:1x, session 37d93bc8 · 2026-09-16
- Timestamp discipline. Every time hand-written by the orchestrator in today's RUN, coordination file and SLASK entries ran two to three hours ahead of this machine. Machine clock read 10:22 +0200 when the prose said 14:3x. Caught by the ZUP lane, which refused to reconcile two time sources silently because staleness is a subtraction of two times. Rulings in rulings.jsonl are machine-stamped by state.py and were always correct. Corrected in place and recorded rather than quietly fixed. Standing rule: a time in prose is a measurement, so read the clock or write unverified. Do not carry a time forward from an earlier document. · ZUP architecture lane, machine date verified by orchestrator morkeeth-a9 2026-09-16 10:22:33 +0200 · 2026-09-16
- Rulings do not reach the machines that do the work unless they are explicitly allowlisted, and the default is not to ship them. state.py rule takes a --git-ok flag described as allowlisting a ruling's text for repo AGENTS.md blocks, and without it a ruling reaches the local dashboards and nothing else. Proven on the STRIVE naming ruling of 2026-09-16 09:22: present 3 times in rulings.jsonl and 10 times in the rendered state, present zero times across all 36 repo instruction blocks including agentgrinder-public which is the repo it governs, and zero times in all six enabled cloud routine prompts. An agent that opens the governed repo and reads that repo's instructions cannot learn the product's name, that the old name was rejected, or that the sibling repo is off limits, while every local surface shows the ruling present and correct. Three distinct stranding mechanisms exist and each needs a different fix: a remote prompt never updated from a local ruling, a local renderer that requires opt-in per ruling, and a local mirror of a remote object going stale with no signal. The third is illustrated by the file that documents mirror drift in its own words having itself drifted, claiming the routine runs version 6 while it runs version 7. STANDING CONSEQUENCE: every ruling that names a repo or a surface is issued with --git-ok unless there is a stated reason not to, and a ruling is not applied until the executor can read it. · Stranded rulings sweep, 2026-09-16, four rulings with a named executor tested at the object · 2026-09-16
- STRIVE is the public name of the product in Morkeeth/agentgrinder-public. Tagline: Post your strides. Pacecard is rejected and must not appear in new user-visible copy. NEVER touch Morkeeth/agentgrinder, which is a frozen hackathon entry. Internal identifiers are deliberately NOT renamed: the package agentgrinder, the CLI command, the python module paths and the database schema strava all stay. The brand string lives in one place, server/brand.mjs, and the build fails if a placeholder token survives into the output. Issued as a standing fact rather than against a task, because a ruling attached to a task stops rendering into repo instruction blocks the moment that task closes, which is how this ruling disappeared from the repo it governs within hours of being made. · Grok Bot handover pasted by Oscar 2026-09-16, confirmed by him directly when asked; re-issued as a fact 11:5x after two stranding mechanisms were found · 2026-09-16
- Third stranding mechanism, found while fixing the second. A ruling carrying a --tasks id is excluded from the repo instruction blocks entirely: state.py builds that section from rulings with NO tasks field, and a task-attached ruling renders only inside its task row, which disappears when the task closes. So closing a task strands every ruling attached to it. The STRIVE naming ruling was attached to PACECARD-NAME, that row was closed the same day, and the name of the product vanished from the repo that contains the product within hours of being ruled. Two consequences. A durable ruling that must reach an executor is issued as a FACT with no task id, and --tasks is for rulings that only matter while the work is open. And the render population itself was wrong: repo targets are read from a hand-maintained registry file and only entries carrying a lane are rendered, so agentgrinder-public, bout, kill-motor and fika-eval were absent entirely while world-relay, waveradio-archive and weirder-md had no lane. Six of the seven repos worked in today received no state at all. Fixed: all seven added or given a lane, render targets 19 to 26, check findings 63 to 44. · Orchestrator morkeeth-a9, state.py line 224 read and the registry file measured, 2026-09-16 · 2026-09-16
- An invariant that names its own switch as its gate cannot be violated, only disabled, and that is how a security property sat broken for months while the code stayed conformant by definition. FAVOUR invariant 4 asserted that identity MUST be proven and not claimed, then named the enforcement environment variable as its gate. Since the variable ships off, the invariant was satisfied by its own terms while an unauthenticated request reached the store. Rewritten so the invariant states the PROPERTY, the switch is an implementation detail that can only record non-conformance rather than redefine it, and conformance is recorded as NOT MET in production with the evidence beside it. Until fixed it reads as violated rather than as configured. General form: if a rule can be satisfied by changing a setting rather than by changing behaviour, it is not a rule. Related practice from the same lane: one guard test deliberately asserts the CURRENT permissive behaviour, so it changes colour the day the defect is fixed. A test that documents a known defect is more honest than a comment, because a comment cannot go red. · FAVOUR identity gate lane, 2026-09-16 · 2026-09-16

### ACKNOWLEDGED THIS REVISION: nobody yet
<!-- STATE:end -->

# Mountain of Helicon — agent brief

## What this repo is

**Mountain of Helicon** is the external product: a governance and memory-integrity layer for AI agents.

It is **not** Mount Helicon. `MorkeethHQ/mount-helicon` is a **frozen hackathon submission** under judging until 2026-08-17 — a separate repository, write-blocked at GitHub. Never push to it, never open a PR against it, never assume the two share code state. "Helicon V2" and "helicon-v2" are dead names for this repo; use **Mountain of Helicon**.

## Memory journey — user direction, 6 September 2026

Capture history, context and memory, and show how they work together. A user must
be able to inspect why a belief exists, its exact source and observation time,
what correction superseded it, and which consumer received that source revision.
Read/delivery, acknowledgment and observed behavior are different evidence states.
Do not infer behavior from an ACK or causality from a reviewed artifact. Reuse the
existing stores; keep private source text on the explicit loopback review boundary.
ZUP owns next actions; Helicon owns this inspectable history.

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
- Live connectors, Qwen model calls, and embeddings still require the author's `~/.helicon/config.json` (see `helicon/config.py`) / API keys and cannot run in this VM (see above).

## The web build is a build artifact — never commit it

`web/dist/` is gitignored. It is generated, not source. PRs are **source-only**: edit `web/src/**`, never `web/dist/**`. Rebuild locally when you need the backend to serve the compiled dashboard:

```bash
cd web && npm ci && npm run build   # writes web/dist/ (untracked)
```

The FastAPI backend serves `web/dist/` when present and otherwise falls back to the SPA route, so a missing `web/dist/` only means the prebuilt UI is not served — run `npm run dev` (Vite on :5173, proxies `/api`) for live frontend work. Deployment/CI is responsible for building `web/dist/`; a committed copy only drifts from source.


## Governed run receipts (helicon export)

<!-- HELICON-RUN-RECEIPT START -->
### tr_4fdf504db330 · 2026-07-31 · reviewed

**Objective:** wire the doorway gate into a live Claude Code session

```
TaskRun tr_4fdf504db330 — reviewed
  objective:  wire the doorway gate into a live Claude Code session
  context:    0 items in packet, 0 relevant excluded (privacy/scope), ~0 tokens · mode=compact
  outcome:    unverified (source: —)
  egress:     local-only
  context:    packet delivery unproven · 0 ruling delivery record(s) linked to this run · recorded: yes · delivered: unproven · obeyed: unproven
```
<!-- HELICON-RUN-RECEIPT END -->


