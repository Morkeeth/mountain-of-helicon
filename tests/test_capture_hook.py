"""The Claude Stop hook reminds, but never writes or blocks an open capture."""
import json
import os
import subprocess

from helicon.workgraph_capture import launch
from helicon.db import init_db
from helicon.demo import seed
from helicon.wager import open_wager


def test_claude_capture_stop_hook_reports_an_unclosed_agentic_run(tmp_path):
    db = str(tmp_path / "hook.db")
    seed(db)
    conn = init_db(db)
    wager = open_wager(conn, intent="hook test", beneficiary="operator", observable_change="reminder",
                       evidence_contract="hook JSON", kill_condition="hook writes")
    launch(conn, wager, acceptance_test="test", query="none")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = os.path.join(root, "scripts", "claude-capture-reminder.sh")
    result = subprocess.run([script], input=json.dumps({"cwd": root}), text=True,
                            env={**os.environ, "HELICON_CAPTURE_DB": db}, capture_output=True, check=True)
    payload = json.loads(result.stdout)
    assert "helicon_capture_closeout" in payload["systemMessage"]
    assert conn.execute("SELECT status FROM task_runs").fetchone()[0] == "executing"
