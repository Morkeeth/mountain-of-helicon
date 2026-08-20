# Contributing

Mountain of Helicon is local-first: everything reads your own machine and
nothing leaves it. Contributions should keep those two properties intact.

## Ground rules

- **Deterministic checks stay keyless.** A check that needs an API key belongs
  in the optional LLM tier, gated and honestly labeled.
- **No fake verdicts.** A check that cannot run reports UNMEASURED with the
  reason. A zero must never render as a pass. This is the product's whole
  point; PRs that soften it will be declined.
- **Fixture first.** New detectors ship with a fixture that includes a case
  the detector must catch AND a case it must not. The witness fixture
  (`tests/fixtures/witness_fixture.jsonl`) is the template — it caught three
  real bugs before the first release.
- **Doc counts are checked.** `helicon ci` runs the rot exam on this repo
  itself; if you add a CLI command, update the counts in README/CLAUDE.md or
  CI fails honestly.

## Quick dev loop

```bash
python3 -m pip install -e .
python3 -m pytest tests/ -q
helicon ci            # the repo audits itself
cd web && npm install && npx vite build
```

Open an issue with the probe output that shows the problem — evidence over
description, same as the tool itself.
