"""Regression coverage for false alarms reproduced on public instruction files."""

from helicon.pointers import check_pointers


def audit(tmp_path, text):
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    report = check_pointers(str(tmp_path))
    return (
        [p["raw"].strip("`") for p in report["receipts"]],
        [p["raw"].strip("`") for p in report["unverified_paths"]],
    )


def test_placeholder_paths_in_shell_and_text_examples(tmp_path):
    broken, _ = audit(tmp_path, """```txt
TEST=path/to/test.py make test
```
```sh
uv run pytest tests/path/test_foo.py
run checks::<path/to/mdtest_file.md>
python scripts/missing_runner.py
```
""")
    assert broken == ["scripts/missing_runner.py"]


def test_runtime_bundle_files_and_optional_project_settings(tmp_path):
    broken, unverified = audit(tmp_path, """- Treat `state.json` as the consumer API and `manifest.json` identity metadata
  as the bundle discovery API. For every `state.json` schema change, bump the version.
- **Config locations** (lowest to highest precedence):
  - `.claude/settings.json`, `.continue/settings.json` (project)
  - `.claude/settings.local.json` (project-local)
- Tests should be written with `.test.ts` extension.
- Open `src/checked-in.json`.
- Load the checked-in defaults from `settings.json`.
""")
    assert broken == ["src/checked-in.json", "settings.json"]
    assert set(unverified) == {
        "state.json", "manifest.json", ".claude/settings.json",
        ".continue/settings.json", ".claude/settings.local.json",
    }


def test_explicit_upstream_paths_and_checkout(tmp_path):
    (tmp_path / "roll.js").touch()
    broken, unverified = audit(tmp_path, """The server itself is in
`microsoft/playwright`, in `packages/playwright-core/src/tools/`: `mcp/` has the server,
and `backend/` has the tools.

- `roll.js` copies `config.d.ts` from
  `packages/playwright-core/src/tools/mcp/config.d.ts`. Change it upstream.
- Work in a checkout of `microsoft/playwright`, as its instructions say.
  The tests of the server are its `tests/mcp/`. Fix here only what this repo owns.

1. Run `roll.js`. It copies `config.d.ts` from `../playwright`, a checkout of
   `microsoft/playwright`: check out the same revision.

Open this project's `docs/missing.md` and `../outside/AGENTS.md`.
Read [also](../outside/README.md).
@../outside/instructions.md
""")
    assert broken == [
        "config.d.ts", "docs/missing.md", "../outside/AGENTS.md",
        "../outside/README.md", "@../outside/instructions.md",
    ]
    assert set(unverified) == {
        "packages/playwright-core/src/tools/", "mcp/", "backend/",
        "packages/playwright-core/src/tools/mcp/config.d.ts", "tests/mcp/", "../playwright",
    }


def test_later_local_reference_to_the_same_name_remains_graded(tmp_path):
    broken, unverified = audit(tmp_path, """The server is in `owner/project`, in `src/bridge/server.py`.
Open our `src/bridge/server.py` and `state.json`.
""")
    assert broken == ["src/bridge/server.py", "state.json"]
    assert unverified == ["src/bridge/server.py"]


def test_local_checkout_directory_and_same_line_reference_are_still_graded(tmp_path):
    (tmp_path / "packages" / "web").mkdir(parents=True)
    broken, unverified = audit(tmp_path, """The web app is in `packages/web`, in `src/missing.py`.
The upstream app is in `owner/project`, in `src/elsewhere.py`; open our `src/elsewhere.py`.
""")
    assert broken == ["src/missing.py", "src/elsewhere.py"]
    assert unverified == ["src/elsewhere.py"]


def test_retains_a_real_path_under_placeholder_named_directory(tmp_path):
    (tmp_path / "path" / "to").mkdir(parents=True)
    broken, unverified = audit(tmp_path, "Open `path/to/missing.py`.\n")
    assert broken == ["path/to/missing.py"]
    assert unverified == []
