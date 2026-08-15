"""What `helicon ci` is allowed to call a pass.

Assertions written from the task, before opening cmd_ci: the shipping command
must never print a green verdict over an exam it did not run. Two cold runs of
the published 0.1.0 wheel on 2026-08-15 (uvx --isolated, empty HOME) are what
these tests are written against:

    $ helicon ci --path /tmp/.../nonexistent-dir
      ...
      ✓ CI PASS (0/13 classes firing; fail-on=rot)      exit 0

    $ helicon ci --path /tmp/.../empty-dir
      ...
      ✓ CI PASS (0/13 classes firing; fail-on=rot)      exit 0

A path that is not there absolves the repo the user meant to check. "0 classes
firing" out of 0 classes graded is the same false green the exam already
refuses one class at a time (R2/R13 say UNMEASURED, not CLEAN) — the summary
line was the one place the rule was not applied.

The other direction is defended too: tests/fixtures/rotten-repo must keep
failing, and --fail-on none must keep never wedging anyone's CI.
"""
import os
import subprocess
import sys

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ROTTEN = os.path.join(FIXTURES, "rotten-repo")


def run_ci(path, home, *extra):
    """Drive the shipping command, not the library under it. HOME is redirected
    so the exam grades the repo named on --path and not the runner's own store."""
    env = dict(os.environ, HOME=str(home))
    env.pop("GITHUB_ACTIONS", None)
    return subprocess.run(
        [sys.executable, "-m", "helicon", "ci", "--path", str(path), *extra],
        capture_output=True, text=True, env=env,
    )


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def empty_repo(tmp_path):
    """No instruction file, no git, nothing to grade. An ordinary shape for a
    stranger's first run — and nothing about it is evidence of health."""
    r = tmp_path / "empty-repo"
    r.mkdir()
    return r


def test_a_path_that_does_not_exist_is_not_a_pass(tmp_path, home):
    missing = tmp_path / "no-such-repo"
    res = run_ci(missing, home)
    assert "CI PASS" not in res.stdout, (
        "a typo in --path was reported as a clean repo:\n" + res.stdout[-600:])
    assert res.returncode != 0, "a nonexistent path exited 0"
    assert "no-such-repo" in (res.stdout + res.stderr)


def test_a_path_that_does_not_exist_says_so_in_a_sentence(tmp_path, home):
    """Not a traceback, and not an errno — the same bar the exam's receipts hold."""
    res = run_ci(tmp_path / "no-such-repo", home)
    out = res.stdout + res.stderr
    assert "Traceback" not in out, out[-800:]
    assert "Errno" not in out, out[-800:]


def test_an_empty_repo_is_unmeasured_not_clean(empty_repo, home):
    res = run_ci(empty_repo, home)
    assert "CI PASS" not in res.stdout, (
        "an exam that graded nothing reported a pass:\n" + res.stdout[-600:])
    assert "UNMEASURED" in res.stdout
    assert res.returncode != 0, "0 of 13 classes graded exited 0"


def test_report_only_still_never_wedges_a_stranger_ci(empty_repo, home):
    """--fail-on none is report-only. It may say UNMEASURED; it may not exit red."""
    res = run_ci(empty_repo, home, "--fail-on", "none")
    assert res.returncode == 0, res.stdout[-600:]
    assert "CI PASS" not in res.stdout


def test_planted_rot_still_fails(home):
    """The other direction. A gate that cannot fail is decoration."""
    res = run_ci(ROTTEN, home)
    assert "CI FAIL" in res.stdout, res.stdout[-800:]
    assert res.returncode == 1, res.stdout[-800:]


def test_planted_rot_is_report_only_under_fail_on_none(home):
    res = run_ci(ROTTEN, home, "--fail-on", "none")
    assert res.returncode == 0, res.stdout[-600:]
