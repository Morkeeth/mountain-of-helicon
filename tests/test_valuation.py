"""The valuation gate — govern-by-exception.

The properties that matter are not "it reduces the number". A gate that reduces
the number is easy; a gate that reduces it without eating a real finding, and
without forging law, is the product. These pin both halves.
"""
import pytest

from helicon import valuation
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "v.db"))


def _cube(conn, cid, status="pending"):
    conn.execute(
        "INSERT INTO helicon_cubes (id, source, source_ref, type, title, content, "
        "content_hash, created_at, valid_from, review_status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, "test", "ref", "note", "t", "c", cid, "2026-07-01", "2026-07-01", status))
    conn.commit()


def _finding(conn, finding="something drifted", target="c1", audit_type="temporal",
             target_type="cube", human=None):
    cur = conn.execute(
        "INSERT INTO audit_log (audit_type, target_type, target_id, finding, "
        "severity, audited_at, human_decision) VALUES (?,?,?,?,?,?,?)",
        (audit_type, target_type, target, finding, "critical", "2026-07-01", human))
    conn.commit()
    return cur.lastrowid


def _open_ids(conn):
    return [r[0] for r in conn.execute(
        "SELECT id FROM audit_log WHERE human_decision IS NULL "
        "AND machine_decision IS NULL")]


def test_finding_on_a_killed_memory_never_reaches_the_human(conn):
    """The 68% case in the real store: a ruling on a dead memory changes nothing."""
    from helicon.db import get_audit_results

    _cube(conn, "c1", status="killed")
    fid = _finding(conn, target="c1")
    valuation.triage_open(conn, apply=True)
    assert fid not in _open_ids(conn)
    assert get_audit_results(conn, pending_only=True) == []


def test_finding_on_a_live_memory_still_reaches_the_human(conn):
    """The gate must not be a mute button. A live memory's drift is still a question."""
    _cube(conn, "c1", status="pending")
    fid = _finding(conn, target="c1")
    valuation.triage_open(conn, apply=True)
    assert fid in _open_ids(conn)


def test_a_rename_the_operator_ruled_resolves_itself(conn):
    conn.execute("INSERT INTO entity_aliases (old_name, new_name, renamed_at, note, "
                 "created_at) VALUES ('glaze','helicon','2026-07-04','rename','2026-07-04')")
    conn.commit()
    _cube(conn, "c1")
    fid = _finding(conn, finding="dead path: /CODE/glaze/x.py is gone", target="c1")
    valuation.triage_open(conn, apply=True)
    assert fid not in _open_ids(conn)


def test_a_new_measurement_is_not_silenced_by_an_old_dismissal(conn):
    """A duration can cross a meaningful threshold, so changed evidence returns
    to the human even when the subject and finding shape otherwise match."""
    _cube(conn, "c1")
    _finding(conn, finding="Routine 'scout' silent for 61.9h", target="c1",
             audit_type="routine", human="dismissed: expected")
    fid = _finding(conn, finding="Routine 'scout' silent for 87.3h", target="c1",
                   audit_type="routine")
    valuation.triage_open(conn, apply=True)
    assert fid in _open_ids(conn)


def test_an_exact_dismissed_precedent_does_not_come_back(conn):
    _cube(conn, "c1")
    finding = "Routine 'scout' silent for 61.9h"
    _finding(conn, finding=finding, target="c1",
             audit_type="routine", human="dismissed: expected")
    fid = _finding(conn, finding=f"  {finding.upper()}  ", target="c1",
                   audit_type="routine")
    valuation.triage_open(conn, apply=True)
    assert fid not in _open_ids(conn)


def test_alias_matching_never_uses_substrings(conn):
    conn.execute(
        "INSERT INTO entity_aliases "
        "(old_name, new_name, renamed_at, note, created_at) "
        "VALUES ('art','new-art','2026-07-04','rename','2026-07-04')"
    )
    conn.commit()
    _cube(conn, "c1")
    fid = _finding(
        conn,
        finding="Missing path validation: a partial deployment remains unverified",
        target="c1",
    )
    valuation.triage_open(conn, apply=True)
    assert fid in _open_ids(conn)


def test_a_dismissal_about_one_subject_does_not_silence_another(conn):
    """The regression that mattered. `_normalize` blurred every digit, so
    dismissing a finding about status_2026-07-03.md retired the findings about
    status_2026-07-06/08/14/15/18.md — five true findings eaten by one
    dismissal. A gate that hides real findings is worse than no gate, because
    the operator then trusts a queue that lies by omission.
    """
    _cube(conn, "c1")
    _finding(conn, finding="Memory points at a dead path: status_2026-07-03.md is gone",
             target="c1", audit_type="output", human="dismissed: expected")
    fid = _finding(conn, finding="Memory points at a dead path: status_2026-07-18.md is gone",
                   target="c1", audit_type="output")
    valuation.triage_open(conn, apply=True)
    assert fid in _open_ids(conn), "a different file is a different fact"


def test_a_dismissal_about_one_routine_does_not_silence_another(conn):
    """Same class of bug, the shape my own test originally asserted as correct:
    'scout' being expectedly silent says nothing about 'track'."""
    _cube(conn, "c1")
    _finding(conn, finding="Routine 'scout' silent for 61.9h", target="c1",
             audit_type="routine", human="dismissed: expected")
    fid = _finding(conn, finding="Routine 'track' silent for 61.9h", target="c1",
                   audit_type="routine")
    valuation.triage_open(conn, apply=True)
    assert fid in _open_ids(conn), "a different routine is a different fact"


def test_machine_decisions_never_write_human_decision(conn):
    """gold.py compiles the Golden Rules from human_decision. If the gate wrote
    there, every auto-retirement would forge a ruling into the stack's law."""
    _cube(conn, "c1", status="killed")
    _finding(conn, target="c1")
    valuation.triage_open(conn, apply=True)
    forged = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE human_decision IS NOT NULL").fetchone()[0]
    assert forged == 0


def test_dry_run_writes_nothing(conn):
    _cube(conn, "c1", status="killed")
    _finding(conn, target="c1")
    before = _open_ids(conn)
    res = valuation.triage_open(conn, apply=False)
    assert res["auto_retired"] == 1
    assert _open_ids(conn) == before


def test_undo_restores_every_retired_finding(conn):
    """The gate is a judgment call on the operator's attention. If it cannot be
    reversed in one command it is not a gate, it is a deletion."""
    _cube(conn, "c1", status="killed")
    _finding(conn, target="c1")
    _finding(conn, finding="another", target="c1")
    before = len(_open_ids(conn))
    valuation.triage_open(conn, apply=True)
    assert len(_open_ids(conn)) == 0
    assert valuation.undo(conn) == before
    assert len(_open_ids(conn)) == before


def test_undo_only_restores_the_latest_valuation_batch(conn):
    _cube(conn, "c1", status="killed")
    first = _finding(conn, target="c1")
    batch1 = valuation.triage_open(conn, apply=True)["batch_id"]
    second = _finding(conn, finding="second", target="c1")
    batch2 = valuation.triage_open(conn, apply=True)["batch_id"]
    unrelated = _finding(conn, finding="other machine", target="c1")
    conn.execute(
        "UPDATE audit_log SET machine_decision='other-system', "
        "machine_batch_id='other' WHERE id=?", (unrelated,)
    )
    conn.commit()

    assert batch1 != batch2
    assert valuation.undo(conn) == 1
    assert second in _open_ids(conn)
    assert first not in _open_ids(conn)
    assert conn.execute(
        "SELECT machine_decision FROM audit_log WHERE id=?", (unrelated,)
    ).fetchone()[0] == "other-system"


def test_applying_twice_is_idempotent(conn):
    _cube(conn, "c1", status="killed")
    _finding(conn, target="c1")
    valuation.triage_open(conn, apply=True)
    second = valuation.triage_open(conn, apply=True)
    assert second["considered"] == 0



def test_retired_memory_is_unreachable_on_every_agent_facing_path(tmp_path):
    """Codex's A1, pinned. The gate retires a finding on the grounds that its
    memory is killed/superseded and therefore cannot reach an agent. That
    reasoning is only sound while EVERY retrieval path agrees. `taskrun`'s
    ContextPacket excluded 'killed' but happily packed 'superseded', so a
    memory explicitly replaced by a newer one could still be delivered into a
    governed run while search_cubes and embeddings both refused to serve it.

    Uses the demo seed because the packet applies a sensitivity gate: cubes with
    synthetic sources are dropped before the status filter is ever reached, which
    made an earlier hand-rolled version of this test pass against the bug.
    """
    from helicon.demo import seed
    from helicon import taskrun

    db = str(tmp_path / "seeded.db")
    seed(db)
    conn = init_db(db)
    conn.execute("UPDATE helicon_cubes SET review_status='superseded' WHERE id='demo-stripe-test'")
    conn.execute("UPDATE helicon_cubes SET review_status='killed' WHERE id='demo-stripe-live'")
    conn.commit()

    rid = taskrun.open_run(conn, "stripe objective", "acceptance", harness="test",
                           repo_ref="/tmp/x@abc")
    taskrun.build_packet(conn, rid, query="stripe")
    packed = {r[0] for r in conn.execute(
        "SELECT cube_id FROM context_packet_items WHERE cube_id IS NOT NULL")}

    assert packed, "fixture is vacuous: the packet must contain something to be a real check"
    assert "demo-stripe-live" not in packed, "killed memory must not reach an agent"
    assert "demo-stripe-test" not in packed, "superseded memory must not reach an agent either"


def test_retired_memory_is_excluded_from_active_derived_surfaces(conn):
    """A dead cube must not leak back through summaries, repair, or playbooks.

    The valuation gate auto-handles findings about retired memories only because
    those memories are unreachable. Keep that premise pinned across every
    derived surface that can shape an agent or create a new memory.
    """
    import json

    from helicon.consolidation import find_clusters
    from helicon.heal import _active_cubes
    from helicon.playbooks import _get_feedback_from_cubes
    from helicon.portrait import _areas, _output_mix, _recent
    from helicon.volatility import find_suspects

    for cid, status in (("dead-k", "killed"), ("dead-s", "superseded")):
        conn.execute(
            "INSERT INTO helicon_cubes "
            "(id, source, source_ref, type, title, content, summary, tags, "
            "content_hash, created_at, valid_from, review_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, "obsidian", f"01 Projects/Retired/{cid}.md", "memory",
             "retired signal", "Budget changed by 42 percent", "",
             json.dumps(["retiredtag"]), cid, "2099-01-01", "2099-01-01", status),
        )
    conn.commit()

    assert _output_mix(conn) == []
    assert _areas(conn) == []
    assert _recent(conn) == []
    assert _active_cubes(conn) == []
    assert _get_feedback_from_cubes(conn, ["retired_signal"]) == []
    assert find_suspects(conn) == []
    assert find_clusters(conn) == []


