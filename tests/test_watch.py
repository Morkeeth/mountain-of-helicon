"""helicon watch: speak once on new drift, then silence.

The acceptance from the master doc: introduce drift, watch fires once, a
second run with nothing new stays quiet. Also: the cursor survives runs, rot
class flips are reported with receipts, and notification failure never
crashes a tick.
"""
import json
import os

import pytest

from helicon import watch as W
from helicon.aliases import add_alias
from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube


def _cube(conn, content, ref, created_at="2026-07-05T09:00:00"):
    r = ConnectorResult(source="claude-code", source_ref=ref, type="memory",
                        title=ref, content=content, created_at=created_at)
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_path = str(tmp_path / "data" / "helicon.db")
    conn = init_db(db_path)
    config = {"db_path": db_path, "connectors": {}}  # no connectors: no scan
    # never pop real desktop notifications from tests
    calls = []
    monkeypatch.setattr(W, "notify_macos", lambda t, m: calls.append((t, m)) or True)
    return conn, config, calls


def test_first_run_quiet_on_clean_store(env):
    conn, config, calls = env
    res = W.watch_once(conn, config)
    assert res["spoke"] is False
    assert res["baseline"] is True
    assert res["report_path"] is None
    assert calls == []


def test_first_run_baselines_a_store_with_old_findings(env):
    """A new watcher on a store with months of open findings must not greet
    the user with all of them — first run sets the cursor silently."""
    conn, config, calls = env
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | dinner |", "trips.md")
    first = W.watch_once(conn, config)  # pair_scan files the finding here
    assert first["baseline"] is True
    assert first["spoke"] is False and calls == []
    # and it stays quiet after, because nothing NEW arrived
    assert W.watch_once(conn, config)["spoke"] is False


def test_fires_once_on_new_drift_then_silence(env):
    conn, config, calls = env
    W.watch_once(conn, config)  # baseline cursor

    # drift arrives: two files disagree on a birthday (R1 material)
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | dinner |", "trips.md")

    fired = W.watch_once(conn, config)
    assert fired["spoke"] is True
    assert fired["new_findings"] >= 1
    assert any(f["id"] == "R1" and f["to"] == "ROT FOUND" for f in fired["flips"])
    assert os.path.exists(fired["report_path"])
    body = open(fired["report_path"]).read()
    assert "Lea" in body and "R1" in body
    assert len(calls) == 1

    again = W.watch_once(conn, config)  # nothing new
    assert again["spoke"] is False
    assert len(calls) == 1  # still exactly one notification


def test_cursor_persists_across_runs(env):
    conn, config, _ = env
    W.watch_once(conn, config)
    state = W.load_state(config)
    assert state["last_run"] is not None
    assert set(state["rot_verdicts"]) == {f"R{i}" for i in range(1, 14)}


def test_alias_drift_flips_r4(env):
    conn, config, _ = env
    add_alias(conn, "glaze", "helicon", "2026-07-04T17:05:45")
    W.watch_once(conn, config)  # baseline: alias clean (no refs)

    _cube(conn, "polish the glaze demo tonight", "stale.md",
          created_at="2026-07-05T09:00:00")  # post-rename, dead name only
    fired = W.watch_once(conn, config)
    assert fired["spoke"] is True
    assert any(f["id"] == "R4" and f["to"] == "ROT FOUND" for f in fired["flips"])


def test_report_dir_config_respected(env, tmp_path):
    conn, config, _ = env
    target = tmp_path / "vault"
    target.mkdir()
    config["watch"] = {"report_dir": str(target)}
    W.watch_once(conn, config)
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | dinner |", "trips.md")
    fired = W.watch_once(conn, config)
    assert fired["report_path"] == str(target / "drift-report.md")


def test_notification_failure_does_not_crash(env, monkeypatch):
    conn, config, _ = env
    monkeypatch.setattr(W, "notify_macos", lambda t, m: False)
    W.watch_once(conn, config)
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | dinner |", "trips.md")
    assert W.watch_once(conn, config)["spoke"] is True


def test_watch_tick_with_missing_report_dir_does_not_crashloop(env, tmp_path):
    """P1 from the audit: a bad report_dir crashed the tick after findings
    were filed but before the cursor advanced -> every cron tick re-crashed
    on the same drift. The dir is now created; a write failure is recorded
    and the cursor still advances."""
    conn, config, _ = env
    config["watch"] = {"report_dir": str(tmp_path / "does" / "not" / "exist")}
    W.watch_once(conn, config)
    _cube(conn, "| Lea birthday Jul 13 | from her list |", "mindmap.md")
    _cube(conn, "| Jul 18 | Lea birthday (Paris) | dinner |", "trips.md")
    fired = W.watch_once(conn, config)
    assert fired["spoke"] is True
    assert fired["report_path"] and os.path.exists(fired["report_path"])
    assert W.watch_once(conn, config)["spoke"] is False  # cursor advanced


def test_state_file_write_is_atomic(env):
    conn, config, _ = env
    W.watch_once(conn, config)
    assert not os.path.exists(W._state_path(config) + ".tmp")
    assert json.load(open(W._state_path(config)))["rot_verdicts"]


def test_cron_line_is_tagged_and_parameterized():
    line = W._cron_line("/repo", 6)
    assert line.startswith("0 */6 * * * cd /repo && ")
    assert "helicon.cli watch --quiet" in line
    assert W.CRON_TAG in line
