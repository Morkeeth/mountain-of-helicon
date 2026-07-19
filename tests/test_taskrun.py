"""TaskRun + ContextPacket recorder — the six properties the rev-2 design pins.
Read-only, local-only, attach-only, default-deny privacy, no contamination."""
import subprocess

import pytest

import helicon.taskrun as tr
from helicon.db import init_db
from helicon.demo import seed


@pytest.fixture
def conn(tmp_path):
    db = str(tmp_path / "demo.db")
    seed(db)
    return init_db(db)


def _open(conn, mode="compact"):
    return tr.open_run(conn, "summarise the user's current diet", "the summary matches the latest ruling",
                       task_class="content-draft", model="qwen3.6-flash", harness="cc",
                       skill_versions=["frame@1"], context_mode=mode)


def test_packet_provenance_is_reconstructible(conn):
    rid = _open(conn)
    built = tr.build_packet(conn, rid, query="diet")
    # recomputing the hash from the STORED items reproduces the frozen packet hash
    assert tr.reconstruct_packet_hash(conn, rid) == built["packet_hash"]
    # and the packet predates any artifact (opened -> executing, no artifact yet)
    row = conn.execute("SELECT status, artifact_attached_at FROM task_runs WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "executing" and row["artifact_attached_at"] is None


def test_no_private_or_unclassified_item_enters_a_packet(conn):
    rid = _open(conn)
    tr.build_packet(conn, rid, query="")   # everything live
    # the demo's runway/finance memory (bank balance) is hard-private -> excluded
    items = conn.execute("SELECT cube_id FROM context_packet_items cpi "
                         "JOIN context_packets cp ON cp.id=cpi.packet_id WHERE cp.task_run_id=?", (rid,)).fetchall()
    ids = {r["cube_id"] for r in items}
    assert "demo-runway" not in ids
    # and the exclusion log is OPAQUE — no title / ref / content of the private item
    import json
    excl = json.loads(conn.execute("SELECT excluded_relevant FROM context_packets WHERE task_run_id=?", (rid,)).fetchone()["excluded_relevant"])
    assert excl, "the private item should be logged as excluded"
    blob = json.dumps(excl)
    assert "balance" not in blob.lower() and "finance" not in blob.lower() and "180,000" not in blob


def test_build_packet_does_not_contaminate_any_existing_table(conn):
    tables = ["helicon_cubes", "retrieval_log", "memory_utility", "regret_events", "route_evidence", "audit_log"]
    def snap():
        s = {}
        for t in tables:
            try:
                s[t] = conn.execute(f"SELECT * FROM {t}").fetchall()
                s[t] = [tuple(r) for r in s[t]]
            except Exception:
                s[t] = None
        return s
    before = snap()
    rid = _open(conn)
    tr.build_packet(conn, rid, query="diet")
    after = snap()
    for t in tables:
        assert before[t] == after[t], f"{t} was mutated by packet building"


def test_verification_is_attach_only_and_runs_nothing(conn, monkeypatch):
    # If the recorder ever shells out to 'run' a verifier, this fails.
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess in slice one")))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess in slice one")))
    rid = _open(conn)
    tr.build_packet(conn, rid, query="diet")
    tr.attach_artifact(conn, rid, [{"path_or_ref": "out.md", "content_hash": "abc", "observed_at": "t"}])
    tr.attach_verification(conn, rid, "unverified", evidence="operator did not run the test")
    row = conn.execute("SELECT verification_outcome, verification_receipt FROM task_runs WHERE id=?", (rid,)).fetchone()
    assert row["verification_outcome"] == "unverified"          # first-class, never a pass
    assert '"source": "attached"' in row["verification_receipt"]


def test_state_machine_rejects_out_of_order_transitions(conn):
    rid = _open(conn)
    # verify or attach before a packet/artifact must be refused, not silently done
    with pytest.raises(tr.TaskRunError):
        tr.attach_artifact(conn, rid, [])                       # no packet yet
    tr.build_packet(conn, rid, query="diet")
    with pytest.raises(tr.TaskRunError):
        tr.attach_verification(conn, rid, "verified")           # no artifact yet
    tr.attach_artifact(conn, rid, [{"path_or_ref": "o", "content_hash": "h", "observed_at": "t"}])
    with pytest.raises(tr.TaskRunError):
        tr.attach_artifact(conn, rid, [])                       # already attached
    tr.attach_verification(conn, rid, "verified")
    with pytest.raises(tr.TaskRunError):
        tr.attach_verification(conn, rid, "contradicted")       # mutating a verified run


def test_ab_pair_shares_task_identity_but_distinct_context(conn):
    a = _open(conn, mode="current-global")
    b = _open(conn, mode="compact")
    ha = conn.execute("SELECT task_spec_hash FROM task_runs WHERE id=?", (a,)).fetchone()["task_spec_hash"]
    hb = conn.execute("SELECT task_spec_hash FROM task_runs WHERE id=?", (b,)).fetchone()["task_spec_hash"]
    assert ha == hb, "same objective/model/harness/skills -> same task identity for a fair A/B"
    pa = tr.build_packet(conn, a, query="")
    pb = tr.build_packet(conn, b, query="diet")
    assert pa["packet_id"] != pb["packet_id"]
    modes = {conn.execute("SELECT context_mode FROM task_runs WHERE id=?", (r,)).fetchone()["context_mode"] for r in (a, b)}
    assert modes == {"current-global", "compact"}
