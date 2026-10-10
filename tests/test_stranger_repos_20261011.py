"""Lines a stranger's repo made `helicon review` flag on 2026-10-11, with the fix
each one asked for. Every case is copied from a public repo as it stood that day
(humanlayer/humanlayer and vercel/ai, shallow clones) and rebuilt as a small
fixture. The true dead pointers from the same files sit beside the false ones so
the fix cannot buy precision with recall.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helicon import pointers as P
from helicon.commands import check_commands


def _repo(files: dict) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p) or d, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    P._TREE_CACHE.clear()
    P._WS_CACHE.clear()
    return d


def _broken(repo, text, file_dir=""):
    return [p.target for p in P.extract_pointers(text, repo, file_dir) if not p.resolved]


def _ungraded(repo, text, file_dir=""):
    return [u["raw"] for u in P.extract_unverified_paths(text, repo, file_dir)]


# vercel/ai apps/docs/AGENTS.md:24 names `sitemap.md`. It is a directory there
# (app/[lang]/sitemap.md/route.ts), and the basename index held files only.
def test_bare_name_that_is_a_directory_resolves():
    d = _repo({"apps/docs/AGENTS.md": "x", "apps/docs/app/[lang]/sitemap.md/route.ts": "x"})
    text = "The sitemap is generated (see `sitemap.md` there)."
    assert _broken(d, text, "apps/docs") == []


# vercel/ai AGENTS.md:168-169 lists the naming pattern, not a file.
def test_case_pattern_with_two_extensions_is_not_a_path():
    d = _repo({"AGENTS.md": "x"})
    text = "- Test files: `kebab-case.test.ts`\n- Type test files: `kebab-case.test-d.ts`\n"
    assert _broken(d, text) == []


# The same token bare and in code font on one line used to raise IndexError in
# _token_start (group 1 on a regex with no group).
def test_token_start_handles_a_quoted_and_bare_token_on_one_line():
    line = "Name tests `user_profile.py`; snake_case: user_profile.py"
    assert P._token_start(line, "user_profile.py") == 12


# humanlayer apps/daemon/CLAUDE.md:16: "- `Bun.sql` for Postgres. Don't use `pg` or `postgres.js`."
def test_dont_use_is_a_negation():
    d = _repo({"CLAUDE.md": "x"})
    text = "Don't use `pg` or `postgres.js`."
    assert _broken(d, text) == []


def test_runtime_member_access_is_not_a_file():
    d = _repo({"CLAUDE.md": "x", "src/db.ts": "x"})
    assert _broken(d, "- `Bun.sql` for Postgres.\n") == []
    assert _broken(d, "Read `Deno.env` and `process.env` first.\n") == []
    # A bare file name that is nowhere in the tree still fails, as in 0.2.3.
    assert _broken(d, "Edit `gone.js` to change the colours.\n") == ["gone.js"]


def test_a_path_with_a_directory_still_fails_when_missing():
    d = _repo({"CLAUDE.md": "x", "src/db.ts": "x"})
    assert _broken(d, "Run `src/__tests__/e2e-api.test.ts` first.") == ["src/__tests__/e2e-api.test.ts"]
    # humanlayer CLAUDE.md:15 names a directory the repo no longer has.
    assert _broken(d, "- `humanlayer-ts/` - TypeScript SDK") == ["humanlayer-ts/"]


# vercel/ai AGENTS.md:86 `pnpm tsx src/stream-text/openai/basic.ts` exists only under
# examples/ai-functions/, a directory the suffix rule excludes on purpose.
def test_path_found_only_under_an_excluded_dir_is_ungraded():
    d = _repo({"AGENTS.md": "x", "examples/ai-functions/src/stream-text/openai/basic.ts": "x"})
    text = "pnpm tsx src/stream-text/openai/basic.ts    # Run a specific example"
    assert _broken(d, text) == []
    assert "src/stream-text/openai/basic.ts" in _ungraded(d, text)


# vercel/ai AGENTS.md:60 `pnpm install`; :76-80 scripts that live in packages/ai/package.json.
def test_package_manager_builtins_and_workspace_scripts_are_not_missing():
    d = _repo({
        "AGENTS.md": "| `pnpm install` | deps |\n| `pnpm build:watch` | watch |\n| `pnpm test:node` | node |\n| `pnpm nope` | x |\n",
        "package.json": json.dumps({"scripts": {"build": "x"}}),
        "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
        "packages/ai/package.json": json.dumps({"scripts": {"build:watch": "x", "test:node": "x"}}),
    })
    res = check_commands(d)
    raws = sorted(r["raw"] for r in res["receipts"])
    assert raws == ["nope"], raws


# humanlayer CLAUDE.md:72 `make mocks`; the target is in hld/Makefile, not the root one.
def test_make_target_in_a_nested_makefile_counts():
    d = _repo({
        "CLAUDE.md": "- Generate mocks with `make mocks`\n- `make gone`\n",
        "Makefile": "build:\n\techo x\n",
        "hld/Makefile": "mocks:\n\tmockgen\n",
    })
    res = check_commands(d)
    raws = sorted(r["raw"] for r in res["receipts"])
    assert raws == ["gone"], raws
