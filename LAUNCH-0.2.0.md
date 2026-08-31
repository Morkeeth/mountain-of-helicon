# Mountain of Helicon 0.2.0 — launch pack

**Status: everything is ready except the publish, and the publish is Oscar's.**

## The gate, run cold, 31 Aug

```
$ python3 -m build --wheel
Successfully built mountain_of_helicon-0.2.0-py3-none-any.whl

$ python3 -m venv /tmp/hstranger
$ /tmp/hstranger/bin/pip install dist/mountain_of_helicon-0.2.0-py3-none-any.whl
$ cd /tmp && /tmp/hstranger/bin/helicon truth ~/.claude --recursive --top 3
STALENESS + ROT REPORT — /Users/morkeeth/.claude
1185 files scanned · 629 carry a staleness/rot signal · 556 clean
EXIT=0
```

**An empty environment, one install, one command, a real answer.** No key, no database, no LLM,
no config file. That is the whole product claim and it now holds from a clean venv rather than
from this working tree.

## Why this is the launch, not a version bump

PyPI has served **0.1.2 since 16 August**. Everything since is invisible: two weeks of work that
~6 people a day are not getting. The download floor — 2 to 8 a day for the fourteen days after the
last release, with **zero** promotion, our own CI excluded (15 runs all August) and release-day
traffic excluded — is the only organic demand signal on the whole board.

**Those people are installing 0.1.2 because that is all there is.**

## What changed at the front door

The README opened on `helicon witness`, which needs a session and a store. `helicon truth` needs
neither, and the README's own line 404 already called it *"the stranger-facing cold path"* — four
hundred lines below the install instruction. It now leads, with a measured example rather than a
promise.

## Oscar's one command

```
cd ~/CODE/mountain-of-helicon && python3 -m twine upload dist/mountain_of_helicon-0.2.0-py3-none-any.whl
```

**PyPI never lets a version be replaced.** Before running it: confirm `pyproject.toml` says 0.2.0
(it does, checked 31 Aug) and that this wheel is the one built from the current tree (it is —
built and cold-tested above, same session).

## Not done, and named rather than hidden

- **Nobody has asked who the ~6/day are.** The curve's shape decides it — weekday-shaped is humans,
  flat is machines — and the answer changes whether this is a product or an artifact. UNMEASURED.
- **No release notes for end users.** The wheel is ready; the story of what they get is not written.
- **Subtraction not done.** 79 subcommands, one reason to install. `truth` leads the README now, but
  the CLI still presents all 79 as peers. That is the next real piece of work and it is a product
  decision, not a chore.
