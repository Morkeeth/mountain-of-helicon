"""Safe pointer rewrites and the one-page report."""
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from helicon.fix import apply_fixes, plan_fixes, render_diff
from helicon.page import render_page
from helicon.pointers import _TREE_CACHE
from helicon.review import main as review_main, review, review_summary


def _repo(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp()
    for rel, text in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _TREE_CACHE.clear()
    return root


def test_dry_run_names_the_unique_file_and_does_not_write():
    root = _repo({
        "AGENTS.md": "See `docs/old.md` before you edit.\n",
        "notes/old.md": "moved\n",
    })
    before = (Path(root) / "AGENTS.md").read_text()
    planned = apply_fixes(root, apply=False)
    assert planned[0]["replacement"] == "notes/old.md"
    assert planned[0]["written"] is False
    diff = render_diff(root, planned)
    assert "--- a/AGENTS.md" in diff
    assert "notes/old.md" in diff
    assert (Path(root) / "AGENTS.md").read_text() == before
    shutil.rmtree(root)


def test_apply_writes_only_the_unique_match():
    root = _repo({
        "AGENTS.md": "See `docs/old.md` before you edit.\n",
        "notes/old.md": "moved\n",
    })
    written = apply_fixes(root, apply=True)
    assert written[0]["written"] is True
    assert (Path(root) / "AGENTS.md").read_text() == "See `notes/old.md` before you edit.\n"
    shutil.rmtree(root)


def test_two_matches_are_not_a_safe_fix():
    root = _repo({
        "AGENTS.md": "See `docs/old.md`.\n",
        "notes/old.md": "a\n",
        "other/old.md": "b\n",
    })
    assert plan_fixes(root) == []
    assert "`docs/old.md`" in (Path(root) / "AGENTS.md").read_text()
    shutil.rmtree(root)


def test_missing_name_is_left_alone():
    root = _repo({"AGENTS.md": "See `docs/gone.md`.\n", "README.md": "hi\n"})
    assert plan_fixes(root) == []
    shutil.rmtree(root)


def test_page_shows_grade_three_problems_and_a_copy_button():
    root = _repo({
        "AGENTS.md": "\n".join([
            "One `docs/a.md` here.",
            "Two `docs/b.md` here.",
            "Three `docs/c.md` here.",
            "Four `docs/d.md` here.",
        ]) + "\n",
        "keep/a.md": "a\n",
        "keep/b.md": "b\n",
        "keep/c.md": "c\n",
        "keep/d.md": "d\n",
    })
    summary = review_summary(root, review(root, execute=False))
    page = render_page(root, summary)
    assert f'<p class="grade">{summary["grade"]}</p>' in page
    assert page.count("<article>") == 3
    assert page.count("Copy the fix") == 3
    assert "keep/a.md" in page
    assert "docs/d.md" not in page
    assert "navigator.clipboard.writeText" in page
    shutil.rmtree(root)


def test_review_html_writes_a_file(capsys):
    root = _repo({
        "AGENTS.md": "See `docs/old.md`.\n",
        "notes/old.md": "moved\n",
    })
    dest = os.path.join(root, "out", "report.html")
    code = review_main([root, "--html", dest])
    assert code == 1
    text = Path(dest).read_text()
    assert "Copy the fix" in text
    assert "notes/old.md" in text
    assert f"page: {dest}" in capsys.readouterr().out
    shutil.rmtree(root)


def _clean_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "SETUP.md").write_text("# setup\n")
    (repo / "CLAUDE.md").write_text("Read `docs/SETUP.md`.\n")
    _TREE_CACHE.clear()
    return repo


def test_default_html_refuses_a_symlink_and_leaves_the_outside_file(tmp_path, capsys):
    repo = _clean_repo(tmp_path)
    outside = tmp_path / "home" / ".zshrc"
    outside.parent.mkdir()
    original = b"# leave this file alone\n"
    outside.write_bytes(original)
    link = repo / "helicon-review.html"
    link.symlink_to(outside)

    code = review_main([str(repo), "--html"])

    captured = capsys.readouterr()
    assert code != 0
    assert outside.read_bytes() == original
    assert link.is_symlink()
    error = captured.err.strip()
    assert error
    assert "\n" not in error


