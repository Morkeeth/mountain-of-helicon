# Mountain of Helicon 0.2.2

- `helicon review` no longer reports false contradictions on monorepos with symlinked
  agent files. On a clone of colinhacks/zod, PyPI 0.2.1 printed GRADE C with 24
  contradictions. 0.2.2 prints GRADE A with 0. The fixes:
  - Instruction files that are symlinks to one file are graded once. The review names the aliases.
  - Paths resolve against monorepo packages (package.json `workspaces`, pnpm-workspace.yaml)
    before they count as missing.
  - CLI flags such as `--conditions=@zod/source` and empty targets such as `//` are never graded as paths.
  - Paths the repo's `.gitignore` covers are listed as created on demand and not graded.
- The README states that Python 3.10 or newer is required, and says how to get it on a Mac.
