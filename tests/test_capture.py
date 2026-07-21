"""Real Run Capture tests — capture real transcript facts (no fabrication),
govern the lifecycle, and promote a prompt ONLY on an accepted outcome."""
import json
import subprocess

import pytest

from helicon.db import init_db
from helicon import capture, taskrun


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)


def _make_session(tmp_path):
    repo = tmp_path / "helicon-fixture"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.email", "t@t.t"); _git(repo, "config", "user.name", "t")
    (repo / "f.py").write_text("x=1\n"); _git(repo, "add", "-A"); _git(repo, "commit", "-m", "base")
    proj = tmp_path / "projects"; proj.mkdir()
    jl = proj / "sess.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-07-22T00:00:00Z", "cwd": str(repo),
         "gitBranch": "main", "sessionId": "sess", "version": "2.1.0",
         "promptSource": "user", "message": {"role": "user", "content": "first real prompt"}},
        {"type": "assistant", "timestamp": "2026-07-22T00:01:00Z", "cwd": str(repo),
         "sessionId": "sess", "message": {"role": "assistant", "model": "claude-sonnet-5",
          "usage": {"input_tokens": 100, "output_tokens": 50,
                    "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5}}},
        {"type": "user", "timestamp": "2026-07-22T00:02:00Z", "cwd": str(repo),
         "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "user", "timestamp": "2026-07-22T00:03:00Z", "cwd": str(repo),
         "message": {"role": "user", "content": "second real prompt"}},
    ]
    jl.write_text("\n".join(json.dumps(x) for x in lines))
    return repo, str(jl)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def test_capture_real_facts_not_fabricated(conn, tmp_path, monkeypatch):
    repo, jl = _make_session(tmp_path)
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: str(repo))
    cap = capture.capture_session(conn, jl)
    assert cap["ok"] and cap["provenance"] == "imported"
    assert cap["prompts"] == 2  # the tool_result entry is skipped, only real prompts
    row = conn.execute("SELECT * FROM run_captures WHERE id=?", (cap["capture_id"],)).fetchone()
    prompts = [p["text"] for p in json.loads(row["prompt_chain"])]
    assert prompts == ["first real prompt", "second real prompt"]  # verbatim, in order
    assert row["model"] == "claude-sonnet-5"
    tokens = json.loads(row["tokens"])
    assert tokens["input"] == 100 and tokens["output"] == 50
    assert row["cost_status"] == "unknown"          # never fabricate a cost
    assert row["task_run_id"] is None               # imported: no governed wrapper yet
    # NO fabricated objective/acceptance from prose (that is what 'imported' means)
    assert conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 0


def test_govern_accept_promote_only_on_accepted(conn, tmp_path, monkeypatch):
    repo, jl = _make_session(tmp_path)
    monkeypatch.setattr(capture, "_safe_repo_root", lambda p, ar=None: str(repo))
    cap = capture.capture_session(conn, jl)
    g = capture.govern_from_capture(conn, cap["capture_id"], "obj", "acceptance frozen")
    assert g["ok"]
    rid = g["task_run_id"]
    # rework first -> no promotion
    taskrun.accept_run(conn, rid, "rework", note="not good enough")
    assert capture.promote_prompt(conn, rid)["ok"] is False
    assert conn.execute("SELECT COUNT(*) FROM prompt_library").fetchone()[0] == 0
    # accept -> promotes exactly one
    taskrun.accept_run(conn, rid, "accepted", note="good")
    assert capture.promote_prompt(conn, rid)["ok"] is True
    assert conn.execute("SELECT COUNT(*) FROM prompt_library").fetchone()[0] == 1
    # append-only history preserved (rework AND accepted both recorded)
    kinds = [e["kind"] for e in conn.execute(
        "SELECT kind FROM run_events WHERE task_run_id=? ORDER BY id", (rid,)).fetchall()]
    assert "rework" in kinds and "accepted" in kinds


def test_open_run_requires_acceptance(conn):
    with pytest.raises(taskrun.TaskRunError):
        taskrun.open_run(conn, "objective", "")  # empty acceptance is refused (P1)
