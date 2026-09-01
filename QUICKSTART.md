# Quickstart — is your agent's memory still true?

Your AI coding agent (Claude Code, Cursor, Cline, Copilot) reads a pile of memory
and notes files every session — `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, an
Obsidian vault, a `docs/` folder. Over weeks those files rot: a deadline passes,
a "live" status goes stale, a page says "refresh daily" and nobody did, a project
gets renamed but the old name lingers. Your agent keeps obeying the stale lines.

`helicon truth` points at any folder of `.md` / `.jsonl` files and gives you a
ranked, evidence-cited staleness report in **one command** — no account, no API
key, no LLM, no database. It reads the disk, nothing else. Nothing leaves your
machine.

## Run it (2 minutes)

```bash
git clone https://github.com/MorkeethHQ/mount-helicon.git
cd mount-helicon
pip install -e .

helicon truth ./docs                    # any flat folder of notes / rules files
```

Point it at whatever your agent actually reads:

```bash
helicon truth .                         # this repo's CLAUDE.md / AGENTS.md / docs
helicon truth ~/notes                   # your Obsidian vault or notes folder
helicon truth ~/.claude/projects --recursive   # your Claude Code agent memory
```

Add `--recursive` when the folder has subfolders (it scans one level deep by
default). Add `--top 10` to see only the ten most-rotten. Add `--json` to pipe it
into a script or CI.

## What you'll see

```
STALENESS + ROT REPORT — ./docs
3 files scanned · 2 carry a staleness/rot signal · 1 clean · as of 2026-08-27
Freshest file in store: 2026-08-27. Signals read from disk only — no DB, no key, no LLM.
Signals: stamp-stale · freshness-rule · claims-live-but-stale · retired-but-live · expired-date · superseded-term.
Redaction ON: owner-only/personal file bodies shown as metadata only.

  #  SCORE    AGE  FILE
  ----------------------------------------------------------------------------
  1     30     0d  OUTLINE.md
          +15  expired dated claim (38d past, 2026-07-20)
                └ Deadline:** Jul 20
          +15  expired dated claim (38d past, 2026-07-20)
                └ Deadline: Jul 20
  2     21     0d  ROT.md
          +21  expired dated claim (99d past, 2026-05-20)
                └ by framing alone, replicated May 20
```

Every row cites the exact line it fired on, so you can open the file and fix it
(or delete it) in seconds. High score at the top = fix this first.

## What it looks for

- **stamp-stale** — a `date:` / `updated:` stamp older than the file's own last
  edit: the page changed, its freshness stamp lied.
- **freshness-rule** — the page says "refresh daily / weekly" and nobody did.
- **claims-live-but-stale** — `status: live` on a file edited weeks ago.
- **retired-but-live** — the file says RETIRED / DEPRECATED / PARKED, yet it's
  still on disk and still being loaded.
- **expired-date** — a deadline / freeze date in the body that's now in the past.
- **superseded-term** — an old file still uses a word a newer file bans or
  renamed.

## Privacy

Read-only. It never writes to, edits, or deletes your files. Nothing is sent
anywhere — no key, no network call. Any file that looks personal or is
owner-only (mode 600) is shown as metadata only, so a report you save or paste
never leaks a body. Add `--no-redact` to see everything in your own terminal.

That's the whole tool: point it at your memory, see what's gone stale, fix the
top few. Run it again next week.
