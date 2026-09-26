"""The doorway board — real token cost of what each repo loads into an agent.

Pins the honest properties: the count is chars/4 over the ACTUAL loaded files,
@imports are resolved (and contained to the repo), cold docs load zero, repos
sort heaviest-first, and a missing root is reported rather than invented.
"""
import os
import subprocess

import pytest

from helicon import doorway


def _git_init(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def _repo(root, name, files: dict):
    p = root / name
    p.mkdir(parents=True)
    _git_init(p)
    for rel, text in files.items():
        f = p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return p


def test_loaded_docs_counts_claude_md(tmp_path):
    body = "# Rules\n" + ("x" * 400) + "\n"   # ~ >100 tokens
    repo = _repo(tmp_path, "alpha", {"CLAUDE.md": body})
    load = doorway.repo_load(str(repo))
    assert load["doc_count"] == 1
    assert load["docs"][0]["file"] == "CLAUDE.md"
    assert load["loaded_tokens"] == len(body) // 4
    assert load["loaded_tokens"] > 0


def test_at_imports_are_followed_and_counted(tmp_path):
    imported = "# Imported\n" + ("y" * 800) + "\n"
    claude = "# Root\nSee @docs/more.md for details.\n"
    repo = _repo(tmp_path, "beta", {"CLAUDE.md": claude, "docs/more.md": imported})
    load = doorway.repo_load(str(repo))
    files = {d["file"] for d in load["docs"]}
    assert "CLAUDE.md" in files and "docs/more.md" in files
    # loaded total includes the imported file's tokens
    assert load["loaded_tokens"] == (len(claude) + len(imported)) // 4
    more = next(d for d in load["docs"] if d["file"] == "docs/more.md")
    assert more["via_import"] == "CLAUDE.md"


def test_imports_cannot_escape_the_repo(tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("SECRET " * 100)
    claude = f"# Root\nload @../secret.md please\n"
    repo = _repo(tmp_path, "gamma", {"CLAUDE.md": claude})
    load = doorway.repo_load(str(repo))
    files = {d["file"] for d in load["docs"]}
    assert not any("secret" in f for f in files), "an @import must not escape the repo"


def test_cold_doc_loads_zero_but_is_kept(tmp_path):
    body = "# Rules\n" + ("z" * 1000) + "\n"
    repo = _repo(tmp_path, "delta", {"CLAUDE.md": body})
    hot = doorway.repo_load(str(repo))
    cold = doorway.repo_load(str(repo), cold={"CLAUDE.md"})
    assert hot["loaded_tokens"] > 0
    assert cold["loaded_tokens"] == 0          # loads nothing
    assert cold["cold_tokens"] == hot["loaded_tokens"]   # kept, not deleted
    assert cold["doc_count"] == 1              # still present on the board


def test_board_lists_repos_heaviest_first(tmp_path):
    _repo(tmp_path, "small", {"CLAUDE.md": "# s\n" + "a" * 40})
    _repo(tmp_path, "big", {"CLAUDE.md": "# b\n" + "a" * 4000})
    _repo(tmp_path, "nodocs", {"README.md": "not an agent rules file"})  # skipped-ish
    board = doorway.list_repos(root=str(tmp_path))
    assert board["exists"] is True
    names = [r["name"] for r in board["repos"]]
    assert names[0] == "big" and "small" in names   # heaviest first
    big = next(r for r in board["repos"] if r["name"] == "big")
    small = next(r for r in board["repos"] if r["name"] == "small")
    assert big["loaded_tokens"] > small["loaded_tokens"]
    assert board["total_loaded_tokens"] == sum(r["loaded_tokens"] for r in board["repos"])


def test_missing_root_is_reported_not_invented(tmp_path):
    board = doorway.list_repos(root=str(tmp_path / "does-not-exist"))
    assert board["exists"] is False
    assert board["repos"] == [] and board["repo_count"] == 0


def test_root_resolution_prefers_arg_then_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_CODE_ROOT", str(tmp_path / "from-env"))
    assert doorway.resolve_root(str(tmp_path / "from-arg")).endswith("from-arg")
    assert doorway.resolve_root(None).endswith("from-env")
    monkeypatch.delenv("HELICON_CODE_ROOT")
    assert doorway.resolve_root(None, {"code_root": str(tmp_path / "from-cfg")}).endswith("from-cfg")


def _joined_text(docs) -> str:
    return "\n".join(d.get("text", "") for d in docs)


def test_loaded_docs_refuses_a_root_symlink_outside_the_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "out"
    outside.write_text("SENTINEL-OUTSIDE-ROOT\n")
    (repo / "CLAUDE.md").symlink_to("../out")
    docs = doorway.loaded_docs(str(repo))
    assert "SENTINEL-OUTSIDE-ROOT" not in _joined_text(docs)
    refused = [d for d in docs if "refused" in d.get("reason", "")]
    assert any(d["file"] == "CLAUDE.md" for d in refused)
    assert all("SENTINEL-OUTSIDE-ROOT" not in d.get("reason", "") for d in refused)


def test_loaded_docs_in_repo_symlink_loads_once(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    body = "# Agents\nhello agents unique\n"
    (repo / "AGENTS.md").write_text(body)
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    docs = doorway.loaded_docs(str(repo))
    loaded = [d for d in docs if "hello agents unique" in d.get("text", "")]
    assert len(loaded) == 1
    assert loaded[0]["text"] == body


def test_import_chain_through_symlinked_directory_is_refused(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("SENTINEL-CHAIN-DIR\n")
    repo.mkdir()
    (repo / "linked").symlink_to(outside, target_is_directory=True)
    (repo / "notes").mkdir()
    (repo / "notes" / "inner.md").write_text("inner stays\n@../linked/secret.md\n")
    (repo / "CLAUDE.md").write_text("root\n@notes/inner.md\n")
    docs = doorway.loaded_docs(str(repo))
    assert "SENTINEL-CHAIN-DIR" not in _joined_text(docs)
    assert any("inner stays" in d.get("text", "") for d in docs)
    refused = [d for d in docs if "refused" in d.get("reason", "")]
    assert any(d["file"].endswith("secret.md") and "refused" in d["reason"] for d in refused)
    assert all("SENTINEL-CHAIN-DIR" not in d.get("reason", "") for d in refused)


def test_cursor_rules_directory_symlink_is_refused(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.mdc").write_text("SENTINEL-MDC\n")
    repo.mkdir()
    (repo / ".cursor").mkdir()
    (repo / ".cursor" / "rules").symlink_to(outside, target_is_directory=True)
    (repo / "CLAUDE.md").write_text("# ok\n")
    docs = doorway.loaded_docs(str(repo))
    assert "SENTINEL-MDC" not in _joined_text(docs)
    refused = [d for d in docs if "refused" in d.get("reason", "")]
    assert any(d["file"] == ".cursor/rules" for d in refused)
