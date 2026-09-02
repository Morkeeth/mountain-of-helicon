# Quickstart — does your AGENTS.md lie?

Your coding agent reads `AGENTS.md`, `CLAUDE.md`, or `.cursorrules` at the start of
every session. Those files point at paths, name commands, and claim versions. When
the repo moves on, the rules don't — and your agent walks into dead ends nobody
noticed.

`helicon review` checks every pointer and claim against the repo on disk. No API key.
No database. Nothing uploaded.

## Run it (30 seconds)

```bash
pip install mountain-of-helicon
helicon review .                    # the repo you're in
```

Or without installing:

```bash
uvx --from mountain-of-helicon helicon-review /path/to/your-repo
```

## What you'll see

```
  ❄ HELICON  reviewing your-repo

  ✗ Your setup lies to its agent in 2 places.

    ✗ CLAUDE.md:48  points at docs/architecture.md  — not in this repo
    ✗ AGENTS.md:12  runs npm test  — not in this repo

  GRADE D   ·   5 references checked, 2 broken
  An agent that trusts this file walks into 2 dead ends.
```

Every row names `file:line` and what the repo actually has. Exit code is **1** when
something is broken — so you can gate CI on it.

Machine-readable output:

```bash
helicon review . --json
```

## Gate it on every PR

Copy `.github/workflows/helicon-ci.yml` from this repo, or:

```yaml
- uses: Morkeeth/mountain-of-helicon@main
  with:
    path: .
    fail-on: none   # start report-only; use rot when clean
```

## Optional depth

| Command | Question |
|---------|----------|
| `helicon truth <dir>` | Are my notes / agent memory files stale? |
| `helicon witness --latest` | Did the last agent session's claims match the transcript? |
| `helicon ci --path .` | Full rot exam + executable probes (CI-shaped) |

The memory lab (`helicon init`, `helicon scan`, `helicon serve`) is optional — see
[docs/ONBOARDING.md](docs/ONBOARDING.md).
