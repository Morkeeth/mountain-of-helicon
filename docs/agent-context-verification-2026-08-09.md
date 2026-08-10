# Agent-context survivor verification — 2026-08-09

Every row below was re-cloned from the current default branch, checked at the
recorded SHA, read in context, and rerun with the exact command. `FALSE` includes
anything arguable or unresolved. No maintainer was contacted.

All probe outputs for these 30 path findings were empty; this is shown explicitly
as `(no output)` rather than omitted.

## Complete ledger

| # | Repo @ SHA | Doc:line | Claim under review | Command | Output | Verdict and reason |
|---:|---|---|---|---|---|---|
| 1 | `hoangtruong01/HorseTrack@3ee8c1f` | `CLAUDE.md:9` | Read `MASTER_GUIDE.md` for the operating model | `git ls-files -- MASTER_GUIDE.md` | `(no output)` | **TRUE** — concrete repository source-of-truth instruction; no file, rename, generator, submodule, or external qualifier |
| 2 | `hoangtruong01/HorseTrack@3ee8c1f` | `CLAUDE.md:11` | Read `PORTABILITY.md` for copy strategy | `git ls-files -- PORTABILITY.md` | `(no output)` | **TRUE** — concrete repository source-of-truth instruction; no file or replacement |
| 3 | `hoangtruong01/HorseTrack@3ee8c1f` | `AGENTS.md:9` | Read `MASTER_GUIDE.md` for the operating model | `git ls-files -- MASTER_GUIDE.md` | `(no output)` | **TRUE** — active second agent surface repeats the missing concrete guide |
| 4 | `hoangtruong01/HorseTrack@3ee8c1f` | `AGENTS.md:11` | Read `PORTABILITY.md` for copy strategy | `git ls-files -- PORTABILITY.md` | `(no output)` | **TRUE** — active second agent surface repeats the missing concrete guide |
| 5 | `WadeBalsamo/Qualitative_Research_Algorithm@759bf77` | `CLAUDE.md:13` | `qra_config.json` treated as repository path | `git ls-files -- qra_config.json` | `(no output)` | **FALSE** — generated runtime config under ignored pipeline output; the reported line is also misattributed |
| 6 | `WadeBalsamo/Qualitative_Research_Algorithm@759bf77` | `CLAUDE.md:253` | `efficacy_summary.json` treated as repository path | `git ls-files -- efficacy_summary.json` | `(no output)` | **FALSE** — generated analysis output; implementation/tests name its producer |
| 7 | `orbforge/sensorbox@31aec6b` | `CLAUDE.md:51` | Entry point `asu/main.py` | `git ls-files -- asu/main.py` | `(no output)` | **FALSE** — `asu` is a git submodule and contains the path at its pinned SHA |
| 8 | `orbforge/sensorbox@31aec6b` | `CLAUDE.md:66` | Config lives in `www/config.js` | `git ls-files -- www/config.js` | `(no output)` | **FALSE** — heading scopes it to the `firmware-selector` submodule, where the path exists |
| 9 | `Broccode/acci_framework@075f067` | `.cursorrules:322` | Config is `cursor-tools.config.json` or `~/.cursor-tools/config.json` | `git ls-files -- cursor-tools.config.json` | `(no output)` | **FALSE** — explicit user-level alternative; repo-local file is optional |
| 10 | `DrakeDamon/Portfolio@bdfffca` | `AGENTS.md:5` | `portfolio-nextjs` has `next.config.mjs` | `git ls-files -- next.config.mjs` | `(no output)` | **FALSE** — path is scoped to the `portfolio-nextjs` submodule, where it exists |
| 11 | `PyAutoLabs/PyAutoNerves@5a67f18` | `AGENTS.md:17` | Boundaries live in `PyAutoBrain/ORGANISM.md` | `git ls-files -- PyAutoBrain/ORGANISM.md` | `(no output)` | **FALSE** — surrounding generated block explicitly identifies PyAutoBrain as a peer repository |
| 12 | `Strategic-Cowork-Consulting/confidence-routed-extraction@178a7c3` | `CLAUDE.md:136` | FastAPI exception handlers live in `api/exceptions.py` | `git ls-files -- api/exceptions.py` | `(no output)` | **TRUE** — no such path; handlers are actually in `src/extraction/api/main.py` |
| 13 | `URML-MARS/URML@d317547` | `CLAUDE.md:139` | RFCs use `/docs/rfcs/NNNN-short-name.md` | `git ls-files -- /docs/rfcs/NNNN-short-name.md` | `(no output)` | **FALSE** — filename template; 665 concrete RFC files follow the convention |
| 14 | `VarunDasharadhi/newsletter-demo@bdae024` | `CLAUDE.md:16` | Example uses `workflows/scrape_website.md` | `git ls-files -- workflows/scrape_website.md` | `(no output)` | **FALSE** — explicitly introduced as a generic architecture example |
| 15 | `algotiqa/gui@5d332a6` | `AGENTS.md:53` | No `karma.conf.js`; configuration is implicit | `git ls-files -- karma.conf.js` | `(no output)` | **FALSE** — explicit negation; absence is exactly the documented state |
| 16 | `cpliakas/claude-code-engineering-leaders@018dae1` | `CLAUDE.md:93` | Do not duplicate version in `plugin.json` | `git ls-files -- plugin.json` | `(no output)` | **FALSE** — intentional absence; commit history moved canonical metadata to marketplace config |
| 17 | `elsom25/jcmcginnis-2022@d732441` | `.cursorrules:87` | Posts use `YYYY-MM-DD-slug.md` | `git ls-files -- YYYY-MM-DD-slug.md` | `(no output)` | **FALSE** — naming template instantiated by tracked posts |
| 18 | `fxp/AI-Buzzwords@7327f45` | `CLAUDE.md:374` | See `feedback_no_zhipu.md` in user memory | `git ls-files -- feedback_no_zhipu.md` | `(no output)` | **FALSE** — explicitly external user-memory path |
| 19 | `joemooney/aida@9527689` | `CLAUDE.md:27` | `objects/TYPE/000/SPEC-ID.yaml` in `aida-store` history | `git ls-files -- objects/TYPE/000/SPEC-ID.yaml` | `(no output)` | **FALSE** — schematic path on the explicitly named orphan branch; thousands of concrete objects exist there |
| 20 | `jorgejr568/organizze-mcp@bde178e` | `AGENTS.md:198` | Read `openapi.yaml`; it is the source of truth | `git ls-files -- openapi.yaml` | `(no output)` | **TRUE** — no file, history, generator, retrieval step, other branch, or external qualifier |
| 21 | `lh1207/levihuff.net@3492ab1` | `CLAUDE.md:101` | Config is `eleventy.config.cjs`, not `.eleventy.js` | `git ls-files -- .eleventy.js` | `(no output)` | **FALSE** — explicit negation; `eleventy.config.cjs` is tracked |
| 22 | `limhaowei/prescription-manager@06dfb63` | `.cursor/rules/convex_rules.mdc:23` | HTTP endpoints are defined in `convex/http.ts` | `git ls-files -- convex/http.ts` | `(no output)` | **FALSE** — generic framework guidance; this project defines no HTTP endpoints |
| 23 | `myadmin-plugins/mail-module@1ecb89c` | `CLAUDE.md:109` | Read `CALIBER_LEARNINGS.md` | `git ls-files -- CALIBER_LEARNINGS.md` | `(no output)` | **TRUE** — concrete relative project file, included by the same managed block in `git add`, but absent and unignored |
| 24 | `nicolafavero/eml-to-mailmd@3e1ee2e` | `AGENTS.md:44` | Do not create `main.py`; only source is `eml_to_mailmd.py` | `git ls-files -- main.py` | `(no output)` | **FALSE** — explicit prohibition; absence is intended |
| 25 | `pedrosanto90/portfolio_os@1ac856d` | `CLAUDE.md:25` | Components use `ComponentName/ComponentName.tsx` | `git ls-files -- ComponentName/ComponentName.tsx` | `(no output)` | **FALSE** — naming template; concrete components follow it |
| 26 | `pvieito/CodeSignKit@6c8616c` | `CLAUDE.md:9` | Read `README.md` for project-specific guidance | `git ls-files -- README.md` | `(no output)` | **TRUE** — active symlinked instruction; no README on disk or in history; same instruction blob/owner as row 27 |
| 27 | `pvieito/XCTestKit@7badb9a` | `CLAUDE.md:9` | Read `README.md` for project-specific guidance | `git ls-files -- README.md` | `(no output)` | **TRUE** — active symlinked instruction; no README on disk or in history; same instruction blob/owner as row 26 |
| 28 | `smalls257/claude-md-autoresearch@4805caf` | `CLAUDE.md:3` | Local rules live in each directory's `AGENTS.md` | `git ls-files -- AGENTS.md` | `(no output)` | **FALSE** — describes consumer repositories for a global-CLAUDE experiment, not this repo |
| 29 | `stdkoehler/gamemAIster-frontend@b8e372b` | `CLAUDE.md:19` | Port configured in `.claude/launch.json` | `git ls-files -- .claude/launch.json` | `(no output)` | **FALSE** — environment-specific local preview configuration; repository absence does not disprove it |
| 30 | `stefanoginella/auto-bmad@9224abd` | `CLAUDE.md:153` | `validate-module.py` requires `merge-config.py` | `git ls-files -- validate-module.py` | `(no output)` | **FALSE** — basename reference to an ignored installer-owned script whose full path is documented elsewhere |

