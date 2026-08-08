"""The three surviving Cursor P1s on the governed-run surface.

Each was re-verified against current code before being fixed, not taken from the
review doc on trust. (F-C05, the cost field, was genuinely closed already: real
parse_session_cost wiring is in place and 'unknown' is never rendered as 0.)

F-C03  accept_run validated the verdict string and the run's status and NOTHING
       else. No artifact-integrity check, and /run/accept added none — so a
       human could accept a run while the viewer was showing a hash-mismatch
       block. For an integrity product, acceptance not being bound to the thing
       reviewed is the sharpest claim on the board.

F-C02  autogov built the observed manifest as {path, state, observed_at} with no
       content hash, so the Run viewer served mutable current file content as
       capture-time truth. attach_artifact's own docstring already promised the
       opposite ("a path+mtime alone can never masquerade as proof"), and the
       imported path (capture._artifacts) already delivered it.

F-C04  the same manifest is `git diff base..HEAD` + `git status --porcelain` —
       repo-wide, not session-scoped — so a concurrent session's edits are
       attributed to this run. git cannot know who wrote a line; what a ledger
       owes the signer is to SAY so.
"""
import json
import os
import subprocess

import pytest

from helicon import autogov, taskrun
from helicon.db import init_db


def _repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "a.py").write_text("print('one')\n")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=r, check=True)
    return r


