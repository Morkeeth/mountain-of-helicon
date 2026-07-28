"""Baselines expire, and that is what makes "CI for agent memory" hold up.

The product's novel core claim is that a captured baseline turns memory drift
into a regression signal. That claim was only true on the day the baseline was
seeded. All 13 baselines on the live store were captured 2026-07-09 and
2026-07-11 and were still being scored as current 18-20 days later, with no
refresh policy, no expiry, and no way to record WHY a baseline moved.

Three consequences, all measured on a copy of the real store:

  - every real change in memory looked like a regression forever, so
    "regression" and "legitimate drift" were indistinguishable (10 of 13
    "regressed", and nobody could say how many were the product working);
  - #28 'Search' read fossil: True with overlap 0.0 and still scored OK,
    because live_overlap over an empty set is 1.0 — a vacuous pass;
  - #16 asks for "RELAY project status and progress". RELAY was renamed to
    FAVOUR on 2026-07-02, BEFORE that baseline was captured, so the exam has
    been scoring retrieval on a question about a thing that no longer exists.

After the lifecycle, the same 13 report: 11 expired, 1 stale-task, 1 fossil.
Zero are still evidence — which is the honest reading, and it is deliberately
NOT the same as "zero regressions".
"""
import json

import pytest

from helicon.db import init_db
from helicon.snapshots import (SNAPSHOT_MAX_AGE_DAYS, check_all, check_snapshot,
                               init_snapshot_table, recapture_snapshot)
from helicon.timeutil import utc_now


def _snap(conn, task, ids, titles, age_days=0.0, k=3):
    from datetime import timedelta
    created = (utc_now() - timedelta(days=age_days)).isoformat()
    conn.execute(
        "INSERT INTO context_snapshots (task, cube_ids, titles, top_k, created_at, note) "
        "VALUES (?,?,?,?,?,'')",
        (task, json.dumps(ids), json.dumps(titles), k, created))
    conn.commit()
    return conn.execute(
        "SELECT * FROM context_snapshots ORDER BY id DESC LIMIT 1").fetchone()


def _cube(conn, cid, title, status="approved"):
    now = utc_now().isoformat()
    conn.execute(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, confidence, review_status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (cid, "test", f"ref/{cid}", "memory", title, "body", cid,
         now, now, 0.8, status))
    conn.commit()


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "t.db"))
    init_snapshot_table(c)
    return c


def _retrieves(monkeypatch, hits):
    monkeypatch.setattr("helicon.snapshots._retrieve",
                        lambda conn, task, k: [{"id": i, "title": t} for i, t in hits])


def test_a_fresh_baseline_that_lost_a_live_memory_is_a_regression(conn, monkeypatch):
    _cube(conn, "gc_a", "kept")
    _cube(conn, "gc_b", "vanished")
    snap = _snap(conn, "t", ["gc_a", "gc_b"], ["kept", "vanished"], age_days=1)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    res = check_snapshot(conn, snap)
    assert res["status"] == "regressed" and res["regressed"] is True


def test_the_same_drift_on_an_expired_baseline_is_not_a_regression(conn, monkeypatch):
    """The whole point. Past the shelf life a diff measures elapsed time, not
    retrieval quality — so it reports 'needs re-capture', never 'got worse'."""
    _cube(conn, "gc_a", "kept")
    _cube(conn, "gc_b", "vanished")
    snap = _snap(conn, "t", ["gc_a", "gc_b"], ["kept", "vanished"],
                 age_days=SNAPSHOT_MAX_AGE_DAYS + 5)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    res = check_snapshot(conn, snap)
    assert res["status"] == "expired"
    assert res["regressed"] is False
    assert res["needs_recapture"] is True
    assert res["age_days"] > SNAPSHOT_MAX_AGE_DAYS


def test_expired_is_not_the_same_as_clean(conn, monkeypatch):
    """An expired baseline must not read as a pass either. `needs_recapture`
    is how the report knows to treat it as unmeasured rather than healthy —
    the same distinction that made the old contra_rate-is-None a silent pass."""
    _cube(conn, "gc_a", "kept")
    snap = _snap(conn, "t", ["gc_a"], ["kept"], age_days=SNAPSHOT_MAX_AGE_DAYS + 1)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    res = check_snapshot(conn, snap)
    assert res["status"] == "expired" and res["needs_recapture"] is True
    assert res["status"] != "ok"


def test_a_fossil_baseline_stops_scoring_a_vacuous_pass(conn, monkeypatch):
    """#28 'Search': every baseline memory retired, overlap 0.0, and it scored
    OK because live_overlap over an empty set is 1.0."""
    _cube(conn, "gc_dead", "retired", status="killed")
    snap = _snap(conn, "Search", ["gc_dead"], ["retired"], age_days=1)
    _retrieves(monkeypatch, [("gc_other", "something else")])
    res = check_snapshot(conn, snap)
    assert res["fossil"] is True
    assert res["status"] == "fossil" and res["needs_recapture"] is True


