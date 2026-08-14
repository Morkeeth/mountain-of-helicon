"""What `helicon ci` says to someone whose repo is not this one.

Written before reading R2's implementation, from the first run against
openai/codex on 2026-08-14: the exam printed

    R2  Doc-drift  UNMEASURED
        unmeasured: [Errno 2] No such file or directory:
        '/private/tmp/.../codex/CLAUDE.md'

on a repository that has a README and an AGENTS.md and simply no CLAUDE.md,
which is an ordinary shape. A stranger's first contact with the tool was a
filesystem error naming a directory on the runner's disk.

The rule these tests defend: no receipt in the exam may contain a traceback,
an errno, or an absolute path. A class that cannot run says so in a sentence.
"""
import subprocess
import sys

import pytest

from helicon.db import init_db
from helicon.rot import run_rot_exam


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


@pytest.fixture
def foreign_repo(tmp_path):
    """An ordinary repo that is not Mountain of Helicon. No CLAUDE.md, because
    that absence is what crashed the exam on openai/codex."""
    repo = tmp_path / "someone-elses-project"
    repo.mkdir()
    (repo / "README.md").write_text("# Someone else's project\n\nIt does a thing.\n")
    (repo / "AGENTS.md").write_text("# Rules\n\nRun the tests before pushing.\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return str(repo)


def _receipts(conn, repo_root):
    return {c["id"]: c["receipt"] for c in run_rot_exam(conn, repo_root=repo_root)["checks"]}


def test_no_receipt_leaks_a_path_or_a_traceback(conn, foreign_repo):
    """The whole exam, not only R2 — any class may be the one a stranger reads."""
    for rid, receipt in _receipts(conn, foreign_repo).items():
        assert "Errno" not in receipt, f"{rid} prints an errno at the user: {receipt}"
        assert "Traceback" not in receipt, f"{rid} prints a traceback: {receipt}"
        assert "/" not in receipt or not any(
            part.startswith("/") for part in receipt.split()
        ), f"{rid} prints an absolute path: {receipt}"


def test_r2_says_it_did_not_run_rather_than_reporting_clean(conn, foreign_repo):
    """A class that cannot grade a foreign repo must not be readable as a pass.
    UNMEASURED is the honest verdict; CLEAN would be a false green."""
    r2 = next(c for c in run_rot_exam(conn, repo_root=foreign_repo)["checks"]
              if c["id"] == "R2")
    assert r2["verdict"] == "UNMEASURED"
    assert r2["coverage"] == "PARTIAL"
    assert "unchecked, not clean" in r2["receipt"]


def test_scrub_keeps_the_reason_and_drops_the_machine():
    # imported here, not at module scope: the three tests above must be able to
    # run against a build that has no _scrub, which is how they were watched
    # failing on the published 0.1.0 behaviour.
    from helicon.rot import _scrub
    scrubbed = _scrub(FileNotFoundError(
        2, "No such file or directory", "/private/tmp/x/codex/CLAUDE.md"))
    assert "CLAUDE.md" in scrubbed
    assert "/private/tmp" not in scrubbed


@pytest.mark.skipif(sys.platform == "win32", reason="posix paths only")
def test_own_repo_still_grades_its_docs(conn):
    """The fix must not buy a clean stranger run by disabling R2 everywhere."""
    from pathlib import Path
    own = str(Path(__file__).resolve().parent.parent)
    r2 = next(c for c in run_rot_exam(conn, repo_root=own)["checks"] if c["id"] == "R2")
    assert r2["coverage"] == "TESTED"
