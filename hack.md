# hack.md — WAVE 2026-09-04 · Verify-first + HorseTrack spine

## NORTH STAR

A stranger runs `helicon --help`, sees **Verify** first, and has one paste-ready PR that proves a real repo's agent docs lie — with commands, not vibes.

## PROMISE LINE

**GET:** Launch receipt (2026-09-04) proving Verify-first help + green launch_contract, plus `docs/PR-01-HORSETRACK-READY.md` Oscar can paste (no PR opened from this agent).

**CONSTRAINT:** No PyPI upload; no foreign-repo PR open; no Show HN; no broad ROADMAP rewrite. Outward acts are Oscar's click.

## OPEN QUESTIONS

- **BLOCKING:** none for this slice (Verify grouping already on `main`; work is verify + receipt + draft + gate rot).
- **NON-BLOCKING:** Whether Oscar pastes the HorseTrack PR tonight; which second stranger repo is PR-02.

## CONSTITUTION

1. Run it, do not read it — every checkbox needs the command that proved it.
2. Re-derive numbers at the object (`helicon --help`, `launch_check.py`, `pytest`, live HorseTrack clone). Never carry August corpus counts from docs.
3. Never tick a done-when whose command did not execute.
4. Do not open PRs on foreign repos; do not `twine upload`; do not push public beyond this product branch/PR.
5. Report SHIPPED / VERIFIED / WRONG; WRONG is mandatory.
6. Ambition = open the bigger object + baseline arm that can beat us + something a stranger can use.

## PLAN

1. **Slice 1 (NOW):** Confirm Verify-first help at object; fix launch_contract blockers found by running (package-metadata string rot + anyio collection); re-clone HorseTrack and run `helicon review` vs naive baseline; write `docs/HELICON-LAUNCH-RECEIPT-2026-09-04.md` + `docs/PR-01-HORSETRACK-READY.md`. *Risk: findings from August may be dead or false after pointer precision work — must re-verify at HEAD.*
2. Slice 2 (deferred): README ≤400 lines truth→witness→review path only.
3. Slice 3 (Oscar gate): PyPI description / upload.

## NOW

**Slice 1 only** — Verify-first receipt + HorseTrack paste draft + launch gates green at object.

**Done when:**
- [ ] `helicon --help | head -25` shows Verify group with `truth` first (command logged in receipt)
- [ ] `python3 scripts/launch_check.py` → READY
- [ ] `TMPDIR="$HOME/pytmp" python3 -m pytest tests/test_launch_contract.py -q` green (count re-derived)
- [ ] `docs/HELICON-LAUNCH-RECEIPT-2026-09-04.md` exists with commands run
- [ ] `docs/PR-01-HORSETRACK-READY.md` is paste-ready; no foreign PR opened
- [ ] HorseTrack findings re-derived at current default SHA (not carried from 2026-08-09 ledger)

## LOG

- 2026-09-03 night: Read prior `hack.md` (S2 already shipped). Ran first-step: Verify-first **already present** on `main`. `launch_check.py` → **BLOCKED** on `package-metadata` (`"Mountain of Helicon"` missing from `pyproject.toml` since `747a550`). `test_launch_contract` 2 failed / 6 passed. Full `pytest -q` interrupted: 5 collection errors from `anyio.abc.BlockingPortal` DeprecationWarning under `error::DeprecationWarning`.
- 2026-09-03 night: Rewrote this contract for WAVE 2026-09-04 before further code.
