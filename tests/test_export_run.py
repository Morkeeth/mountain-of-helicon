"""helicon export — JSON dump of a governed TaskRun."""
import json

import pytest

from helicon.db import init_db
from helicon.taskrun import build_packet, export_run, open_run


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def test_export_run_roundtrip(conn):
    rid = open_run(conn, "export me", "json written", harness="test")
    build_packet(conn, rid, query="export")
    payload = export_run(conn, rid)
    assert payload["task_run_id"] == rid
    assert payload["run"]["objective"] == "export me"
    assert isinstance(payload["events"], list)
    assert isinstance(payload["packets"], list)
    assert "TaskRun" in payload["receipt"]
    # serializable
    json.dumps(payload, default=str)