def test_still_true_beats_rename_when_path_exists_again(conn, tmp_path):
    """A rename alias must not auto-retire a dead-path finding whose path
    exists again — re-verify first, then explain by rename."""
    alive = tmp_path / "glaze" / "x.py"
    alive.parent.mkdir(parents=True)
    alive.write_text("ok")
    conn.execute(
        "INSERT INTO entity_aliases (old_name, new_name, renamed_at, note, "
        "created_at) VALUES ('glaze','helicon','2026-07-04','rename','2026-07-04')")
    conn.commit()
    _cube(conn, "c1")
    fid = _finding(conn, finding=f"dead path: {alive} is gone", target="c1")
    out = valuation.evaluate(conn, conn.execute(
        "SELECT * FROM audit_log WHERE id=?", (fid,)).fetchone())
    assert out["escalate"] is False
    assert out["gate"] == "still_true"
    assert "exists again" in out["reason"]


def test_machine_retired_finding_does_not_block_human_confirm(conn):
    """Resolvers must refuse to human-rule a machine-closed row."""
    from helicon.api import govern

    _cube(conn, "c1")
    fid = _finding(conn, target="c1")
    conn.execute(
        "UPDATE audit_log SET machine_decision='auto-retired', "
        "machine_reason='test' WHERE id=?", (fid,))
    conn.commit()
    res = govern._confirm(conn, fid, "acted")
    assert res["ok"] is False
    assert "machine-closed" in res["error"]
    assert conn.execute(
        "SELECT human_decision FROM audit_log WHERE id=?", (fid,)
    ).fetchone()[0] is None