def test_explicit_html_symlink_is_refused(tmp_path, capsys):
    repo = _clean_repo(tmp_path)
    target = tmp_path / "secret.txt"
    original = b"do not overwrite\n"
    target.write_bytes(original)
    link = tmp_path / "linked.html"
    link.symlink_to(target)

    code = review_main([str(repo), "--html", str(link)])

    captured = capsys.readouterr()
    assert code != 0
    assert target.read_bytes() == original
    assert link.is_symlink()
    error = captured.err.strip()
    assert error
    assert "\n" not in error


def _spell_through_system_symlink(path: Path) -> Path:
    """Use the /var or /tmp symlink when path already sits under its target.

    pytest's tmp_path is realpath'd to /private/var on macOS, so a test that
    uses it directly never walks the /var symlink. tempfile.mkdtemp does.
    """
    text = os.path.abspath(path)
    for link in ("/var", "/tmp"):
        if not os.path.islink(link):
            continue
        real = os.path.realpath(link)
        if text == real or text.startswith(real + os.sep):
            return Path(link + text[len(real):])
    return Path(text)


def test_explicit_html_outside_the_repo_is_written(tmp_path):
    repo = _clean_repo(tmp_path)
    dest = tmp_path / "out" / "page.html"

    code = review_main([str(repo), "--html", str(dest)])

    assert code == 0
    assert dest.is_file()
    assert not dest.is_symlink()
    assert "<!DOCTYPE html>" in dest.read_text()


def test_explicit_html_under_tmp_path_is_written(tmp_path):
    repo = _clean_repo(tmp_path)
    dest = _spell_through_system_symlink(tmp_path / "out" / "page.html")
    if os.path.islink("/var"):
        assert str(dest).startswith("/var" + os.sep)

    code = review_main([str(repo), "--html", str(dest)])

    assert code == 0
    written = Path(os.path.realpath(dest))
    assert written.is_file()
    assert not written.is_symlink()
    assert "<!DOCTYPE html>" in written.read_text()


def test_explicit_html_under_slash_tmp_is_written(tmp_path):
    repo = _clean_repo(tmp_path)
    dest = f"/tmp/helicon-review-{os.getpid()}-{uuid.uuid4().hex}.html"
    try:
        code = review_main([str(repo), "--html", dest])
        assert code == 0
        assert os.path.isfile(dest)
        assert not os.path.islink(dest)
        assert "<!DOCTYPE html>" in Path(dest).read_text()
    finally:
        if os.path.lexists(dest):
            os.remove(dest)
        assert not os.path.lexists(dest)


def test_default_html_on_a_clean_repo_is_written_inside_it(tmp_path):
    repo = _clean_repo(tmp_path)

    code = review_main([str(repo), "--html"])

    dest = repo / "helicon-review.html"
    assert code == 0
    assert dest.is_file()
    assert not dest.is_symlink()
    assert dest.resolve().parent == repo.resolve()
    assert "<!DOCTYPE html>" in dest.read_text()


def _one_line(capsys) -> str:
    captured = capsys.readouterr()
    text = f"{captured.out}{captured.err}".strip()
    assert text
    assert "\n" not in text
    return text


def test_apply_refuses_a_symlink_to_a_file_outside_the_repo(tmp_path, capsys, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "notes" / "old.md").write_text("moved\n")
    outside = tmp_path / "outside.md"
    original = b"See `docs/old.md` before you edit.\n"
    outside.write_bytes(original)
    (repo / "AGENTS.md").symlink_to(outside)
    _TREE_CACHE.clear()

    monkeypatch.setattr("sys.argv", ["helicon", "fix", "--apply", str(repo)])
    from helicon.cli import main
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code not in (0, None)
    assert "refus" in _one_line(capsys).lower()
    assert outside.read_bytes() == original
    assert (repo / "AGENTS.md").is_symlink()


