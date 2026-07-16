"""Live guard: the agent consults the law before it writes.

Hermetic: seed a rename + an identity ruling, assert the guard blocks a
ruled-against claim and a dead-name claim, and passes clean output. This is
rulings-become-law made enforceable at write time.
"""
import pytest

from helicon.db import init_db, insert_cube, insert_audit
from helicon.models import AuditResult, ConnectorResult
from helicon.scanner import result_to_cube
from helicon.aliases import add_alias
from helicon.identity import identity_scan, resolve_identity
from helicon.pairing import resolve_pair
from helicon.guard import guard_output


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


def _cube(conn, content, ref):
    r = ConnectorResult(source="obsidian", source_ref=ref, type="memory",
                        title=ref, content=content, created_at="2026-07-01T00:00:00")
    insert_cube(conn, result_to_cube(r))
    conn.commit()


def _file_factual(conn, subject, topic, values):
    """File a factual (claim) conflict finding the way claim_scan does, so
    resolve_pair can rule it. Returns the audit id."""
    finding = AuditResult(
        audit_type="factual", target_type="cube", target_id="gc_x",
        finding=f"Cross-source claim conflict: {topic} [{subject}]",
        severity="critical", proposed_action="flag",
        details={"pair_key": f"claim|{topic}|{subject}", "person": subject,
                 "topic": topic, "dates": values, "all_dates": values,
                 "value_a": values[0], "value_b": values[1],
                 "support": {v: 1 for v in values}, "judged_by": "deterministic"},
        audited_at="2026-07-06T00:00:00",
    )
    insert_audit(conn, finding)
    conn.commit()
    return conn.execute("SELECT id FROM audit_log WHERE audit_type='factual'").fetchone()[0]


def test_dead_name_is_flagged(conn):
    add_alias(conn, "RELAY", "FAVOUR", "2026-07-02T00:00:00", note="rebrand executed")
    res = guard_output(conn, "RELAY just shipped its points sink this week.")
    assert res["clean"] is False
    assert any(v["rule"] == "rename" and "FAVOUR" in v["message"] for v in res["violations"])


def test_ruled_identity_is_blocked(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    resolve_identity(conn, aid, "a yield treasury")     # canonical = treasury
    res = guard_output(conn, "Yieldbound is a wallet tracker that reads balances.")
    assert res["verdict"] == "blocked"                  # a critical ruling contradicts it
    assert any(v["rule"] == "identity-ruling" for v in res["violations"])


def test_clean_output_passes(conn):
    add_alias(conn, "RELAY", "FAVOUR", "2026-07-02T00:00:00")
    res = guard_output(conn, "FAVOUR is live with real money.")
    assert res["clean"] is True and res["verdict"] == "clean"


def test_ruled_wrong_fact_is_blocked(conn):
    aid = _file_factual(conn, "hackathon", "wins", ["4", "9"])
    resolve_pair(conn, aid, "9")                          # human rules wins = 9
    res = guard_output(conn, "4 hackathon wins")
    assert res["verdict"] == "blocked"
    assert any(v["rule"] == "ruled-fact" and "4" in v["message"]
               for v in res["violations"])


def test_reasserting_the_ruled_truth_fact_is_clean(conn):
    aid = _file_factual(conn, "hackathon", "wins", ["4", "9"])
    resolve_pair(conn, aid, "9")
    assert guard_output(conn, "9 hackathon wins")["clean"] is True


def test_ruled_fact_no_false_positive_on_canonical_line(conn):
    # The canonical true line names BOTH 9 (wins) and 4 (a different metric).
    # The 4 quantifies "finalist placements", never "wins" — must stay clean.
    aid = _file_factual(conn, "hackathon", "wins", ["4", "9"])
    resolve_pair(conn, aid, "9")
    res = guard_output(conn, "9 hackathon wins, 4 finalist placements, $115K prizes")
    assert res["clean"] is True


def test_reasserting_the_ruled_truth_is_clean(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    resolve_identity(conn, aid, "a yield treasury")
    res = guard_output(conn, "Yieldbound is a yield treasury.")
    assert res["clean"] is True                         # the canonical definition passes
