# Mountain of Helicon 0.2.0 — release notes

**For strangers installing from PyPI today.** You were on 0.1.2 because that was all there was.

## Install

```bash
pip install mountain-of-helicon==0.2.0
helicon truth ~/.claude --recursive --top 5
```

No API key. No database. No config file. Exit code 0 means the report ran; non-zero means contradictions or rot signals were found.

## What changed since 0.1.2

### Front door: `helicon truth`

The README now leads with the command that works from a cold install. It scans agent-rules and memory directories, ranks staleness and rot, and cites the exact line each row fired on.

### `helicon witness`

Point it at your last Claude Code session (or pass a `session.jsonl` path). Every agent claim is checked against the transcript. Rows marked `[NO-EVIDENCE]` are claims the trace cannot support — before you merge.

### `helicon review` / `helicon ci`

Drop into CI with `--fail-on none` first; flip to `rot` after your docs are clean. Grades `CLAUDE.md`, `AGENTS.md`, and sibling rules files against the repo tree.

### Doctor / BYOK path

`helicon init` + `helicon doctor` no longer FAIL on a fresh install when you have not added a Qwen/DashScope key. Remote rerank and semantic search are optional; deterministic probes run keyless.

## What did not change

- No hosted personal-store service — local-first, BYOK for Qwen-judged tiers.
- No automatic PyPI re-publish — versions are immutable once uploaded.
- The frozen hackathon submission repo is separate and untouched.

## Upgrade

```bash
pip install -U mountain-of-helicon==0.2.0
helicon doctor
```

## One-minute demo

```bash
helicon truth . --top 3          # any directory with markdown agent context
helicon witness --latest         # last session, if Claude Code is installed
```

---

Built and cold-tested 31 Aug 2026. See `LAUNCH-0.2.0.md` for the wheel receipt.