def test_apply_rewrites_the_in_repo_target_of_claude_symlink(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "notes").mkdir(parents=True)
    (repo / "notes" / "old.md").write_text("moved\n")
    (repo / "AGENTS.md").write_text("See `docs/old.md` before you edit.\n")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    _TREE_CACHE.clear()

    monkeypatch.setattr("sys.argv", ["helicon", "fix", "--apply", str(repo)])
    from helicon.cli import main
    main()
    assert (repo / "AGENTS.md").read_text() == "See `notes/old.md` before you edit.\n"
    assert (repo / "CLAUDE.md").is_symlink()
    assert os.readlink(repo / "CLAUDE.md") == "AGENTS.md"

    # The row can name the symlink. The write still lands on the in-repo target.
    other = tmp_path / "named-link"
    (other / "notes").mkdir(parents=True)
    (other / "notes" / "old.md").write_text("moved\n")
    (other / "AGENTS.md").write_text("See `docs/old.md` before you edit.\n")
    (other / "CLAUDE.md").symlink_to("AGENTS.md")
    _TREE_CACHE.clear()
    apply_fixes(str(other), planned=[{
        "file": "CLAUDE.md",
        "line_no": 1,
        "raw": "`docs/old.md`",
        "replacement": "notes/old.md",
        "line": "",
    }], apply=True)
    assert (other / "AGENTS.md").read_text() == "See `notes/old.md` before you edit.\n"
    assert os.readlink(other / "CLAUDE.md") == "AGENTS.md"


def test_apply_refuses_a_file_under_a_directory_symlink(tmp_path, capsys, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original = b"See `docs/old.md` before you edit.\n"
    (outside / "AGENTS.md").write_bytes(original)
    (repo / "sub").symlink_to(outside, target_is_directory=True)
    _TREE_CACHE.clear()
    monkeypatch.setattr("helicon.fix.plan_fixes", lambda repo_root: [{
        "file": "sub/AGENTS.md",
        "line_no": 1,
        "raw": "`docs/old.md`",
        "replacement": "notes/old.md",
        "line": "",
    }])
    monkeypatch.setattr("sys.argv", ["helicon", "fix", "--apply", str(repo)])
    from helicon.cli import main
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code not in (0, None)
    assert "refus" in _one_line(capsys).lower()
    assert (outside / "AGENTS.md").read_bytes() == original
    assert (repo / "sub").is_symlink()


def test_explicit_html_inside_repo_parent_symlink_is_refused(tmp_path, capsys):
    repo = _clean_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_bytes(b"keep\n")
    link_parent = repo / "via-link"
    link_parent.symlink_to(outside, target_is_directory=True)
    dest = link_parent / "page.html"

    code = review_main([str(repo), "--html", str(dest)])

    assert code != 0
    assert not (outside / "page.html").exists()
    assert marker.read_bytes() == b"keep\n"
    assert link_parent.is_symlink()
    error = capsys.readouterr().err.strip()
    assert error
    assert "\n" not in error
    assert "refus" in error.lower()


def test_swapping_a_parent_after_the_walk_does_not_redirect_the_write(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    sub = repo / "sub"
    sub.mkdir(parents=True)
    (sub / "note.txt").write_text("before\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.txt").write_bytes(b"outside\n")

    import helicon.nofollow as nofollow
    real_open = os.open
    swapped = {"done": False}

    def swapping_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if (
            not swapped["done"]
            and path == "sub"
            and kwargs.get("dir_fd") is not None
            and flags & os.O_DIRECTORY
        ):
            swapped["done"] = True
            os.rename(sub, repo / "sub.real")
            sub.symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(nofollow.os, "open", swapping_open)
    with nofollow.open_nofollow(str(repo), "sub/note.txt", write=True) as fh:
        fh.write("rewritten\n")

    assert swapped["done"]
    assert (outside / "note.txt").read_bytes() == b"outside\n"
    assert not (outside / "note.txt").is_symlink()
    assert (repo / "sub.real" / "note.txt").read_text() == "rewritten\n"
    assert (repo / "sub").is_symlink()


def test_fix_needs_no_config(capsys, monkeypatch):
    root = _repo({
        "AGENTS.md": "See `docs/old.md`.\n",
        "notes/old.md": "moved\n",
    })
    monkeypatch.setattr("sys.argv", ["helicon", "fix", root])
    from helicon.cli import main
    main()
    out = capsys.readouterr().out
    assert "Nothing written" in out
    assert "notes/old.md" in out
    assert (Path(root) / "AGENTS.md").read_text().startswith("See `docs/old.md`")
    shutil.rmtree(root)
