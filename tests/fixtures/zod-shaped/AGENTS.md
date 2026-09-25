# zod-shaped fixture

Vendored from the shape of colinhacks/zod AGENTS.md (2026-09-23). CLAUDE.md and
.cursorrules are symlinks to this file.

## Commands
- `nub run test` - Run the tests
- `nub run check:comments` - Fail on stacked `//` comment lines (`--fix` joins them)
- `nub run lint` - Run biome linter

## The three axes

Any change to `core/` at all needs a number on all three axes.
The regexes live in `core/regexes.ts`, so every alternation is bytes in every bundle.
Bundle a `packages/bench` fixture under `--conditions=@zod/source` and gzip it.
The package sources live in `src/` of each workspace package.
Empty code spans such as `` must never become a pointer.

Write-ups live in the gitignored `.triage/` tree, `.triage/issues/NNNN/results.md` and
`.triage/prs/NNNN/results.md`.

See `docs/GONE.md` for the release checklist.
