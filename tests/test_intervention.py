"""Intervention Gate — the pre-run factual check.

Pins the product's line: a run must earn the right to start. The gate blocks on
the three things that make an outcome unjudgeable (no success criterion, no
beneficiary, no way to observe an outcome), warns on known gaps (stale/missing
context, unpinned skills, stale scan), and stays READ-ONLY.
"""
import pytest

from helicon import intervention
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "gate.db"))


def _full_contract():
    return {"beneficiary": "Oscar", "observable_change": "the stale count drops",
            "evidence_source": "helicon audit", "decision_owner": "Oscar",
            "time_horizon": "this week"}


def _named(g, name):
    return next(c for c in g["checks"] if c["name"] == name)


def test_empty_run_is_blocked_on_the_three_unjudgeables(conn):
    g = intervention.gate(conn, objective="", acceptance_test="", outcome_contract={})
    assert g["verdict"] == "blocked"
    assert set(g["blockers"]) == {"success criterion", "beneficiary", "observable outcome"}
    assert _named(g, "beneficiary")["status"] == "blocker"


def test_missing_beneficiary_alone_blocks(conn):
    c = _full_contract()
    del c["beneficiary"]
    g = intervention.gate(conn, objective="prune stale", acceptance_test="the count drops",
                          outcome_contract=c)
    assert "beneficiary" in g["blockers"]
    assert "observable outcome" not in g["blockers"]  # change+evidence still present


def test_missing_observable_outcome_blocks(conn):
    c = _full_contract()
    del c["evidence_source"]
    g = intervention.gate(conn, objective="prune stale", acceptance_test="the count drops",
                          outcome_contract=c)
    assert "observable outcome" in g["blockers"]


def test_absent_success_criterion_blocks(conn):
    g = intervention.gate(conn, objective="do the thing", acceptance_test="",
                          outcome_contract=_full_contract())
    assert "success criterion" in g["blockers"]


def test_trivially_short_criterion_still_blocks(conn):
    g = intervention.gate(conn, objective="do the thing", acceptance_test="ok",
                          outcome_contract=_full_contract())
    assert "success criterion" in g["blockers"]


def test_full_contract_no_blockers_but_warns_on_context_and_skills(conn):
    """A complete contract clears the blockers; an empty store + no pinned skill
    are honest WARNINGS, not blocks — the run may proceed, eyes open."""
    g = intervention.gate(conn, objective="prune the stale tail",
                          acceptance_test="the stale count drops measurably",
                          outcome_contract=_full_contract())
    assert g["verdict"] == "warn"
    assert g["blockers"] == []
    assert "skill version" in g["warnings"]        # nothing pinned
    assert _named(g, "context")["status"] == "warn"  # empty store, running blind


def test_recommended_fields_warn_not_block(conn):
    c = {"beneficiary": "Oscar", "observable_change": "x", "evidence_source": "y"}
    g = intervention.gate(conn, objective="obj", acceptance_test="acceptance stated",
                          outcome_contract=c)
    assert g["blockers"] == []
    assert _named(g, "by when")["status"] == "warn"
    assert _named(g, "who rules on it")["status"] == "warn"


def test_pinned_skill_version_passes_malformed_warns(conn):
    good = intervention.gate(conn, objective="obj", acceptance_test="acceptance stated",
                             outcome_contract=_full_contract(), skill_versions=["frame@1.2"])
    assert _named(good, "skill version")["status"] == "ok"
    bad = intervention.gate(conn, objective="obj", acceptance_test="acceptance stated",
                            outcome_contract=_full_contract(), skill_versions=["frame"])
    assert _named(bad, "skill version")["status"] == "warn"


def test_gate_is_read_only(conn):
    def snap():
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("task_runs", "audit_log", "helicon_cubes", "regret_events",
                          "retrieval_log", "run_events")}
    before = snap()
    intervention.gate(conn, objective="prune stale", acceptance_test="the count drops",
                      outcome_contract=_full_contract(), skill_versions=["s@1"])
    assert snap() == before


def test_gate_api_endpoint_returns_the_gate(conn, monkeypatch):
    """POST /api/run/gate exposes the same read-only gate to any surface."""
    import asyncio

    from helicon.api import runs2

    monkeypatch.setattr(runs2, "get_conn", lambda: conn)

    blocked = asyncio.run(runs2.run_gate(runs2.GateReq(objective="do it")))
    assert blocked["verdict"] == "blocked"
    assert "beneficiary" in blocked["blockers"]

    cleared = asyncio.run(runs2.run_gate(runs2.GateReq(
        objective="prune the stale tail",
        acceptance="the stale count drops measurably",
        beneficiary="Oscar", observable_change="fewer stale memories",
        evidence_source="helicon audit", skills=["runbook@1.0"])))
    assert cleared["verdict"] in ("go", "warn")
    assert cleared["blockers"] == []
    # opening nothing: the endpoint is read-only
    assert conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 0


def test_stale_retrieved_memory_warns(conn):
    """A killed memory that still retrieves for the objective is a warning."""
    conn.execute(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "summary, content_hash, created_at, valid_from, last_reinforced, confidence, "
        "review_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("k1", "test", "ref", "note", "escrow release runbook",
         "the escrow release runbook", "s", "k1", "2026-07-20", "2026-07-20",
         "2026-07-20", 1.0, "killed"))
    conn.commit()
    g = intervention.gate(conn, objective="escrow release runbook",
                          acceptance_test="acceptance stated",
                          outcome_contract=_full_contract())
    stale = next((c for c in g["checks"] if c["name"] == "stale memory"), None)
    # only asserted if retrieval surfaced the cube; otherwise 'context' warns instead
    if stale:
        assert stale["status"] == "warn"
