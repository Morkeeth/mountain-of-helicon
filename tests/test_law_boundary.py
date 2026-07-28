"""The machine / human law boundary — locked at the CONSUMER surfaces.

The valuation gate auto-retires findings with `machine_decision`, never
`human_decision`. Three downstream surfaces are supposed to draw only from
human judgment:

  · the compiled law        gold.py  -> audit_log WHERE human_decision IS NOT NULL
  · the triage rulebook     gold.py  -> rules WHERE status='approved' (human approve)
  · Q-value / utility       utility.update_reward, called only by review paths

If a machine decision leaked into any of them, Helicon would forge operator
judgment into its own law — the worst failure mode in this repo. `test_valuation`
already pins the COLUMN (a machine decision never writes `human_decision`). These
pin the same invariant at the surfaces that actually read it, so a future change
that loosens gold's query or wires the gate into reward is caught end to end.
"""
import pytest

from helicon import gold, valuation
from helicon.db import init_db
from helicon.utility import get_q_values_batch, init_utility_table


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "law.db"))


def _cube(conn, cid, status="pending"):
    conn.execute(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, review_status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, "test", "ref", "note", "t", "c", cid, "2026-07-01", "2026-07-01", status))
    conn.commit()


def _finding(conn, finding, target, audit_type="temporal", target_type="cube",
             human=None, details=None):
    import json
    cur = conn.execute(
        "INSERT INTO audit_log (audit_type, target_type, target_id, finding, "
        "severity, audited_at, human_decision, details) VALUES (?,?,?,?,?,?,?,?)",
        (audit_type, target_type, target, finding, "critical", "2026-07-01",
         human, json.dumps(details) if details else None))
    conn.commit()
    return cur.lastrowid


def test_auto_retired_finding_never_appears_in_compiled_law(conn):
    """Run the gate, then compile the ACTUAL law. A machine-retired finding must
    not surface as a rule; a genuine human ruling must (positive control, so the
    test fails if compilation is simply broken rather than correctly filtering).
    """
    # Human ruling -> should become law.
    _cube(conn, "c_live", status="pending")
    _finding(conn, "Stripe mode disagreement", target="c_live",
             audit_type="factual", human="resolved:live",
             details={"person": "Stripe", "topic": "mode",
                      "dates": ["test", "live"]})

    # Machine-retired finding (killed memory) -> must never reach the law.
    _cube(conn, "c_dead", status="killed")
    _finding(conn, "MACHINE_ONLY_MARKER drifted on a dead memory", target="c_dead",
             audit_type="factual")

    res = valuation.triage_open(conn, apply=True)
    assert res["auto_retired"] == 1, res

    law = gold.compile_gold(conn, {})

    # Positive control: the human ruling compiled.
    assert "Stripe mode = live" in law
    # The boundary: the machine-retired finding did not forge a rule.
    assert "MACHINE_ONLY_MARKER" not in law
    # And it was recorded as a MACHINE decision, human_decision left untouched.
    row = conn.execute(
        "SELECT human_decision, machine_decision FROM audit_log "
        "WHERE finding LIKE 'MACHINE_ONLY_MARKER%'").fetchone()
    assert row["human_decision"] is None
    assert row["machine_decision"] == "auto-retired"


def test_gate_moves_no_q_value(conn):
    """Reward flows only from human review. The auto-retirement of a finding must
    not create or move a memory's Q-value — otherwise the utility loop learns
    from the machine's own echo."""
    init_utility_table(conn)
    _cube(conn, "c_dead", status="killed")
    _finding(conn, "drifted", target="c_dead", audit_type="factual")

    before = conn.execute("SELECT COUNT(*) FROM memory_utility").fetchone()[0]
    valuation.triage_open(conn, apply=True)
    after = conn.execute("SELECT COUNT(*) FROM memory_utility").fetchone()[0]

    # No utility row is written by the gate...
    assert before == 0 and after == 0, "the gate must not touch Q-value"
    # ...so the cube still reads the uninformed prior, not a machine-learned value.
    from helicon.utility import DEFAULT_Q
    assert get_q_values_batch(conn, ["c_dead"]) == {"c_dead": DEFAULT_Q}


def test_gate_creates_no_triage_rule(conn):
    """The triage rulebook in the compiled law comes from human-approved rules
    only. A machine retirement must never add an approved rule."""
    _cube(conn, "c_dead", status="killed")
    _finding(conn, "drifted", target="c_dead", audit_type="factual")

    before = conn.execute(
        "SELECT COUNT(*) FROM rules WHERE status='approved'").fetchone()[0]
    valuation.triage_open(conn, apply=True)
    after = conn.execute(
        "SELECT COUNT(*) FROM rules WHERE status='approved'").fetchone()[0]

    assert before == 0 and after == 0


def test_undo_leaves_human_rulings_untouched(conn):
    """Undo reverses a machine batch only. A human ruling made in between must
    survive it — the boundary holds in both directions."""
    _cube(conn, "c_dead", status="killed")
    _finding(conn, "machine drifted", target="c_dead", audit_type="factual")
    valuation.triage_open(conn, apply=True)

    _cube(conn, "c_live", status="pending")
    hid = _finding(conn, "human ruled", target="c_live", audit_type="factual",
                   human="resolved:kept")

    valuation.undo(conn)

    row = conn.execute(
        "SELECT human_decision FROM audit_log WHERE id=?", (hid,)).fetchone()
    assert row["human_decision"] == "resolved:kept"
    # the machine finding is back in the open queue, not forged into law
    reopened = conn.execute(
        "SELECT human_decision, machine_decision FROM audit_log "
        "WHERE finding='machine drifted'").fetchone()
    assert reopened["human_decision"] is None
    assert reopened["machine_decision"] is None
