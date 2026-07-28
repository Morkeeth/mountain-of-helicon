"""Reflection — a real day of runs, rolled up honestly.

Pins the properties that make it a reflection rather than a vibe: it counts the
day's real runs and outcomes, it never fabricates a cost (unknown stays
unknown), and an empty day says so.
"""
import json

import pytest

from helicon import reflection
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "reflect.db"))


def _run(conn, rid, opened_at, *, acceptance="pending", model="probe",
         task_class="", artifacts=None, cost=None, objective="obj"):
    conn.execute(
        "INSERT INTO task_runs (id, objective, task_class, acceptance_test, model, "
        "harness, human_acceptance, opened_at, status, artifact_manifest, "
        "cost_observation) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (rid, objective, task_class, "acc", model, "claude-code", acceptance,
         opened_at, "reviewed", json.dumps(artifacts or []),
         json.dumps(cost) if cost is not None else None))
    conn.commit()


def _card(conn, rid, start, *, score=1.0, cost=2.0, output_tokens=1000):
    conn.execute(
        "INSERT INTO run_cards (run_id, start, end, duration_min, model, "
        "session_count, output_tokens, total_tokens, verified, checkable, "
        "verified_ratio, cost, damage, score, scored_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, start, start, 30, "probe", 1, output_tokens, output_tokens * 2,
         1, 1, 1.0, cost, 0, score, start))
    conn.commit()


def test_empty_store_reflects_nothing_without_fabricating(conn):
    d = reflection.day_reflection(conn)
    assert d["has_activity"] is False
    assert d["day"] is None
    assert d["totals"]["runs"] == 0
    assert d["headline"]  # a headline is always stated


def test_day_rolls_up_runs_and_outcomes(conn):
    day = "2026-07-18"
    _run(conn, "r1", f"{day}T09:00:00", acceptance="accepted",
         artifacts=[{"path": "a.py"}, {"path": "b.py"}])
    _run(conn, "r2", f"{day}T10:00:00", acceptance="pending")
    _run(conn, "r3", f"{day}T11:00:00", acceptance="rework")
    # a run on a DIFFERENT day must not bleed in
    _run(conn, "r_other", "2026-07-17T09:00:00", acceptance="accepted")

    d = reflection.day_reflection(conn, day=day)
    assert d["day"] == day and d["has_activity"] is True
    t = d["totals"]
    assert t["runs"] == 3
    assert t["accepted"] == 1 and t["rework"] == 1 and t["needs_verdict"] == 1
    assert len(d["runs"]) == 3
    r1 = next(r for r in d["runs"] if r["id"] == "r1")
    assert r1["outcome"] == "accepted" and r1["artifacts"] == 2


def test_unknown_cost_is_never_counted_as_zero(conn):
    day = "2026-07-18"
    _run(conn, "known", f"{day}T09:00:00",
         cost={"status": "known", "total_tokens": 4200})
    _run(conn, "unknown", f"{day}T10:00:00", cost={"status": "unknown"})
    _run(conn, "missing", f"{day}T11:00:00", cost=None)

    d = reflection.day_reflection(conn, day=day)
    assert d["totals"]["known_tokens"] == 4200
    assert d["totals"]["unknown_cost_runs"] == 2
    statuses = {r["id"]: r["cost_status"] for r in d["runs"]}
    assert statuses == {"known": "known", "unknown": "unknown", "missing": "unknown"}


def test_default_day_is_the_latest_with_activity(conn):
    _run(conn, "old", "2026-07-16T09:00:00", acceptance="accepted")
    _run(conn, "new", "2026-07-18T09:00:00", acceptance="pending")
    d = reflection.day_reflection(conn)
    assert d["day"] == "2026-07-18"
    assert [r["id"] for r in d["runs"]] == ["new"]


def test_malformed_start_never_becomes_the_day(conn):
    """A non-date start (some seeded/legacy run_cards carry 'run-2026-...') must
    not be picked as the latest day — only well-formed YYYY-MM-DD counts."""
    _run(conn, "real", "2026-07-18T09:00:00", acceptance="pending")
    _card(conn, "run-2026-07-19", "run-2026-07-19T20:00:00")  # malformed start
    assert reflection.latest_activity_day(conn) == "2026-07-18"


def test_scored_cards_and_rulings_join_the_same_day(conn):
    day = "2026-07-18"
    _card(conn, "c1", f"{day}T20:00:00", score=0.8, cost=3.0, output_tokens=5000)
    _card(conn, "c2", f"{day}T21:00:00", score=0.4, cost=1.0, output_tokens=1000)
    conn.execute(
        "INSERT INTO govern_batches (id, applied_at, rulings_json, receipt_json, "
        "undo_json) VALUES ('gb1', ?, '[]', '[]', '{}')", (f"{day}T21:30:00",))
    conn.commit()

    d = reflection.day_reflection(conn, day=day)
    assert d["scored"]["cards"] == 2
    assert d["scored"]["output_tokens"] == 6000
    assert d["scored"]["avg_score"] == 0.6
    assert d["scored"]["total_cost"] == 4.0
    assert d["rulings_applied"] == 1
    assert d["has_activity"] is True


def test_an_undone_ruling_is_not_counted(conn):
    day = "2026-07-18"
    _card(conn, "c1", f"{day}T20:00:00")
    conn.execute(
        "INSERT INTO govern_batches (id, applied_at, undone_at, rulings_json, "
        "receipt_json, undo_json) VALUES ('gb1', ?, ?, '[]', '[]', '{}')",
        (f"{day}T21:30:00", f"{day}T22:00:00"))
    conn.commit()
    d = reflection.day_reflection(conn, day=day)
    assert d["rulings_applied"] == 0


def test_format_is_readable_and_names_the_day(conn):
    day = "2026-07-18"
    _run(conn, "r1", f"{day}T09:00:00", acceptance="pending",
         objective="ship the thing")
    text = reflection.format_day_reflection(reflection.day_reflection(conn, day=day))
    assert day in text
    assert "need" in text.lower()
    assert "ship the thing" in text


def test_brief_embeds_the_day_reflection(conn):
    """The brief's Reflection pillar carries the day roll-up and a day-aware
    headline, without dropping any of the five top-level pillars."""
    from helicon.brief import build_brief

    day = "2026-07-18"
    _run(conn, "r1", f"{day}T09:00:00", acceptance="pending")
    b = build_brief(conn, {})
    assert set(b) == {"truth", "continuity", "direction", "reflection", "calm"}
    assert b["reflection"]["today"]["day"] == day
    assert b["reflection"]["today"]["totals"]["needs_verdict"] == 1
    assert "Today" in b["reflection"]["headline"]
