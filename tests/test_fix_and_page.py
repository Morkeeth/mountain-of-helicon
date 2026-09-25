"""Safe pointer rewrites and the one-page report."""
import os
import shutil
import tempfile
from pathlib import Path

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


def test_explicit_html_outside_the_repo_is_written(tmp_path):
    repo = _clean_repo(tmp_path)
    dest = tmp_path / "out" / "page.html"

    code = review_main([str(repo), "--html", str(dest)])

    assert code == 0
    assert dest.is_file()
    assert not dest.is_symlink()
    assert "<!DOCTYPE html>" in dest.read_text()


def test_default_html_on_a_clean_repo_is_written_inside_it(tmp_path):
    repo = _clean_repo(tmp_path)

    code = review_main([str(repo), "--html"])

    dest = repo / "helicon-review.html"
    assert code == 0
    assert dest.is_file()
    assert not dest.is_symlink()
    assert dest.resolve().parent == repo.resolve()
    assert "<!DOCTYPE html>" in dest.read_text()


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
