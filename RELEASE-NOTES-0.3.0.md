# Mountain of Helicon 0.3.0

Covers the work merged since 0.2.4 (bump on 26 Sep 2026, on PyPI since 2 Oct 2026).
The git history was rewritten on 11 Oct 2026 to remove generated state blocks and internal
review material. Tags v0.2.2 to v0.2.4 were made on the old history and are not on this one.
v0.3.0 is the first tag on the current history.

## New

- `helicon start`: one first-run card for the whole agent setup. It reads instructions,
  memory notes, saved decisions, skills, the session index, scheduled jobs and spend, in plain words.
  - `--html` writes the card as one local page. `--share` prints counts and rates only.
  - `--line` prints one saved sentence, so a session-start hook costs nothing.
  - It says which copy of Helicon is running and how far it is behind main.
  - New in this release: when the running copy shares no history with main (after a rewrite),
    it says to install again from main. Before, it said "726 updates behind" and gave a
    `git pull` that cannot work.
- `helicon ask` reads the operator's dated rulings, newest first, and marks the current one
  by subject. A private ruling never reaches an agent, and an older public ruling is not shown
  as current when a newer private one exists. Retired or expired notes are labelled as history.
- `helicon followed`: instruction paths an agent followed and failed to open (#45).
- Cross-harness context check-in (#43).
- Rules and hooks are stored as memory items, so `ask` can say which rule a hook enforces.
- `proof/at-scale-1000/`: 1,000 unattended agent runs on frozen public repositories, with the
  frozen list, the per-run rows and `verify.py`, which rechecks every published number.
  The checker in that run is a GitHub Action pin check. It tests the evaluation method at scale.
  It is not a run of `helicon review`.

## Changed

- The model layer is provider-neutral (`helicon.llm`). Any OpenAI-compatible endpoint, set with
  `llm_base_url`, `llm_model` and `llm_api_key`. No default vendor. `helicon.qwen` stays as a shim.
  The response cache table is now `llm_cache`, with a migration.
- Unknown model cost is reported as unknown. Prices come from config.
- `scripts/truth-daily.sh` runs with the Python that has Helicon installed and exits 1 when no
  receipt is written. Cron's system Python has no Helicon package.

## Fixed

- `helicon review` on strangers' repos: no flags for library names, naming patterns or monorepo
  scripts. Reads nested `.gitignore` files. Names a missing path instead of a missing AGENTS.md (#42).
- `helicon truth` and `review`: a missing or empty path is not reported as a fresh store.
- Weekday and full date are checked inside one context item (#46).
- A judge that returns no verdict keeps the identity fork (#44).
- A job restarted by hand is not counted as failed (#55).
- The vault scan skips a note that is not on this disk, with a time limit and a warning.
- Python 3.10 accepts browser UTC timestamps.
- `helicon start` runs on a fresh machine with no `~/.helicon/config.json`. Before, the config
  gate sent a stranger to `helicon init` before the first-run card could say anything.
- QUICKSTART listed `helicon witness --latest`. That flag does not exist. It now says `helicon witness`.

Known limits:
- `helicon review` does not read `.clinerules`.
- `uv.lock` still names an old package version. `pip install` is the supported install.
