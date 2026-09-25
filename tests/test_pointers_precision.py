"""Precision fixtures for the pointer extractor, 2026-09-03.

Every case here is a line copied from one of the author's own instruction files (or
anthropic-cookbook's CLAUDE.md) that `helicon review` graded as a dead pointer while the
thing it named existed. A lie-detector that convicts truthful files is the defect it
exists to catch, so each false positive gets its own row and each TRUE dead pointer is
kept beside it to prove the fix did not buy precision with recall.
"""
import os, sys, tempfile, textwrap
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


def test_home_path_in_code_font_is_reported_once_but_never_affects_repo_grade():
    d = _repo({"README.md": "x"})
    home = os.path.expanduser("~")
    probe = os.path.join(home, ".helicon-pointer-test-2026-09-03.json")
    open(probe, "w").write("{}")
    try:
        assert _broken(d, "Needs `~/.helicon-pointer-test-2026-09-03.json` to run.") == []
        gaps = P.extract_unverified_paths(
            "Needs `~/.helicon-pointer-test-2026-09-03.json` to run.", d)
        assert len(gaps) == 1
        assert "present on this host" in gaps[0]["reason"]
    finally:
        os.remove(probe)
    # An absent home path is outside the repo population. It stays visible as
    # unverified setup evidence but cannot lower the repo grade.
    line = "Needs `~/.no-such-dir-2026/config.json` to run."
    assert _broken(d, line) == []
    gaps = P.extract_unverified_paths(line, d)
    assert [g["raw"] for g in gaps] == ["`~/.no-such-dir-2026/config.json`"]
    assert "external path absent" in gaps[0]["reason"]


def test_create_on_demand_path_is_not_broken_but_real_miss_still_is():
    d = _repo({"README.md": "x"})
    create_line = "Append the receipt to `.fleet/ACK.jsonl`."
    assert _broken(d, create_line) == []
    gaps = P.extract_unverified_paths(create_line, d)
    assert len(gaps) == 1
    assert "creates this path" in gaps[0]["reason"]

    # A nearby writing verb without a directional write-to relationship must not
    # silence a missing repo pointer.
    assert _broken(d, "Tasks: write the beat; rows in `todo.md`.") == ["todo.md"]


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


def test_parent_dir_on_the_same_line_resolves_listed_children():
    """repomix: `src/` (`cli/`, `config/`, `core/`, `shared/`) lists children of src/."""
    d = _repo({
        "src/cli/index.ts": "x",
        "src/config/index.ts": "x",
        "src/core/index.ts": "x",
        "src/shared/index.ts": "x",
    })
    line = "- `src/` - main source code (`cli/`, `config/`, `core/`, `shared/`)."
    assert _broken(d, line) == []
    # A listed child that is not under that parent is still a miss.
    assert _broken(d, "- `src/` - main source code (`cli/`, `missing/`).") == ["missing/"]
    # The same directory token with no parent on the line is still a miss,
    # even though src/cli exists.
    assert _broken(d, "See `cli/`.") == ["cli/"]


def test_naming_pattern_and_placeholder_are_not_paths():
    d = _repo({"src/index.ts": "x"})
    assert _broken(d, "- Files: `kebab-case.js`, `PascalCase.js` (for classes)") == []
    assert _broken(d, "- **Files**: Use kebab-case for file names (`user-profile.component.ts`)") == []
    assert _broken(d, "- **Files/Modules**: Use snake_case (`user_profile.py`)") == []
    assert _broken(d, "- **Files/Modules**: Use snake_case (`user_profile.rb`)") == []
    assert _broken(
        d, "1. **One folder per component**: `ComponentName/ComponentName.tsx` + `index.ts`"
    ) == []
    assert _broken(d, '"path": "agents/category/agent-name.md",') == []
    # Same shapes, said as real paths, are still misses.
    assert _broken(d, "Update `user_profile.py` before release.") == ["user_profile.py"]
    assert _broken(d, "See `Button/Button.tsx` for the widget.") == ["Button/Button.tsx"]
    assert _broken(
        d, "Review agents/development-team/react-expert.md next."
    ) == ["agents/development-team/react-expert.md"]
    assert _broken(
        d, "Use snake_case in new modules, and fix `src/user_profile.py`."
    ) == ["src/user_profile.py"]


