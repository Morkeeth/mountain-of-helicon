# hack.md — HELICON-S2 subtraction ship (help groups)

## NORTH STAR

A stranger runs `helicon --help` and immediately sees **one reason to install**: find which agent documents are lying, with evidence, before work starts (`helicon truth`).

## PROMISE LINE

**GET:** Grouped CLI help — Verify · Lab · Harness — with `truth` first under Verify and a one-line product sentence at the top.

**CONSTRAINT:** No subcommand deleted; no PyPI publish; outward acts are Oscar's click.

## OPEN QUESTIONS

- **BLOCKING:** none for this slice (grouping is copy/UX only per `docs/SUBTRACTION-MEMO.md`).
- **NON-BLOCKING:** Which ungrouped commands deserve a fourth group later (79 total; only 12 grouped tonight).

## CONSTITUTION

1. Run it, do not read it — every checkbox needs the command that proved it.
2. Re-derive numbers at the object (`pytest -q`, `launch_check.py`), never carry figures from prompts.
3. Minimal diff in `helicon/cli.py` (subparsers/help only).
4. Do not delete subcommands, reorganise the repo, or publish to PyPI.
5. Report SHIPPED / VERIFIED / WRONG; WRONG is mandatory.

## PLAN

1. **Slice 1 (NOW):** Help groups + product one-liner + launch receipt S2 section + launch_contract pytest. *Risk: argparse has no native subcommand groups — custom formatter must not break existing commands.*
2. Slice 2: README ≤400 lines with truth → witness → review path only (deferred).
3. Slice 3: PyPI description matches README lead (Oscar gate, deferred).

## NOW

**Slice 1 only:** Add Verify/Lab/Harness labels in `helicon/cli.py`; product sentence from SUBTRACTION-MEMO at top of `--help`; append S2 before/after to `docs/HELICON-LAUNCH-RECEIPT-2026-09-01.md`; run `python3 -m pytest tests/test_launch_contract.py -q` and `python3 scripts/launch_check.py`.

**Done when:**
- `helicon --help` shows Verify group with `truth` as first listed command
- receipt updated with before/after `helicon --help | head -20`
- launch_check READY; launch_contract pytest count logged

## LOG

- 2026-08-31: Pulled `origin/main` (d7b0853); `hack.md` did not exist — wrote contract before code.
- 2026-08-31: S2 shipped — `_HeliconArgumentParser` groups Verify/Lab/Harness in `helicon/cli.py`; receipt S2 section appended.
- 2026-08-31: `python3 scripts/launch_check.py` → READY; `TMPDIR="$HOME/pytmp" python3 -m pytest tests/test_launch_contract.py -q` → 8 passed.
- 2026-08-31: First `helicon --help` failed — `HelpFormatter.add_usage()` missing `groups` on Py3.12; fixed with `self._mutually_exclusive_groups`.
