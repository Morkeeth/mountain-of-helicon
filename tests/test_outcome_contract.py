"""Outcome Contract — the promise a run makes before it earns the right to start.

Pins the honesty properties: no field is invented, a blank field reads as
missing (never fake-present), the observable-outcome core is tracked separately
from the recommended fields, and the contract round-trips through the run store
without touching a run's A/B identity hash.
"""
import json

import pytest

from helicon import outcome_contract as oc
from helicon import taskrun as tr
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "oc.db"))


def test_empty_contract_reports_everything_missing():
    v = oc.validate({})
    assert v["complete"] is False
    assert v["present"] == []
    assert set(v["missing"]) == set(oc.FIELDS)
    assert set(v["missing_required"]) == set(oc.REQUIRED)
    assert v["has_beneficiary"] is False
    assert v["observable"] is False


def test_blank_and_whitespace_values_are_treated_as_absent():
    v = oc.validate({"beneficiary": "  ", "observable_change": "", "evidence_source": None})
    assert v["contract"] == {}
    assert "beneficiary" in v["missing_required"]


def test_unknown_keys_are_dropped_not_stored():
    c = oc.normalize({"beneficiary": "Oscar", "vibes": "high", "": "x"})
    assert c == {"beneficiary": "Oscar"}


def test_observable_needs_both_change_and_evidence():
    assert oc.validate({"observable_change": "signups rise"})["observable"] is False
    assert oc.validate({"evidence_source": "analytics"})["observable"] is False
    both = oc.validate({"observable_change": "signups rise", "evidence_source": "analytics"})
    assert both["observable"] is True


def test_complete_contract_is_complete():
    full = {f: f"val-{f}" for f in oc.FIELDS}
    v = oc.validate(full)
    assert v["complete"] is True
    assert v["missing"] == [] and v["missing_recommended"] == []


def test_dumps_of_empty_is_none_not_empty_object():
    assert oc.dumps({}) is None
    assert oc.dumps({"beneficiary": "Oscar"}) == json.dumps({"beneficiary": "Oscar"}, sort_keys=True)


def test_from_kwargs_keeps_only_known_nonempty():
    c = oc.from_kwargs(beneficiary="Oscar", time_horizon="", decision_owner="Oscar", junk="x")
    assert c == {"beneficiary": "Oscar", "decision_owner": "Oscar"}


# --- storage round-trip on the run spine --------------------------------------

def test_open_run_persists_and_reloads_the_contract(conn):
    contract = {"beneficiary": "Oscar", "observable_change": "fewer stale memories",
                "evidence_source": "helicon audit", "decision_owner": "Oscar",
                "time_horizon": "this week"}
    rid = tr.open_run(conn, "prune the stale tail", "the stale count drops",
                      outcome_contract=contract)
    stored = conn.execute(
        "SELECT outcome_contract FROM task_runs WHERE id=?", (rid,)).fetchone()[0]
    assert oc.loads(stored) == contract


def test_open_run_without_contract_stores_null(conn):
    rid = tr.open_run(conn, "obj", "acc")
    assert conn.execute(
        "SELECT outcome_contract FROM task_runs WHERE id=?", (rid,)).fetchone()[0] is None


def test_contract_does_not_change_task_identity_hash(conn):
    """Two runs, same task, different beneficiaries → same A/B identity hash.
    The contract is intent metadata, not task identity."""
    base = dict(task_class="draft", model="m", harness="h", skill_versions=["s@1"])
    a = tr.open_run(conn, "obj", "acc", outcome_contract={"beneficiary": "Oscar"}, **base)
    b = tr.open_run(conn, "obj", "acc", outcome_contract={"beneficiary": "the team"}, **base)
    ha = conn.execute("SELECT task_spec_hash FROM task_runs WHERE id=?", (a,)).fetchone()[0]
    hb = conn.execute("SELECT task_spec_hash FROM task_runs WHERE id=?", (b,)).fetchone()[0]
    assert ha == hb
