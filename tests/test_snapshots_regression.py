"""R8: what counts as a retrieval regression, and what is the product working.

`regressed` used to be `dropped or added or reordered or stale` — ANY change at
all. On the live store that read 12/13 "regressed" and `report` printed DEGRADED
off the same count, because 16 of 17 missing baseline memories were missing for
the best possible reason: Helicon had killed them as rot and retrieval correctly
stopped serving them. The one command a judge runs in thirty seconds indicted
the product for succeeding.

Nothing covered check_snapshot before this file, which is why it shipped.
"""
import json

import pytest

from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube
from helicon.snapshots import check_snapshot, init_snapshot_table


def _cube(conn, cid, title, content, status="approved", confidence=1.0):
    insert_cube(conn, HeliconCube(
        id=cid, source="claude-code", source_ref=f"ref_{cid}", type="memory",
        title=title, content=content, content_hash=cid,
        created_at="2026-07-01T00:00:00", valid_from="2026-07-01T00:00:00",
        review_status=status, confidence=confidence))
    conn.commit()


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "helicon.db"))
    init_snapshot_table(c)
    return c


def _snap(conn, task, ids, titles, k=3):
    conn.execute(
        "INSERT INTO context_snapshots (task, cube_ids, titles, top_k, created_at, note) "
        "VALUES (?, ?, ?, ?, ?, '')",
        (task, json.dumps(ids), json.dumps(titles), k, "2026-07-09T00:00:00"))
    conn.commit()
    return conn.execute("SELECT * FROM context_snapshots ORDER BY id DESC LIMIT 1").fetchone()


def _fake_retrieve(monkeypatch, hits):
    monkeypatch.setattr("helicon.snapshots._retrieve",
                        lambda conn, task, k: [{"id": i, "title": t} for i, t in hits])


def test_a_baseline_memory_killed_as_rot_is_not_a_regression(conn, monkeypatch):
    """THE bug. Retrieval filters killed memory at the source, so a killed
    baseline CANNOT come back and must not. Calling that regression means the
    exam fails every time the product does its job."""
    _cube(conn, "gc_keep", "kept", "still true")
    _cube(conn, "gc_rot", "rotten", "was wrong", status="killed")
    snap = _snap(conn, "task", ["gc_keep", "gc_rot"], ["kept", "rotten"])
    _fake_retrieve(monkeypatch, [("gc_keep", "kept")])

    res = check_snapshot(conn, snap)
    assert res["regressed"] is False, "killing rot was reported as a regression"
    assert res["dropped_live"] == []
    assert ("rotten", "killed") in res["stale"]
    assert res["live_overlap"] == 1.0, "every LIVE baseline memory is still served"


@pytest.mark.parametrize("status,why", [
    ("killed", "killed"), ("superseded", "superseded"),
])
def test_every_retirement_reason_counts_as_the_loop_working(conn, monkeypatch, status, why):
    _cube(conn, "gc_live", "live", "true")
    _cube(conn, "gc_gone", "gone", "retired", status=status)
    snap = _snap(conn, "t", ["gc_live", "gc_gone"], ["live", "gone"])
    _fake_retrieve(monkeypatch, [("gc_live", "live")])
    res = check_snapshot(conn, snap)
    assert res["regressed"] is False
    assert ("gone", why) in res["stale"]


def test_a_decayed_memory_is_not_a_regression_either(conn, monkeypatch):
    _cube(conn, "gc_live", "live", "true")
    _cube(conn, "gc_faded", "faded", "old", confidence=0.01)
    snap = _snap(conn, "t", ["gc_live", "gc_faded"], ["live", "faded"])
    _fake_retrieve(monkeypatch, [("gc_live", "live")])
    res = check_snapshot(conn, snap)
    assert res["regressed"] is False
    assert ("faded", "decayed") in res["stale"]


def test_a_LIVE_memory_that_stopped_being_retrieved_IS_the_regression(conn, monkeypatch):
    """The narrow, honest signal: still live, still true, no longer served."""
    _cube(conn, "gc_a", "still here", "true and live")
    _cube(conn, "gc_b", "vanished", "true and live but no longer ranked")
    snap = _snap(conn, "t", ["gc_a", "gc_b"], ["still here", "vanished"])
    _fake_retrieve(monkeypatch, [("gc_a", "still here")])

    res = check_snapshot(conn, snap)
    assert res["regressed"] is True, "a live memory fell out and nothing flagged it"
    assert res["dropped_live"] == ["vanished"]
    assert res["stale"] == []
    assert res["live_overlap"] == 0.5


def test_a_new_memory_outranking_the_baseline_is_not_a_regression(conn, monkeypatch):
    """The store learning is not the store breaking. `added` alone used to flip
    the verdict to regressed."""
    _cube(conn, "gc_a", "baseline", "true")
    _cube(conn, "gc_new", "newer and better", "written yesterday")
    snap = _snap(conn, "t", ["gc_a"], ["baseline"])
    _fake_retrieve(monkeypatch, [("gc_new", "newer and better"), ("gc_a", "baseline")])

    res = check_snapshot(conn, snap)
    assert res["regressed"] is False, "a new memory ranking was called a regression"
    assert res["added"] == ["newer and better"]


def test_reordering_alone_is_not_a_regression(conn, monkeypatch):
    _cube(conn, "gc_a", "a", "x")
    _cube(conn, "gc_b", "b", "y")
    snap = _snap(conn, "t", ["gc_a", "gc_b"], ["a", "b"])
    _fake_retrieve(monkeypatch, [("gc_b", "b"), ("gc_a", "a")])
    res = check_snapshot(conn, snap)
    assert res["reordered"] is True
    assert res["regressed"] is False, "churn was called a regression"


def test_a_baseline_whose_memories_all_retired_is_a_fossil_not_a_pass(conn, monkeypatch):
    """It cannot regress because there is nothing live left to lose. Silently
    passing forever is how a dead test looks exactly like a healthy one."""
    _cube(conn, "gc_x", "gone", "rot", status="killed")
    snap = _snap(conn, "t", ["gc_x"], ["gone"])
    _fake_retrieve(monkeypatch, [])
    res = check_snapshot(conn, snap)
    assert res["fossil"] is True
    assert res["regressed"] is False


def test_overlap_decays_as_the_product_works_but_live_overlap_does_not(conn, monkeypatch):
    """`overlap` counts retired memories against the baseline, so it falls every
    time rot is killed. live_overlap is the number to read."""
    _cube(conn, "gc_live", "live", "true")
    for i in range(3):
        _cube(conn, f"gc_rot{i}", f"rot{i}", "wrong", status="killed")
    snap = _snap(conn, "t", ["gc_live", "gc_rot0", "gc_rot1", "gc_rot2"],
                 ["live", "rot0", "rot1", "rot2"])
    _fake_retrieve(monkeypatch, [("gc_live", "live")])
    res = check_snapshot(conn, snap)
    assert res["overlap"] == 0.25          # looks terrible
    assert res["live_overlap"] == 1.0      # is actually perfect
    assert res["regressed"] is False
