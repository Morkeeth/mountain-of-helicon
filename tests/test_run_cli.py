"""Forward-governed run (helicon run) — freeze objective+acceptance+base BEFORE
work, attach the real diff at close, promote only on accept."""
import subprocess

import pytest

from helicon.db import init_db
from helicon import taskrun, capture
from helicon.cli import _diff_manifest, _latest_open_run


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(r)], check=True, capture_output=True, text=True)
    _git(r, "config", "user.email", "t@t.t"); _git(r, "config", "user.name", "t")
    (r / "a.py").write_text("x=1\n"); _git(r, "add", "-A"); _git(r, "commit", "-m", "base")
    return r


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def test_forward_run_freezes_before_and_attaches_real_diff(conn, repo):
    base = capture._git(str(repo), "rev-parse", "HEAD")
    rid = taskrun.open_run(conn, "obj", "acceptance frozen before work",
                           harness="claude-code", repo_ref=f"{repo}@{base}")
    taskrun.build_packet(conn, rid, query="obj")
    assert _latest_open_run(conn) == rid  # discoverable as the open run

    # work happens AFTER the freeze
    (repo / "a.py").write_text("x=2\n")
    (repo / "new.py").write_text("print('new')\n")
    manifest = _diff_manifest(str(repo), base)
    paths = {m["path"] for m in manifest}
    assert "a.py" in paths and "new.py" in paths
    assert all(m["content_hash"] for m in manifest)  # a path+mtime alone is never proof

    taskrun.attach_artifact(conn, rid, manifest)
    taskrun.accept_run(conn, rid, "accepted", note="works")
    assert _latest_open_run(conn) is None  # reviewed -> no longer open
    pr = capture.promote_prompt(conn, rid, by="operator-ruling")
    assert pr["ok"] is True
    # a forward run with no transcript promotes its objective as the prompt
    assert conn.execute("SELECT prompt FROM prompt_library WHERE task_run_id=?",
                        (rid,)).fetchone()["prompt"] == "obj"


def test_rejected_forward_run_does_not_promote(conn, repo):
    base = capture._git(str(repo), "rev-parse", "HEAD")
    rid = taskrun.open_run(conn, "obj", "acceptance", harness="claude-code",
                           repo_ref=f"{repo}@{base}")
    taskrun.build_packet(conn, rid, query="obj")
    taskrun.attach_artifact(conn, rid, _diff_manifest(str(repo), base))
    taskrun.accept_run(conn, rid, "rollback", note="no good")
    assert capture.promote_prompt(conn, rid)["ok"] is False
    assert conn.execute("SELECT COUNT(*) FROM prompt_library").fetchone()[0] == 0
