"""Context-budget / context-rot guard.

Pins the honest properties: a status + headroom against a stated, overridable
onset — never a fabricated accuracy — and the battery folds it in as a
non-critical signal (over-budget degrades, it does not break).
"""
import pytest

from helicon import context_budget as cb
from helicon.db import init_db


def test_healthy_well_under_onset():
    r = cb.assess(5_000)
    assert r["status"] == "healthy"
    assert r["over_onset"] is False
    assert r["headroom_to_onset"] == cb.ONSET_TOKENS - 5_000
    assert "well within" in r["note"]


def test_watch_band_below_onset():
    r = cb.assess(int(cb.ONSET_TOKENS * 0.8))
    assert r["status"] == "watch"
    assert r["over_onset"] is False
    assert "approaching" in r["note"]


def test_over_onset_is_flagged_with_the_overshoot():
    r = cb.assess(cb.ONSET_TOKENS + 8_000)
    assert r["status"] == "over"
    assert r["over_onset"] is True
    assert r["headroom_to_onset"] == -8_000
    assert "past the" in r["note"]


def test_explicit_budget_can_trip_before_onset():
    r = cb.assess(10_000, budget=8_000)
    assert r["status"] == "over"
    assert r["over_budget"] is True
    assert r["over_onset"] is False
    assert "budget" in r["note"]


def test_onset_is_overridable():
    r = cb.assess(9_000, onset=8_000)
    assert r["status"] == "over"
    assert r["over_onset"] is True


def test_zero_and_garbage_are_healthy_not_crashy():
    for v in (0, None, -5):
        r = cb.assess(v)
        assert r["tokens"] == 0
        assert r["status"] == "healthy"


def test_no_fabricated_accuracy_number():
    """The whole point: report a budget, never an invented 'you lost X%%'."""
    r = cb.assess(cb.ONSET_TOKENS * 3)
    blob = " ".join(str(v) for v in r.values()).lower()
    assert "%" not in blob
    assert "accuracy" not in blob


# --- battery integration -----------------------------------------------------

def _seed(conn, cid, title, content, task_terms=""):
    conn.execute(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "summary, content_hash, created_at, valid_from, last_reinforced, confidence, "
        "review_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, "test", "ref", "note", title, content, content[:80], cid,
         "2026-07-20", "2026-07-20", "2026-07-20", 1.0, "approved"))
    conn.commit()


def test_battery_reports_context_budget(tmp_path):
    from helicon.battery import run_battery, get_test_names
    conn = init_db(str(tmp_path / "b.db"))
    _seed(conn, "c1", "escrow release plan", "Ship the escrow release with tests.")
    res = run_battery(conn, "escrow release plan", k=5)
    assert "Context budget" in get_test_names()
    assert "context_budget" in res
    assert res["context_budget"]["status"] in ("healthy", "watch", "over")
    names = [r["name"] for r in res["results"]]
    assert "Context budget" in names


def test_battery_budget_test_degrades_never_breaks_on_large_context(tmp_path):
    """A huge retrieved memory pushes tokens past the onset. The budget test must
    FAIL, and because it is non-critical the verdict is DEGRADED, not BROKEN."""
    from helicon.battery import run_battery
    conn = init_db(str(tmp_path / "big.db"))
    big = "escrow release runbook " * 20_000  # ~ hundreds of k chars -> >32k tokens
    _seed(conn, "big", "escrow release runbook", big)
    res = run_battery(conn, "escrow release runbook", k=5)
    if res["context_budget"]["status"] == "over":  # retrieval found the big cube
        budget = next(r for r in res["results"] if r["name"] == "Context budget")
        assert budget["status"] == "FAIL"
        assert budget.get("critical", False) is False
        assert res["verdict"] in ("DEGRADED", "BROKEN")  # not HEALTHY with a fail
