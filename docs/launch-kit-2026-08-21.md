# Launch kit — held for Oscar's click, nothing here is sent

*Prepared 2026-08-21. Every block below is paste-ready plain text. Zero placeholders (verified by grep). The clicks that publish anything are yours: make repo public, twine upload, Product Hunt submit.*

---

## 1 · GitHub

Repo description (159 chars):

Did your coding agent actually do what it said? Helicon reads your local agent traces and pairs every claim with its evidence. Local-first, keyless, one command.

Topics (paste into repo settings):

ai-agents, claude, developer-tools, observability, cli, local-first, agent-evaluation, transcripts, coding-agents, python

Pinned-repo tagline (the short one, 56 chars):

Claim vs witness for coding agents. Local and keyless.

## 2 · Product Hunt

Name:

Mountain of Helicon

Tagline (49 chars):

Catch your coding agent lying about what it did

Description (247 chars):

Your agent says "tests pass" and "file updated". Helicon reads the local session trace and pairs every claim with its tool evidence: confirmed, no evidence, or contradicted, with the line cited. Keyless, local-first, first catch in under a minute.

First comment, maker voice (sentence case, no em dashes, every claim checkable):

hi, oscar here. i build with coding agents daily and kept merging things because the agent said "all tests pass". then i checked the traces. some of those claims had no tool call behind them at all.

so i built helicon. it reads the session files already sitting in ~/.claude on your machine, pulls out every checkable claim the agent made, and shows the evidence next to it: confirmed, no evidence, or contradicted, with the exact line cited. deterministic checks run with no key and nothing leaves your machine. if you want the fuzzy prose claims judged too, it calls the claude subscription you already have, locally.

the first thing it caught on my own machine was a planted "i ran the full pytest suite and all tests pass" with zero supporting tool calls. took 38 seconds. it also graded my own setup and failed me on two counts, which felt fair.

pip install mountain-of-helicon and then helicon witness. i would honestly love to see the weirdest claim it catches in your traces.

## 3 · Gallery assets (all real, all committed)

1. artifacts/flipbook-journey.gif (6 real product screens, journey order)
2. The caught-lie terminal block from the README top (screenshot it at post time so it matches the shipped version)
3. /private/tmp scratchpad has setup-1440-final.png + fresh-header.png from tonight; better: retake both from the live app at post time so the header matches the de-Qwened build

## 4 · One-line pitch (friend of a friend, early-tools lists)

Small local tool i built: it reads your coding agent's session traces and shows which of its claims actually have evidence behind them. One command, no key, nothing leaves the machine. Would you run it on your last session and tell me the first thing it catches?

## 5 · Verify-before-send list (yours)

- The stranger command only works after your twine upload of 0.2.0.
- The repo is private today; the star push needs it public first.
- First comment says "planted" for the pytest catch because it was planted (in a copy of a real transcript, as the detector's red test). True as written; do not let anyone edit "planted" out, that would make the claim a lie.
- PH gallery: retake the two app screenshots at post time.
