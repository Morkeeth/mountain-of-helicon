"""`helicon truth` and `helicon review` on a path that is missing or empty.

Found cold on 2026-10-11 with the published 0.2.4: `truth /nonexistent` printed
one line and exited 0; `truth <empty dir>` printed "store looks fresh" and exited 0;
`review /nonexistent` said "No agent instruction file found in this repo" and asked
the stranger to add AGENTS.md to a path that does not exist.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, "-m", "helicon", *args], cwd=ROOT,
                          capture_output=True, text=True, env=env, timeout=60)


def test_truth_missing_path_exits_nonzero_and_names_the_path():
    r = _run("truth", "/nonexistent/helicon-truth-path")
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "not a file or directory" in r.stderr
    assert "store looks fresh" not in r.stdout


def test_truth_empty_dir_says_nothing_scanned_and_exits_2(tmp_path):
    r = _run("truth", str(tmp_path))
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "0 files scanned" in r.stdout + r.stderr
    assert "store looks fresh" not in r.stdout
    assert "--recursive" in r.stdout + r.stderr


def test_truth_count_on_empty_dir_is_not_a_clean_zero(tmp_path):
    r = _run("truth", str(tmp_path), "--count")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)


def test_truth_on_a_file_still_works(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# fresh\n", encoding="utf-8")
    r = _run("truth", str(tmp_path))
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "1 files scanned" in r.stdout


def test_review_missing_path_says_so_and_exits_2():
    r = _run("review", "/nonexistent/helicon-review-path")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "No agent instruction file" not in r.stdout
    assert "/nonexistent/helicon-review-path" in r.stderr
    assert "not a directory" in r.stderr
