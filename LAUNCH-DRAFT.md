# Helicon — launch draft

Draft only. Nothing here is posted. Oscar posts. Every copy block below is written
to be pasted as-is (no em dashes, no hype words, claims checkable).

The wedge to lead with everywhere: **every context linter checks that a documented
command is *defined*. Helicon runs it and checks the doc's claim that it *passes* is
still true.** That is the one thing no other tool in this space does.

---

## Before you post — the one blocker

The one-line command depends on the package being on PyPI. It is built and verified
locally but **not published** (that is your call, not the agent's).

Publish command (run once, from the repo root):

```bash
python3 -m build
python3 -m twine upload dist/mountain_of_helicon-0.1.1-py3-none-any.whl dist/mountain_of_helicon-0.1.1.tar.gz
```

Naming decision you need to make first (it changes the one-liner in every post below):

- **Keep the package name `mountain-of-helicon`.** The stranger command is then
  `uvx --from mountain-of-helicon helicon-review <repo>`. Works today, verified.
- **Or reserve the PyPI project name `helicon-review`** (shorter, cleaner for a
  launch). Then the command is `uvx helicon-review <repo>` with no `--from`. This
  needs a second `[project]` name or a separate thin publish; decide before posting.

Everything below is written with the `--from mountain-of-helicon` form because that
is what builds and runs right now. If you reserve `helicon-review`, delete `--from
mountain-of-helicon ` from each command.

Second rough edge, honest: the package pulls openai/fastapi/numpy as install deps, so
the first `uvx` run downloads ~25 packages before the review runs (a few seconds). The
review path itself uses no key and no model. Trimming those to extras is a follow-up,
not a blocker.

---

## (a) Show HN post

Title:

```
Show HN: Helicon runs the commands your CLAUDE.md claims pass, and grades them
```

Body:

```
Every coding agent (Claude Code, Cursor) loads CLAUDE.md / AGENTS.md / .cursorrules
as fact at the start of a session. Those files rot the way config rots: a path moves,
a script is renamed, a build step is retired, and nobody updates the doc. The agent
then acts on the stale line and neither you nor it finds out. The file still reads
authoritative.

There are already linters that catch dead file references and undefined commands
(ctxlint, agents-lint). Helicon does that tier too, but its point is the next one: an
empirical study of 2,303 of these files found 75.9% document a test or build command.
That is the most common instruction type, and it is the one that goes stale silently,
because "reference exists" and "command still passes" are different questions.

Helicon runs the documented command and grades the doc's claim against the real exit
code: UPHELD, CONTRADICTED (with the failing stderr as the receipt), or UNVERIFIABLE.
A CLAUDE.md that says "tests pass with pytest -q" fails the check the day that stops
being true. No linter I could find actually runs the commands.

One line, no clone, no key, no LLM:

  uvx --from mountain-of-helicon helicon-review ~/your-repo

By default it runs the existence and version tier (pointers, command names, "we use
React 18" vs package.json). The execute-and-compare part runs a stranger's code, so it
is opt-in behind HELICON_EXECUTE=1. Every finding names the exact file:line and the
repo fact that contradicts it. Exit code is non-zero when the setup lies, so it drops
into CI.

Honest about where it stands: the existence tier is commoditized and I am behind the
npm-native tools there. The execute-and-compare tier is the reason to look. Code and
the two papers it cites are in the repo. Feedback on the false-positive surface of
running documented commands is what I most want.
```

Verify before posting: the `uvx` command matches your naming decision above; the repo
is public; `~/your-repo` is a placeholder a reader will swap.

---

## (b) awesome-claude-code / awesome-claude-skills — PR list entry

Paste-ready list line (match the target list's exact column format when you open the PR):

```
- [Helicon](https://github.com/Morkeeth/mountain-of-helicon) - Reviews a repo's CLAUDE.md/AGENTS.md against the actual tree: broken pointers, undefined commands, wrong version claims, and (opt-in) runs the documented test/build command to check the doc's "this passes" claim is still true. One line, no key: `uvx --from mountain-of-helicon helicon-review <repo>`.
```

PR body (paste-ready):

```
Adds Helicon, a reviewer for agent context files. Beyond the usual dead-reference and
undefined-command checks, it can run a documented test/build command and grade the
doc's claim that it passes against the real exit code, with the stderr as the receipt.
No key, no LLM for the default tier. Runs in one line via uvx/pipx. MIT licensed.
```

---

## (c) First-screenshot demo command

Run this against a repo with a known-stale reference so the first screenshot shows a
real CONTRADICTED finding with a file:line, not a clean pass:

```bash
helicon review ~/CODE/hack-fleet-ata
```

Current real output (verified 2026-08-25): GRADE C, 10 references checked, 3 broken,
each naming `CONTEXT.md:<line>  points at <file>  — not in this repo`. Colored, ranked,
exit 1. That is the hook frame.

For the execute-and-compare frame (the wedge), point it at a repo whose CLAUDE.md
claims a passing test and flip the switch:

```bash
HELICON_EXECUTE=1 helicon review ~/your-repo-with-a-documented-test
```

That shows the `commands RAN vs their claim` block, which is the one panel no
competitor's output has.
