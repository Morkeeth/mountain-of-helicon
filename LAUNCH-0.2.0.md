# Mountain of Helicon 0.2.0 — launch pack

**Status: integration candidate. Publish remains a separate action.**

## Release gate

```
$ bash scripts/build_release.sh
$ bash scripts/cold_install_check.sh
COLD INSTALL PASS: mountain-of-helicon 0.2.0 reported the planted missing file and did not report the valid file or command.
```

The build script creates the sdist and wheel twice from the same committed
source and compares each pair byte for byte. The cold test installs only the
local wheel into a new virtual environment. It uses an empty home directory,
no config file, and no API key. It then reviews a generated repository.

## Why this is the launch, not a version bump

PyPI has served **0.1.2 since 16 August**. Everything since is invisible: two weeks of work that
~6 people a day are not getting. The download floor — 2 to 8 a day for the fourteen days after the
last release, with **zero** promotion, our own CI excluded (15 runs all August) and release-day
traffic excluded — is the only organic demand signal on the whole board.

**Those people are installing 0.1.2 because that is all there is.**

## What changed at the front door

The README leads with `helicon review .`, which needs no key, database or config.
The installed distribution is `mountain-of-helicon`; the command remains `helicon`.
The README also states the dependencies installed for the other commands.

## Oscar's one command

```
python3 -m twine upload dist/mountain_of_helicon-0.2.0.tar.gz dist/mountain_of_helicon-0.2.0-py3-none-any.whl
```

**PyPI never lets a version be replaced.** Before running it: confirm `pyproject.toml` says 0.2.0
(it does) and check that the artifact hashes match the draft pull request.

## Footer (1 Sep 2026)

```text
$ python3 scripts/launch_check.py
READY: source-controlled gates pass.

$ python3 -m pytest tests/test_launch_contract.py tests/test_new_user_onboarding.py -q
11 passed in 2.70s
```

Oscar gate: `python3 -m twine upload dist/mountain_of_helicon-0.2.0.tar.gz dist/mountain_of_helicon-0.2.0-py3-none-any.whl`
