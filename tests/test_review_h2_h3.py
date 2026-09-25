"""H2 and H3: a review must not leave the repo, and a basename is not a location.

The fixture matches the 2026-09-25 reproduction. CLAUDE.md is a symlink to
../outside/OUT.md. AGENTS.md names `config.py` (only at src/deep/config.py),
a missing local link docs/GUIDE.md, and `../outside/OUT.md`.
"""
import builtins
import os
import shutil
from pathlib import Path

from helicon import doorway
from helicon import pointers as P
from helicon.review import format_review, review, review_summary

_CASES = Path(
    "/private/tmp/claude-501/-Users-morkeeth/7a280f02-767c-40d2-a4f8-dc5ca75fca8a"
    "/scratchpad/cold-review/cases"
)


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


def _guard_paths(monkeypatch, banned: set[str]):
    """Record open/stat of banned paths and still perform the real call."""
    touched: list[str] = []
    banned_abs = {os.path.abspath(p) for p in banned}

    def _hit(path) -> str | None:
        if isinstance(path, int):
            return None
        try:
            sp = os.fspath(path)
        except TypeError:
            return None
        if not isinstance(sp, str) or not os.path.isabs(sp):
            return None
        ab = os.path.abspath(sp)
        if ab in banned_abs:
            return ab
        return None

    real_stat = os.stat
    real_lstat = os.lstat
    real_open = os.open
    real_builtin = builtins.open

    def guarded_stat(path, *args, **kwargs):
        hit = _hit(path)
        if hit:
            touched.append(hit)
        return real_stat(path, *args, **kwargs)

    def guarded_lstat(path, *args, **kwargs):
        hit = _hit(path)
        if hit:
            touched.append(hit)
        return real_lstat(path, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        hit = _hit(path)
        if hit:
            touched.append(hit)
        return real_open(path, flags, *args, **kwargs)

    def guarded_builtin(file, *args, **kwargs):
        hit = _hit(file)
        if hit:
            touched.append(hit)
        return real_builtin(file, *args, **kwargs)

    monkeypatch.setattr(os, "stat", guarded_stat)
    monkeypatch.setattr(os, "lstat", guarded_lstat)
    monkeypatch.setattr(os, "open", guarded_os_open)
    monkeypatch.setattr(builtins, "open", guarded_builtin)
    return touched


def test_extensionless_parent_import_is_reported(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    secret = outside / "secret"
    notes = outside / "notes.md"
    secret.write_text("SECRET-BODY\n", encoding="utf-8")
    notes.write_text("NOTES-BODY\n", encoding="utf-8")
    repo.mkdir()
    (repo / "CLAUDE.md").write_text(
        "@../outside/secret\n@../outside/notes.md\n",
        encoding="utf-8",
    )
    touched = _guard_paths(monkeypatch, {str(secret), str(notes)})
    res, out = _review(repo)
    raws = [r["raw"] for r in res["pointers"]["receipts"]]
    secret_hit = next(r for r in res["pointers"]["receipts"] if r["raw"] == "@../outside/secret")
    assert "leaves the repo" in secret_hit["receipt"]
    assert "@../outside/notes.md" in raws
    assert "SECRET-BODY" not in out and "NOTES-BODY" not in out
    assert touched == []


def test_tilde_import_is_reported_and_not_read(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    secret = home / "secret"
    secret_md = home / "secret.md"
    secret.write_text("TILDE-SECRET\n", encoding="utf-8")
    secret_md.write_text("TILDE-SECRET-MD\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("@~/secret\n@~/secret.md\n", encoding="utf-8")

    real_expanduser = os.path.expanduser

    def expanduser(path):
        if isinstance(path, str) and path == "~":
            return str(home)
        if isinstance(path, str) and path.startswith("~/"):
            return str(home / path[2:])
        return real_expanduser(path)

    monkeypatch.setattr(os.path, "expanduser", expanduser)
    touched = _guard_paths(monkeypatch, {str(secret), str(secret_md)})
    res, out = _review(repo)
    raws = {r["raw"] for r in res["pointers"]["receipts"]}
    assert "@~/secret" in raws
    assert "@~/secret.md" in raws
    for row in res["pointers"]["receipts"]:
        if row["raw"] in {"@~/secret", "@~/secret.md"}:
            assert "leaves the repo" in row["receipt"]
    assert "TILDE-SECRET" not in out
    load = doorway.repo_load(str(repo))
    loaded = {d["file"] for d in load["docs"]}
    assert "CLAUDE.md" in loaded
    assert not any("secret" in f for f in loaded)
    assert touched == []


def test_relative_import_that_normalizes_outside_is_reported(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    secret = outside / "secret"
    secret.write_text("NORM-SECRET\n", encoding="utf-8")
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Readme\n", encoding="utf-8")
    (repo / "docs" / "CLAUDE.md").write_text(
        "@../../outside/secret\n@../README.md\n",
        encoding="utf-8",
    )
    touched = _guard_paths(monkeypatch, {str(secret)})
    res, out = _review(repo)
    secret_hit = next(r for r in res["pointers"]["receipts"] if "outside/secret" in r["raw"])
    assert secret_hit["raw"] == "@../../outside/secret"
    assert "leaves the repo" in secret_hit["receipt"]
    assert not any(r["raw"] == "@../README.md" for r in res["pointers"]["receipts"])
    assert "NORM-SECRET" not in out
    assert touched == []


def test_npm_scope_is_not_graded_as_an_import(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text(
        "Many lint errors (`@typescript-eslint/no-explicit-any`) pre-exist.\n"
        "Also @typescript-eslint/no-explicit-any in prose.\n",
        encoding="utf-8",
    )
    res, _out = _review(repo)
    blob = " ".join(r["raw"] for r in res["pointers"]["receipts"])
    blob += " ".join(g.get("raw", "") for g in res["pointers"]["unverified_paths"])
    assert "typescript-eslint" not in blob
    assert "no-explicit-any" not in blob
    assert res["pointers"]["broken"] == 0


def _copy_case(tmp_path, name):
    src = _CASES / name
    dest = tmp_path / name
    shutil.copytree(src / "repo", dest / "repo", symlinks=True)
    shutil.copytree(src / "canary", dest / "canary", symlinks=True)
    return dest / "repo", dest / "canary"


def test_negated_line_still_reports_a_reference_that_leaves_the_repo(tmp_path, monkeypatch):
    repo, canary = _copy_case(tmp_path, "case16-negation")
    secret = canary / "no.md"
    touched = _guard_paths(monkeypatch, {str(secret)})
    res, out = _review(repo)
    hit = next(r for r in res["pointers"]["receipts"] if "canary/no.md" in r["raw"])
    assert "outside" in hit["receipt"]
    assert "MARKER_CASE16_HELICON_LEAK" not in out
    assert touched == []


def test_hostname_with_parent_segments_is_reported_when_it_leaves_the_repo(tmp_path, monkeypatch):
    repo, canary = _copy_case(tmp_path, "case15-hostname")
    secret = canary / "h.md"
    touched = _guard_paths(monkeypatch, {str(secret)})
    res, out = _review(repo)
    hit = next(
        r for r in res["pointers"]["receipts"]
        if "evil.example.com" in r["raw"] or "canary/h.md" in r["raw"]
    )
    assert "outside" in hit["receipt"]
    assert "MARKER_CASE15_HELICON_LEAK" not in out
    assert touched == []


def test_in_repo_import_is_scanned_only_for_references_that_leave(tmp_path, monkeypatch):
    repo, canary = _copy_case(tmp_path, "case08-import-chain")
    helper = repo / "docs" / "helper.md"
    helper.write_text(
        helper.read_text(encoding="utf-8").rstrip("\n")
        + "\nSee `docs/not-here.md` for the local note.\n",
        encoding="utf-8",
    )
    secret = canary / "hidden.md"
    touched = _guard_paths(monkeypatch, {str(secret)})
    res, out = _review(repo)
    hit = next(r for r in res["pointers"]["receipts"] if "canary/hidden.md" in r["raw"])
    assert "helper.md:" in hit["receipt"]
    assert "outside" in hit["receipt"]
    assert not any("not-here.md" in r["raw"] or "not-here.md" in r["receipt"]
                   for r in res["pointers"]["receipts"])
    assert "MARKER_CASE08_HELICON_LEAK" not in out
    assert touched == []
