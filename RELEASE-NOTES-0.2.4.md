# Mountain of Helicon 0.2.4

- Fewer false alarms on real repos. On 13 public repos (frozen clones, 26 Sep), 0.2.3
  raised 53 distinct flags. 0.2.4 raises 33. Every flag a hand check found to be a
  real missing file still fires, and no new flag appears. `helicon review` no longer
  counts these as missing paths:
  - A directory listed relative to a parent named earlier on the same line, such as
    `src/` (`cli/`, `core/`).
  - A naming example placed right after a case-style word, such as
    snake_case (`user_profile.py`). A file named elsewhere on that line is still
    checked.
  - A bare file extension such as `.js`, a placeholder such as `ComponentName`, an
    npm subpath such as `react-dom/server.node`, an environment variable prefix, and
    `process.env`.
  - Paths inside JSON, YAML, TOML and XML code blocks, which show a format. Paths in
    shell and source code blocks are still checked.
  - A glob whose files sit under a deeper folder of the same name, such as
    `src/**/*.test.ts` matching `packages/app/src/foo/bar.test.ts`.
- `helicon review` does not read a file outside the repo it reviews.
  - An instruction file or instruction directory that is a symlink to a place outside
    the repo is refused and listed under `refused`.
  - A path or an `@import` that leaves the repo is reported, including one without an
    extension, one starting with `~`, and one inside an imported file.
  - `@/lib/x` is read as a TypeScript path alias and is not checked.
  - Your own files, such as `~/.claude/CLAUDE.md`, are still read through a symlink.
- `helicon --version` prints the version and exits 0.

Known limits:
- `helicon review` does not read `.clinerules`.
- An absolute path to a file outside the repo, written in plain prose, is not
  reported.
- A real path inside a JSON, YAML, TOML or XML code block is not checked. The same
  shape is usually an example.
