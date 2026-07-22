import asyncio

from helicon import taskrun
from helicon.api import app as _api_app  # initialize API modules in production order
from helicon.api import runs2
from helicon.db import init_db


def test_forward_taskrun_is_visible_in_list_and_detail(tmp_path, monkeypatch):
    conn = init_db(str(tmp_path / "runs.db"))
    rid = taskrun.open_run(
        conn,
        "Ship the forward path",
        "The pre-execution run is visible in the Cockpit",
        harness="claude-code",
        repo_ref="/tmp/project@abc123",
    )
    taskrun.build_packet(conn, rid, query="forward")
    monkeypatch.setattr(runs2, "get_conn", lambda: conn)

    listed = asyncio.run(runs2.run_list())
    assert listed["total"] == 1
    assert listed["needs_you"] == 1
    run = listed["runs"][0]
    assert run["task_run_id"] == rid
    assert run["provenance"] == "forward"
    assert run["repo"] == "/tmp/project"
    assert run["start_commit"] == "abc123"
    assert run["governed"]["acceptance_test"].startswith("The pre-execution")

    detailed = asyncio.run(runs2.run_detail(task_run_id=rid))
    assert detailed["ok"] is True
    assert detailed["run"]["task_run_id"] == rid
    assert [e["kind"] for e in detailed["run"]["events"]] == []
    assert detailed["run"]["receipt"].startswith(f"TaskRun {rid}")