def test_bare_extension_is_not_a_path():
    d = _repo({"CLAUDE.md": "x"})
    line = "- `typescript` - `.ts`, `.tsx`, `.js`, and `.jsx` package and tooling code."
    assert _broken(d, line) == []
    assert _broken(d, "imports don't need `.js` extensions.") == []
    # A filename with that extension, and a real dotfile, are still paths.
    assert _broken(d, "Open `gone.js`.") == ["gone.js"]
    assert _broken(d, "Run `src/missing.ts` in dev.") == ["src/missing.ts"]
    assert _broken(d, "Copy `.env` before starting.") == [".env"]


def test_fenced_code_examples_are_not_graded_and_prose_paths_still_are():
    d = _repo({"CLAUDE.md": "x"})
    text = textwrap.dedent("""\
        Format:
        ```json
        { "location": "src/auth.js:45" }
        ```
        ```tsx
        import('./animation-frames.js')
        ```
        ```ruby
        # spec/spec_helper.rb
        config.example_status_persistence_file_path = "spec/examples.txt"
        ```
        ```tsx
        // app/index.tsx
        ```
        See `src/missing.js` for the handler.
        ```
        review cli-tool/components/agents/development-team/react-expert.md
        ```
        ```markdown
        Read `.loki/queue/pending.json` before claiming work.
        ```
        """)
    broken = _broken(d, text)
    assert "src/auth.js" not in broken
    assert "animation-frames.js" not in broken
    assert "spec/spec_helper.rb" not in broken
    assert "spec/examples.txt" not in broken
    assert "app/index.tsx" not in broken
    # Same shape in prose, in an untagged fence, and in a markdown fence.
    assert "src/missing.js" in broken
    assert "cli-tool/components/agents/development-team/react-expert.md" in broken
    assert ".loki/queue/pending.json" in broken


def test_glob_matches_a_tree_suffix_and_a_real_miss_stays():
    # Root `components/` exists, so the glob is a path, but the json lives under
    # dashboard/public/components/. An unmatched glob under a real directory stays a miss.
    d = _repo({
        "components/readme.md": "x",
        "dashboard/public/components/agents.json": "{}",
        "contracts/src/FavourEscrowV2.sol": "x",
    })
    assert _broken(d, "artifacts (`components/*.json`).") == []
    assert _broken(d, "Foundry: `contracts/src/Nothing*.sol`.") == ["contracts/src/Nothing*.sol"]


def test_npm_node_subpath_is_not_a_repo_file():
    d = _repo({"src/index.ts": "x", "cli-tool/readme.md": "x"})
    assert _broken(d, "aliases `react-dom/server` to `react-dom/server.node`.") == []
    # A `.node` file under a real directory is still a path.
    assert _broken(d, "Load `src/addon.node` at startup.") == ["src/addon.node"]
    assert _broken(d, "See `cli-tool/missing.node`.") == ["cli-tool/missing.node"]


def test_env_var_prefix_is_not_a_repo_path():
    d = _repo({"CLAUDE.md": "x"})
    assert _broken(d, "recorded in `$SUPERSET_HOME_DIR/plugins/installed_plugins.json`.") == []
    assert _broken(d, "See `plugins/installed_plugins.json`.") == ["plugins/installed_plugins.json"]


def test_process_env_is_a_code_identifier():
    d = _repo({"CLAUDE.md": "x"})
    assert _broken(d, "1. Use `process.env` (Node.js) or `os.environ.get()` (Python)") == []
    assert _broken(d, "Copy `service.env` into place.") == ["service.env"]
    assert _broken(d, "Load from `.env` file.") == [".env"]