## Totals

- **TRUE:** 9 rows across 6 repositories and 5 independent maintainer situations.
- **FALSE:** 21 rows.
- **Finding-level precision:** 9 / 30 = **0.30**.
- **Verified repo-level prevalence:** 6 / 577 scored = **1.04%**.

False-row causes: generated output (2), submodule scope (3), cross-repo scope
(1), templates (4), generic/example guidance (2), negation or intentional
absence (4), user/environment paths (3), installer-owned basename (1), and
consumer-repo guidance (1).

## Three maintainer-sendable findings

These are the three strongest after a second independent check.

### `hoangtruong01/HorseTrack`

`CLAUDE.md` and `AGENTS.md` direct agents to `MASTER_GUIDE.md` and
`PORTABILITY.md` as operating sources. At `3ee8c1f`, both
`git ls-files -- MASTER_GUIDE.md` and `git ls-files -- PORTABILITY.md` return no
path; please restore those guides or update the references.

### `Strategic-Cowork-Consulting/confidence-routed-extraction`

`CLAUDE.md:136` says FastAPI exception handlers live in `api/exceptions.py`, but
that path is not tracked at `178a7c3`. The handlers are implemented in
`src/extraction/api/main.py`; please update the instruction to point contributors
to the existing module.

### `jorgejr568/organizze-mcp`

`AGENTS.md:198` tells contributors to read `openapi.yaml` before adding wire
fields, but that file is not tracked at `bde178e`. Please add the specification
or a reproducible retrieval step, or update the guidance to its canonical source.

## Process note

The initial 30 rows were generated mechanically. Five independent review batches
then inspected current default branches and applied the rule “uncertain or
arguable = FALSE.” The top three were cloned and rerun a second time before this
ledger was written.
