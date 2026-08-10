# Mountain of Helicon — founder + Claude review packet

## Review outcome requested

Decide whether the launch-hardening branch should merge, and settle four
founder-controlled gates:

1. Make `Morkeeth/mountain-of-helicon` public after merge?
2. Publish the first distribution as `mount-helicon` or
   `mountain-of-helicon`?
3. Omit the stale HTTP ECS demo or replace it with a current HTTPS deployment?
4. Approve the launch claim and warning-by-default posture?

Recommended answers: **yes; `mountain-of-helicon`; omit until replaced; yes.**

## Fifteen-minute review order

1. Run the machine receipt:

   ```bash
   python3 scripts/launch_check.py
   python3 scripts/launch_check.py --online
   ```

   The first command must pass. The online command is expected to block while
   the repository remains private; PyPI is informational until the distribution
   name is chosen.

2. Read only these documents, in order:

   - `README.md` through “What ships”
   - `DEMO.md`
   - `LAUNCH_ROADMAP.md`
   - `LAUNCH_KIT.md`

3. Inspect the high-risk implementation seams:

   - `helicon/cli.py::_ensure_demo_dashboard`
   - `helicon/demo.py::_demo_root` and `ensure_demo`
   - `helicon/config.py::load_config`
   - `.github/workflows/memory-ci.yml`
   - `scripts/judge-check.sh`

4. Run the clean-clone acceptance:

   ```bash
   bash scripts/judge-check.sh --full
   ```

5. Review the diff by intent:

   ```bash
   git diff --stat main...HEAD
   git log --oneline main..HEAD
   ```

## What changed

| Area | Before | Now |
|---|---|---|
| Product identity | Mount/Mountain and two repositories mixed | Mountain + one product repository on launch surfaces |
| Doorway promise | Docs said “refused”; runtime warned | Warning default stated everywhere; block explicit opt-in |
| Public evidence | Broad memory/control-plane pitch | Hand-verified 6/577 repos (1.04%); 9/30 finding precision |
| Terminal demo | Worked, but copy contradicted behavior | Deterministic sweep → warning → recorded reason |
| Visual demo | Fresh clone crashed on stale config, then lacked bundle | Dynamic config, on-demand frontend build, writable demo home, direct Rulings URL |
| CI | Report-only memory exam | Python 3.10/3.12, frontend, package, memory exam |
| Release proof | Manual reconstruction | Executable launch receipt + clean-clone judge check |

## Claim ledger

| Public claim | Evidence | Status |
|---|---|---|
| 6 of 577 scored repos have a sendable doc-vs-code contradiction | `docs/agent-context-report-2026-08.md` + complete survivor ledger | Supported |
| 9 of 30 mechanical survivors are TRUE | `docs/agent-context-verification-2026-08-09.md` | Supported |
| Doorway warns before work continues | `helicon/doorway.py`, `helicon/cli.py`, terminal demo | Supported |
| Every surfaced path contradiction includes command + stdout | `helicon/probes.py`, report evidence table, demo output | Supported for bound executable probes |
| Keyless terminal demo touches no real Claude settings/store | `scripts/demo.sh` isolated paths and clean run | Supported |
| Visual demo is populated and local-only | `scripts/judge-check.sh --full`, `tests/test_demo_golden.py` | Supported |
| “All memory is true” | No system can prove this | Prohibited |
| “Runs are blocked by default” | Runtime defaults to warn | Prohibited |
| Any superseded corpus rate | Replaced by the 2026-08-09 rerun and full hand review | Prohibited |
| Public hosted service is production-safe | HTTPS/session boundary not shipped | Prohibited |

## Known risks intentionally not hidden

- Repository visibility is founder-controlled and currently blocks public clone.
- PyPI is not published; distribution name is unsettled.
- Hosted dashboard auth/TLS is a later gate; launch is local-first.
- Finding precision is 0.30 after the mechanical fixes; the repo-level verified
  1.04% rate is the launch headline.
- The broad Truth/Continuity/Direction/Reflection/Calm vision is not the v0.1
  product promise.
- The dashboard has deep Lab surfaces; the launch journey uses only Rulings.

## Claude review prompt

Copy this exactly after checking out the branch:

> Act as a skeptical open-source launch reviewer. Do not praise the ambition.
> Verify whether a stranger can understand, install, run, and trust the narrow
> launch claim. Read `README.md`, `DEMO.md`, `LAUNCH_ROADMAP.md`,
> `LAUNCH_KIT.md`, and `REVIEW_PACKET.md`. Run
> `python3 scripts/launch_check.py`, the focused launch tests, and
> `bash scripts/judge-check.sh --full`. Inspect the source behind every public
> number and the warning-vs-block behavior. Return only:
> (1) P0 blockers that make the tweet false or the first run fail,
> (2) P1 credibility risks,
> (3) claims that are adequately supported,
> (4) the smallest edits required before merge,
> (5) a GO / NO-GO verdict. Treat private-repo visibility, PyPI naming, and
> deployment as founder decisions, not code failures. Cite exact files.

## Merge checklist

- [ ] Machine receipt passes offline.
- [ ] Clean-clone judge check passes.
- [ ] Release-gate CI is green.
- [ ] No stale identity or frozen repository link on launch surfaces.
- [ ] Founder accepts warning-by-default language.
- [ ] Founder settles public visibility and package name.
- [ ] Final Claude review returns GO or names bounded edits.