def test_a_baseline_asking_for_a_renamed_entity_is_flagged(conn, monkeypatch):
    """#16 is 'RELAY project status and progress'. RELAY -> FAVOUR happened
    2026-07-02, before the baseline was captured. The alias table already knew;
    the exam did not ask it."""
    from helicon.aliases import add_alias
    add_alias(conn, "RELAY", "FAVOUR", "2026-07-02T00:00:00")
    _cube(conn, "gc_a", "kept")
    snap = _snap(conn, "RELAY project status and progress", ["gc_a"], ["kept"],
                 age_days=1)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    res = check_snapshot(conn, snap)
    assert res["status"] == "stale-task"
    assert res["stale_task"] == "RELAY -> FAVOUR"
    assert res["needs_recapture"] is True


def test_a_live_name_inside_a_word_is_not_a_false_positive(conn, monkeypatch):
    from helicon.aliases import add_alias
    add_alias(conn, "glaze", "helicon", "2026-07-04T17:05:45")
    _cube(conn, "gc_a", "kept")
    snap = _snap(conn, "glazed ceramics research", ["gc_a"], ["kept"], age_days=1)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    assert check_snapshot(conn, snap)["stale_task"] is None


# ------------------------------------------------- re-capture, with a reason
def test_recapture_requires_a_reason(conn, monkeypatch):
    """A baseline that can be silently overwritten is not evidence, it is an
    opinion that always agrees with today."""
    _cube(conn, "gc_a", "kept")
    snap = _snap(conn, "t", ["gc_a"], ["kept"], age_days=20)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    with pytest.raises(ValueError) as e:
        recapture_snapshot(conn, snap["id"], "  ")
    assert "needs a reason" in str(e.value)


def test_recapture_records_lineage_and_why(conn, monkeypatch):
    _cube(conn, "gc_a", "kept")
    old = _snap(conn, "Orchestrator Closeout", ["gc_a"], ["kept"], age_days=20)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    new = recapture_snapshot(conn, old["id"], "memory legitimately moved on")
    row = conn.execute("SELECT * FROM context_snapshots WHERE id=?",
                       (old["id"],)).fetchone()
    assert row["superseded_by"] == new["id"]
    fresh = conn.execute("SELECT * FROM context_snapshots WHERE id=?",
                         (new["id"],)).fetchone()
    assert fresh["rebaseline_reason"] == "memory legitimately moved on"
    assert fresh["as_of"] and fresh["stale_when"] == f"age > {SNAPSHOT_MAX_AGE_DAYS}d"
    assert fresh["task"] == old["task"]


def test_a_superseded_baseline_stops_being_an_exam_question(conn, monkeypatch):
    """It stays in the table as history — the lineage IS the record of why a
    baseline moved — but scoring both would double-count one task, and the
    older row can only ever look worse."""
    _cube(conn, "gc_a", "kept")
    old = _snap(conn, "t", ["gc_a"], ["kept"], age_days=20)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    recapture_snapshot(conn, old["id"], "why")
    ids = [r["snapshot_id"] for r in check_all(conn)]
    assert old["id"] not in ids
    assert old["id"] in [r["snapshot_id"] for r in
                         check_all(conn, include_superseded=True)]


def test_recapturing_twice_is_refused(conn, monkeypatch):
    _cube(conn, "gc_a", "kept")
    old = _snap(conn, "t", ["gc_a"], ["kept"], age_days=20)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    recapture_snapshot(conn, old["id"], "first")
    with pytest.raises(ValueError) as e:
        recapture_snapshot(conn, old["id"], "second")
    assert "already superseded" in str(e.value)


def test_a_recaptured_baseline_is_evidence_again(conn, monkeypatch):
    _cube(conn, "gc_a", "kept")
    old = _snap(conn, "t", ["gc_a"], ["kept"], age_days=20)
    _retrieves(monkeypatch, [("gc_a", "kept")])
    assert check_snapshot(conn, old)["status"] == "expired"
    recapture_snapshot(conn, old["id"], "re-seeded after the cleanup")
    live = check_all(conn)
    assert len(live) == 1 and live[0]["status"] == "ok"
    assert live[0]["needs_recapture"] is False


def test_the_migration_is_idempotent_on_an_existing_table(conn):
    """Real stores already have 13 rows without these columns."""
    init_snapshot_table(conn)
    init_snapshot_table(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(context_snapshots)")}
    assert {"as_of", "stale_when", "superseded_by", "rebaseline_reason"} <= cols