@pytest.fixture
def run(tmp_path):
    """A governed run with a hashed manifest, at the point of acceptance."""
    conn = init_db(str(tmp_path / "t.db"))
    repo = _repo(tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()
    rid = taskrun.open_run(conn, "ship the thing", "tests pass",
                           repo_ref=f"{repo}@{head}")
    taskrun.build_packet(conn, rid, query="thing")
    import hashlib
    body = (repo / "src" / "a.py").read_bytes()
    taskrun.attach_artifact(conn, rid, [{
        "path": "src/a.py", "state": "committed", "observed_at": "2026-07-28",
        "content_hash": hashlib.sha256(body).hexdigest()[:16]}])
    return conn, rid, repo


# ------------------------------------------------------------------- F-C03
def test_an_unchanged_artifact_accepts_normally(run):
    conn, rid, _repo_path = run
    res = taskrun.accept_run(conn, rid, "accepted")
    assert res["human_acceptance"] == "accepted"
    assert res["artifact_integrity"]["ok"] is True
    assert res["artifact_integrity"]["checked"] == 1


def test_accepting_a_changed_artifact_is_refused(run):
    """The defect in one line: the bytes moved, and 'accepted' would have been
    recorded against bytes nobody reviewed."""
    conn, rid, repo = run
    (repo / "src" / "a.py").write_text("print('something else entirely')\n")
    with pytest.raises(taskrun.TaskRunError) as e:
        taskrun.accept_run(conn, rid, "accepted")
    assert "changed since it was captured" in str(e.value)
    assert "src/a.py" in str(e.value)
    row = conn.execute("SELECT status, human_acceptance FROM task_runs WHERE id=?",
                       (rid,)).fetchone()
    assert row["status"] != "reviewed" and row["human_acceptance"] == "pending"


def test_a_deleted_artifact_is_refused_too(run):
    conn, rid, repo = run
    os.remove(repo / "src" / "a.py")
    with pytest.raises(taskrun.TaskRunError) as e:
        taskrun.accept_run(conn, rid, "accepted")
    assert "missing" in str(e.value)


def test_the_override_is_explicit_and_lands_on_the_record(run):
    """A permanent block would just teach people to route around the gate, so
    drift is overridable — but never silently. 'accepted something that had
    changed' has to be a fact in the run's history."""
    conn, rid, repo = run
    (repo / "src" / "a.py").write_text("print('two')\n")
    res = taskrun.accept_run(conn, rid, "accepted", note="reviewed the diff",
                             accept_changed_artifact=True)
    assert res["human_acceptance"] == "accepted"
    assert res["artifact_integrity"]["ok"] is False
    kinds = [r["kind"] for r in conn.execute(
        "SELECT kind FROM run_events WHERE task_run_id=? ORDER BY id", (rid,))]
    assert "integrity_override" in kinds
    ev = conn.execute("SELECT detail FROM run_events WHERE task_run_id=? "
                      "AND kind='integrity_override'", (rid,)).fetchone()
    assert json.loads(ev["detail"])["mismatched"][0]["path"] == "src/a.py"


def test_integrity_is_filed_on_every_verdict_not_just_the_happy_one(run):
    """What was true about the artifact at the moment of the ruling is part of
    the ruling."""
    conn, rid, _r = run
    taskrun.accept_run(conn, rid, "rework", note="not yet")
    ev = conn.execute("SELECT detail FROM run_events WHERE task_run_id=? "
                      "AND kind='integrity'", (rid,)).fetchone()
    assert json.loads(ev["detail"])["checked"] == 1


def test_rework_and_rollback_are_not_gated(run):
    """They are not endorsements — refusing them on drift would block the exact
    verdict a changed artifact deserves."""
    conn, rid, repo = run
    (repo / "src" / "a.py").write_text("print('changed')\n")
    assert taskrun.accept_run(conn, rid, "rework")["human_acceptance"] == "rework"


def test_a_manifest_path_cannot_escape_the_recorded_repo(tmp_path):
    """A manifest is data, not a promise. An entry pointing outside the repo it
    was captured against would make the integrity check read — and rule on — a
    file the run never touched, and a matching hash there would read as clean.
    Containment came from the integration-nightrun lane; this is its test."""
    conn = init_db(str(tmp_path / "t.db"))
    repo = _repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("print('not this run')\n")
    import hashlib
    rid = taskrun.open_run(conn, "o", "a", repo_ref=f"{repo}@HEAD")
    taskrun.build_packet(conn, rid)
    taskrun.attach_artifact(conn, rid, [{
        "path": "../outside.py", "state": "committed",
        "content_hash": hashlib.sha256(outside.read_bytes()).hexdigest()[:16]}])
    integrity = taskrun.verify_artifact(conn, rid)
    assert integrity["ok"] is False
    assert integrity["mismatched"][0]["actual"] == "path escapes the recorded repo"
    # and the escape is a refusal at acceptance, not a warning
    with pytest.raises(taskrun.TaskRunError):
        taskrun.accept_run(conn, rid, "accepted")


def test_an_unhashed_entry_is_reported_not_counted_as_a_pass(tmp_path):
    """Legacy manifests carry no hash. They cannot be bound to anything, and the
    count says how much of the artifact the verdict actually covers — rather
    than an empty check reading as a clean one."""
    conn = init_db(str(tmp_path / "t.db"))
    repo = _repo(tmp_path)
    rid = taskrun.open_run(conn, "o", "a", repo_ref=f"{repo}@HEAD")
    taskrun.build_packet(conn, rid)
    taskrun.attach_artifact(conn, rid, [{"path": "src/a.py", "state": "committed"}])
    integrity = taskrun.verify_artifact(conn, rid)
    assert integrity["unhashable"] == 1 and integrity["checked"] == 0


# ------------------------------------------------------------------- F-C02
def test_the_observed_manifest_carries_a_content_hash(tmp_path, monkeypatch):
    conn = init_db(str(tmp_path / "t.db"))
    repo = _repo(tmp_path)
    monkeypatch.setattr(autogov, "_safe_repo_root", lambda cwd: str(repo))
    monkeypatch.setattr(autogov, "_is_private", lambda p: False)
    assert autogov.session_start(conn, str(repo), "sess1")["ok"]
    (repo / "src" / "b.py").write_text("print('new file')\n")
    out = autogov.session_stop(conn, "sess1")
    assert out["ok"]
    manifest = json.loads(conn.execute(
        "SELECT artifact_manifest FROM task_runs WHERE id=?",
        (out["task_run_id"],)).fetchone()[0])
    entry = next(m for m in manifest if m["path"].endswith("b.py"))
    assert entry["content_hash"], "a path+mtime alone cannot be proof"
    import hashlib
    assert entry["content_hash"] == hashlib.sha256(
        (repo / "src" / "b.py").read_bytes()).hexdigest()[:16]


# ------------------------------------------------------------------- F-C04
def test_the_manifest_never_claims_to_be_session_scoped(tmp_path, monkeypatch):
    conn = init_db(str(tmp_path / "t.db"))
    repo = _repo(tmp_path)
    monkeypatch.setattr(autogov, "_safe_repo_root", lambda cwd: str(repo))
    monkeypatch.setattr(autogov, "_is_private", lambda p: False)
    autogov.session_start(conn, str(repo), "sessA")
    (repo / "src" / "c.py").write_text("x = 1\n")
    out = autogov.session_stop(conn, "sessA")
    manifest = json.loads(conn.execute(
        "SELECT artifact_manifest FROM task_runs WHERE id=?",
        (out["task_run_id"],)).fetchone()[0])
    assert all(m["attribution"] == "repo-diff (not session-scoped)"
               for m in manifest)
    assert out["manifest_scope"] == "repo-wide"


def test_a_concurrent_session_on_the_same_repo_is_named(tmp_path, monkeypatch):
    """Two terminals in one repo is the fleet case this module exists for —
    _find_open keys on session id precisely so they do not collide — so the
    other session's edits WILL be in this manifest. Say whose they might be."""
    conn = init_db(str(tmp_path / "t.db"))
    repo = _repo(tmp_path)
    monkeypatch.setattr(autogov, "_safe_repo_root", lambda cwd: str(repo))
    monkeypatch.setattr(autogov, "_is_private", lambda p: False)
    a = autogov.session_start(conn, str(repo), "sessA")
    b = autogov.session_start(conn, str(repo), "sessB")
    assert a["ok"] and b["ok"]
    (repo / "src" / "d.py").write_text("y = 2\n")
    out = autogov.session_stop(conn, "sessA")
    assert b["task_run_id"] in out["concurrent_runs"]
    ev = conn.execute("SELECT detail FROM run_events WHERE task_run_id=? "
                      "AND kind='scope'", (out["task_run_id"],)).fetchone()
    detail = json.loads(ev["detail"])
    assert detail["manifest_scope"] == "repo-wide"
    assert b["task_run_id"] in detail["concurrent_runs"]
    assert "probably theirs" in detail["note"]
