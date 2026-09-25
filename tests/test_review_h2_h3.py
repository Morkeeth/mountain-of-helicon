"""H2 and H3: a review must not leave the repo, and a basename is not a location.

The fixture matches the 2026-09-25 reproduction. CLAUDE.md is a symlink to
../outside/OUT.md. AGENTS.md names `config.py` (only at src/deep/config.py),
a missing local link docs/GUIDE.md, and `../outside/OUT.md`.
"""
import builtins
import os

from helicon import pointers as P
from helicon.review import format_review, review, review_summary


def _fixture(tmp_path):
    root = tmp_path / "h23"
    outside = root / "outside"
    repo = root / "repo"
    outside.mkdir(parents=True)
    (outside / "OUT.md").write_text(
        "# Secret outside\nRun `outside-only-cmd` and see `secret/leak.txt`.\n",
        encoding="utf-8",
    )
    deep = repo / "src" / "deep"
    deep.mkdir(parents=True)
    (deep / "config.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        "# Agents\n"
        "Config lives in `config.py`.\n"
        "See [the guide](docs/GUIDE.md) and `../outside/OUT.md`.\n",
        encoding="utf-8",
    )
    (repo / "CLAUDE.md").symlink_to("../outside/OUT.md")
    P._TREE_CACHE.clear()
    P._WS_CACHE.clear()
    P._IGNORE_CACHE.clear()
    return repo, outside


def _review(repo):
    P._TREE_CACHE.clear()
    P._WS_CACHE.clear()
    P._IGNORE_CACHE.clear()
    res = review(str(repo), execute=False)
    return res, format_review(str(repo), res)


def test_outside_instruction_symlink_is_refused_and_not_read(tmp_path):
    repo, _outside = _fixture(tmp_path)
    res, out = _review(repo)
    refused = res["pointers"]["refused"]
    assert any(row["file"] == "CLAUDE.md" and "refused" in row["reason"] for row in refused)
    assert "CLAUDE.md refused" in out
    assert "secret/leak.txt" not in out
    assert "outside-only-cmd" not in out
    assert "CLAUDE.md" not in res["pointers"]["files"]


def test_review_does_not_open_a_file_outside_the_repo(tmp_path, monkeypatch):
    repo, outside = _fixture(tmp_path)
    outside_real = os.path.realpath(outside)
    opened = []

    def _note(path, *, followed: bool):
        if isinstance(path, int):
            return
        sp = os.fspath(path)
        if not os.path.isabs(sp):
            return
        ab = os.path.abspath(sp)
        suspects = [ab]
        if followed and os.path.islink(ab):
            raw = os.readlink(ab)
            target = raw if os.path.isabs(raw) else os.path.join(os.path.dirname(ab), raw)
            suspects.append(os.path.abspath(target))
        for suspect in suspects:
            try:
                canon = os.path.realpath(suspect) if os.path.exists(suspect) else os.path.abspath(suspect)
                if os.path.commonpath([canon, outside_real]) == outside_real:
                    opened.append(sp)
            except (ValueError, OSError):
                pass

    real_open = os.open
    real_builtin = builtins.open

    def guarded_os(path, flags, *args, **kwargs):
        nofollow = bool(isinstance(flags, int) and flags & getattr(os, "O_NOFOLLOW", 0))
        _note(path, followed=not nofollow)
        return real_open(path, flags, *args, **kwargs)

    def guarded_builtin(file, *args, **kwargs):
        _note(file, followed=True)
        return real_builtin(file, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_os)
    monkeypatch.setattr(builtins, "open", guarded_builtin)
    _review(repo)
    assert opened == []


def test_parent_path_outside_the_repo_is_reported_not_a_pass(tmp_path):
    repo, _outside = _fixture(tmp_path)
    res, _out = _review(repo)
    hit = next(r for r in res["pointers"]["receipts"] if "../outside/OUT.md" in r["raw"])
    assert "outside" in hit["receipt"]
    summary = review_summary(str(repo), res)
    assert all("../outside/OUT.md" not in f["raw"] or f["tier"] == "pointer" for f in summary["findings"])
    assert any("../outside/OUT.md" in f["raw"] for f in summary["findings"])


def test_basename_found_only_deeper_is_not_a_pass(tmp_path):
    repo, _outside = _fixture(tmp_path)
    res, out = _review(repo)
    hit = next(r for r in res["pointers"]["receipts"] if "config.py" in r["raw"])
    assert "not at the stated path" in hit["receipt"]
    assert "src/deep/config.py" in hit["receipt"]
    assert "basename anywhere" not in out


def test_broken_local_markdown_link_is_a_contradiction(tmp_path):
    repo, _outside = _fixture(tmp_path)
    res, _out = _review(repo)
    hit = next(r for r in res["pointers"]["receipts"] if "docs/GUIDE.md" in r["raw"])
    assert hit["kind"] == "MDLINK"
    assert res["pointers"]["broken"] >= 1
    summary = review_summary(str(repo), res)
    assert summary["broken"] >= 1
    assert any("docs/GUIDE.md" in f["raw"] for f in summary["findings"])


def test_gitignore_exclusion_ignores_case(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("Docs/\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("See [the guide](docs/GUIDE.md).\n", encoding="utf-8")
    P._TREE_CACHE.clear()
    P._IGNORE_CACHE.clear()
    assert P.is_gitignored(str(repo), "docs/GUIDE.md")
    res = P.check_pointers(str(repo))
    assert res["broken"] == 0
    assert any("docs/GUIDE.md" in g["raw"] and g["reason"].startswith("gitignored")
               for g in res["unverified_paths"])


def test_vendored_exclusion_ignores_case(tmp_path):
    repo = tmp_path / "repo"
    (repo / "Vendor" / "pkg" / "src").mkdir(parents=True)
    (repo / "Vendor" / "pkg" / "src" / "only.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("See `pkg/src/only.py`.\n", encoding="utf-8")
    P._TREE_CACHE.clear()
    res = P.check_pointers(str(repo))
    assert res["broken"] == 1
    assert any("pkg/src/only.py" in r["raw"] for r in res["receipts"])
