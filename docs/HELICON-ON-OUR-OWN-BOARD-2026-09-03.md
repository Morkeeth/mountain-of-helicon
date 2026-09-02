# I ran the liar-detector on my own six repos

*2026-09-03. `helicon review .` (branch `fable/first-screen-2026-09-03`) run read-only inside six of
the author's repositories, on whatever branch each working tree was on. Nothing in those repos was
edited. Every "broken" line was then checked by hand at the file it named.*

## The result, after the fix

| repo | branch | instruction files | grade | checked | broken | the dead pointer, verbatim |
|---|---|---|---|---|---|---|
| zup | `fable/promised-2026-09-02` | CONTEXT.md | **B** | 21 | 2 | `CONTEXT.md:86` "rows in `todo.md`" — no `todo.md` in the repo; `CONTEXT.md:111` "Later `runs.json`" — planned, not present |
| world-relay | `night/2026-09-02` | CLAUDE.md, AGENTS.md, AGENT.md | **B** | 35 | 1 | `AGENTS.md:19` "`src/__tests__/e2e-api.test.ts` is opt-in" — the file is gone |
| cleared | `main` | AGENTS.md | **A** | 22 | 0 | — |
| agentgrinder | `fable/verified-per-turn-2026-09-02` | none | — | 0 | 0 | no CLAUDE.md / AGENTS.md / .cursorrules: nothing tells an agent anything, so nothing can lie |
| agents-for-humans | `fable/magnet-bugs-2026-09-03` | none | — | 0 | 0 | same |
| transcripto | `fable/correction-rate-2026-09-02` | none | — | 0 | 0 | same |

Two of the three graded repos lie to their agent in one or two places each. Three repos on the board
have no agent instructions at all, which is its own finding: an agent opening them starts from zero
every session.

## What the tool got wrong about its owner, before the fix

The first run of the same command, same morning, said something much worse, and it was the tool
that was wrong. Every line below was reported as "not in this repo"; every target existed.

| repo | first run | of which false | what the tool did |
|---|---|---|---|
| zup | GRADE C, 7 broken | **5** | `~/.zen/zup-active.json` (and three siblings) read as `zen/…`: the token in code font was graded correctly at `$HOME`, then scanned again as bare prose starting after the `.`; `~/CODE/fleet-ops/runs/…` read as `ops/runs/…` because the match started after the hyphen |
| world-relay | GRADE C, 8 broken | **7** | `mcp-server/README.md` read as `server/README.md`; `campaign-unlock.ts` (lives in `src/lib/`) graded only at the root; `@typescript-eslint/no-explicit-any` graded as an @import; `contracts/src/FavourEscrowV2*.sol` graded as a literal file; `/api/escrow-v2` (a route, `src/app/api/escrow-v2/`) and `relay.vercel.app/…` (a URL) graded as repo paths |
| cleared | GRADE B, 4 broken | **4** | `truth-dictionary/aliases.json` read as `dictionary/aliases.json`; `research-corpus/MANIFEST.json` read as `corpus/MANIFEST.json`; `research-inbox/YYYY-MM-DD-<slug>.md` (a template) graded as a file; `~/.cursor/mcp.json` read as `cursor/mcp.json` |
| mountain-of-helicon (itself) | GRADE B, 1 broken | **1** | `~/.helicon/config.json` read as `helicon/config.json` |
| anthropic-cookbook (the README's own example) | GRADE D, 4 broken | **4** | `/notebook-review`, `/model-check`, `/link-review` are slash commands that exist at `.claude/commands/*.md`; `<username>/<feature-description>` is the branch-naming template |

Totals: **24 findings, 21 false, 3 true.** Precision 12.5%. The README shipped the cookbook D as its
proof for a day; the cold-run doc of 2026-09-02 recorded it as a stranger-shaped success.

The defects, all in `helicon/pointers.py`, each now pinned by a fixture in
`tests/test_pointers_precision.py` (11 tests, 21 assertions; the true positives are asserted beside
the false ones so the fix did not buy precision with recall):

1. The bare-path regex's lookbehind refused `\w`, backtick, `(`, `/`, `@` — but not `-`, `.`, `~`.
   A match could start mid-token, so every hyphenated directory and every home path was reported
   under a name that does not exist.
2. Code spans were graded, then the same line was scanned again as prose with the spans still in it.
3. Slash commands, npm scopes, globs, templates, hostnames, URL routes and bare basenames had no
   class of their own and fell through to "root-relative file that is not there".

## After the fix, same seven

| repo | before | after | true dead pointers |
|---|---|---|---|
| anthropic-cookbook | D · 4/7 | **A · 0/6** | 0 |
| mountain-of-helicon | B · 1/13 | **A · 0/14** | 0 |
| zup | C · 7/26 | **B · 2/21** | 2 |
| world-relay | C · 8/36 | **B · 1/35** | 1 |
| cleared | B · 4/27 | **A · 0/22** | 0 |
| agentgrinder · agents-for-humans · transcripto | no file | no file | — |

"Checked" counts fall as well, because tokens the tool cannot grade (a harness built-in like
`/help`, a route with no directory, a URL) are now left out of the denominator instead of counted as
verified.

## Reproduce

```bash
git clone https://github.com/Morkeeth/mountain-of-helicon && cd mountain-of-helicon
git checkout fable/first-screen-2026-09-03
python3 -m pip install -e . && python3 -m pytest -q tests/test_pointers_precision.py
cd /path/to/any/repo && helicon review .
```

*The three private-branch names above are the branches those working trees happened to be on; the
grades are of the working tree, not of `main`.*
