"""Precision fixtures for the pointer extractor, 2026-09-03.

Every case here is a line copied from one of the author's own instruction files (or
anthropic-cookbook's CLAUDE.md) that `helicon review` graded as a dead pointer while the
thing it named existed. A lie-detector that convicts truthful files is the defect it
exists to catch, so each false positive gets its own row and each TRUE dead pointer is
kept beside it to prove the fix did not buy precision with recall.
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helicon import pointers as P


def _repo(files):
    d = tempfile.mkdtemp()
    for r, b in files.items():
        p = os.path.join(d, r)
        os.makedirs(os.path.dirname(p) or d, exist_ok=True)
        open(p, "w").write(b)
    P._TREE_CACHE.clear()
    return d


def _broken(repo, text):
    return [p.target for p in P.extract_pointers(text, repo) if not p.resolved]


def _checked(repo, text):
    return [p.target for p in P.extract_pointers(text, repo)]


def test_hyphenated_dir_is_not_truncated():
    d = _repo({"truth-dictionary/aliases.json": "{}", "mcp-server/README.md": "x"})
    assert _broken(d, "Add phrasings to `truth-dictionary/aliases.json`.") == []
    assert _broken(d, "See [`/mcp-server/README.md`](mcp-server/README.md) for config.") == []


def test_hyphenated_dir_still_reports_a_real_miss_by_its_full_name():
    d = _repo({"README.md": "x"})
    assert _broken(d, "Read `research-corpus/MANIFEST.json` first.") == ["research-corpus/MANIFEST.json"]


def test_home_path_in_code_font_is_graded_once_at_home_not_twice():
    d = _repo({"README.md": "x"})
    home = os.path.expanduser("~")
    probe = os.path.join(home, ".helicon-pointer-test-2026-09-03.json")
    open(probe, "w").write("{}")
    try:
        assert _broken(d, "Needs `~/.helicon-pointer-test-2026-09-03.json` to run.") == []
    finally:
        os.remove(probe)
    # and a home path that does not exist is still one broken pointer, not a mangled second one
    b = _broken(d, "Needs `~/.no-such-dir-2026/config.json` to run.")
    assert b == ["~/.no-such-dir-2026/config.json"]


def test_slash_command_resolves_against_claude_commands():
    d = _repo({".claude/commands/notebook-review.md": "x"})
    assert _broken(d, "- `/notebook-review` - Review notebook quality") == []
    assert _checked(d, "- `/notebook-review` - Review notebook quality") == [".claude/commands/notebook-review.md"]
    # a command this repo does not define is a harness built-in, not a dead file
    assert _checked(d, "Run `/help` for the list.") == []


def test_branch_template_is_not_a_pointer():
    d = _repo({"README.md": "x"})
    assert _checked(d, "**Branch naming:** `<username>/<feature-description>`") == []
    assert _checked(d, "append to `research-inbox/YYYY-MM-DD-<slug>.md`") == []


def test_npm_scope_is_not_an_import():
    d = _repo({"README.md": "x"})
    assert _checked(d, "Many lint errors (`@typescript-eslint/no-explicit-any`) pre-exist.") == []
    # a real @import that is missing is still broken
    assert _broken(d, "Read @docs/setup.md before starting.") == ["docs/setup.md"]


def test_bare_basename_resolves_anywhere_in_the_tree():
    d = _repo({"src/lib/campaign-unlock.ts": "x"})
    assert _broken(d, "ERC-20 transfer (`campaign-unlock.ts`) is the only path.") == []
    assert _broken(d, "rows in `todo.md`") == ["todo.md"]


def test_glob_resolves_when_anything_matches():
    d = _repo({"contracts/src/FavourEscrowV2.sol": "x"})
    assert _broken(d, "Foundry: `contracts/src/FavourEscrowV2*.sol`.") == []
    assert _broken(d, "Foundry: `contracts/src/Nothing*.sol`.") == ["contracts/src/Nothing*.sol"]


def test_route_resolves_by_directory_suffix_or_is_not_graded():
    d = _repo({"src/app/api/escrow-v2/route.ts": "x"})
    assert _broken(d, "API `/api/escrow-v2`, override via env.") == []
    assert _checked(d, "API `/api/escrow-v2`, override via env.") == ["api/escrow-v2"]
    assert _checked(d, "POST `/api/nope` is retired.") == []


def test_hostname_path_is_a_url_not_a_pointer():
    d = _repo({"README.md": "x"})
    assert _checked(d, "Spec at `relay.vercel.app/api/agent/openapi.json`.") == []


def test_real_dead_pointer_is_still_caught():
    d = _repo({"src/index.ts": "x"})
    assert _broken(d, "`src/__tests__/e2e-api.test.ts` is opt-in.") == ["src/__tests__/e2e-api.test.ts"]
