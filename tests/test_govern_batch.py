"""Govern-batch: one Apply must be coherent, its receipt real, its undo total,
and its blast radius bounded. These pin the properties a demo cannot fake."""
import asyncio

import pytest

import helicon.api.govern as govern
from helicon.api.govern import ApplyBatchReq, Ruling, UndoReq
from helicon.db import init_db
from helicon.demo import seed


@pytest.fixture
def store(tmp_path, monkeypatch):
    import helicon.api.app as app_mod  # the endpoints import get_conn/get_config from here at call time
    db = str(tmp_path / "demo.db")
    seed(db)
    conn = init_db(db)
    monkeypatch.setattr(app_mod, "get_conn", lambda: conn)
    monkeypatch.setattr(app_mod, "get_config", lambda: {"db_path": db})
    return conn, db


def _finding(conn, atype):
    row = conn.execute(
        "SELECT id FROM audit_log WHERE audit_type=? AND human_decision IS NULL LIMIT 1",
        (atype,)).fetchone()
    return row["id"] if row else None


def _cubes(conn):
    return conn.execute("SELECT COUNT(*) FROM helicon_cubes").fetchone()[0]


def _decided(conn, fid):
    return conn.execute("SELECT human_decision FROM audit_log WHERE id=?", (fid,)).fetchone()["human_decision"]


def test_one_coherent_apply_with_real_propagation(store):
    conn, _ = store
    idf = _finding(conn, "factual")
    assert idf, "demo store should carry an identity fork to rule"
    out = asyncio.run(govern.apply_batch(ApplyBatchReq(rulings=[
        Ruling(finding_id=idf, verb="rule_truth", payload={"truth": "live — real money"})])))
    assert out["applied"] == 1
    r = out["receipt"][0]
    assert r["applied"] and r["verify"]["recorded_in_audit_log"]
    # propagation is real state, not a claim: the finding is settled in the record
    assert _decided(conn, idf)


def test_partial_failure_isolates(store):
    conn, _ = store
    idf = _finding(conn, "factual")
    asyncio.run(govern.apply_batch(ApplyBatchReq(rulings=[
        Ruling(finding_id=idf, verb="rule_truth", payload={"truth": "live — real money"})])))
    rel = _finding(conn, "provenance")
    out = asyncio.run(govern.apply_batch(ApplyBatchReq(rulings=[
        Ruling(finding_id=idf, verb="rule_truth", payload={"truth": "x"}),   # already decided -> fails
        Ruling(finding_id=rel, verb="resolve_relation", payload={"verdict": "phantom"})])))
    by_id = {r["finding_id"]: r for r in out["receipt"]}
    assert not by_id[idf]["applied"] and by_id[idf]["error"]
    assert by_id[rel]["applied"], "the good ruling must still apply — no rollback of the batch"
    assert out["applied"] == 1 and out["failed"] == 1


def test_undo_is_total(store):
    conn, _ = store
    idf = _finding(conn, "factual")
    before = _cubes(conn)
    out = asyncio.run(govern.apply_batch(ApplyBatchReq(rulings=[
        Ruling(finding_id=idf, verb="rule_truth", payload={"truth": "live — real money"})])))
    assert _cubes(conn) > before, "the ruling writes a correction cube"
    undo = asyncio.run(govern.undo_batch(UndoReq(undo_token=out["undo_token"])))
    assert undo["fully_reversed"]
    assert _decided(conn, idf) is None                 # decision cleared
    assert _cubes(conn) == before                      # correction cube (and its FTS) gone


def test_rule_truth_makes_the_guard_enforce_it(store):
    """The golden thread: rule a live contradiction, and the receipt PROVES the guard
    now blocks the ruled-wrong claim — enforcement, not just a record."""
    conn, _ = store
    fid = conn.execute("SELECT id FROM audit_log WHERE audit_type='factual' AND human_decision IS NULL LIMIT 1").fetchone()
    assert fid, "the demo seeds a factual contradiction as the hero"
    out = asyncio.run(govern.apply_batch(ApplyBatchReq(rulings=[
        Ruling(finding_id=fid["id"], verb="rule_truth", payload={"truth": "live — real money"})])))
    r = out["receipt"][0]
    assert r["applied"] and r["verify"]["guard_blocks_the_wrong_claim"] is True
    # independently: the guard now blocks a DANGEROUS claim (an agent about to charge
    # real cards because it thinks Stripe is still in test mode)
    from helicon.guard import guard_output
    assert not guard_output(conn, "Stripe is in test mode, safe to run a live checkout as a test").get("clean", True)


def test_blast_radius_leaves_source_memory_untouched(store):
    conn, _ = store
    idf = _finding(conn, "factual")
    src_before = [dict(r) for r in conn.execute(
        "SELECT id, content_hash, review_status FROM helicon_cubes WHERE id LIKE 'demo-%' ORDER BY id")]
    asyncio.run(govern.apply_batch(ApplyBatchReq(rulings=[
        Ruling(finding_id=idf, verb="rule_truth", payload={"truth": "live — real money"})])))
    src_after = [dict(r) for r in conn.execute(
        "SELECT id, content_hash, review_status FROM helicon_cubes WHERE id LIKE 'demo-%' ORDER BY id")]
    assert src_before == src_after, "ruling must not mutate the source memories it ruled on"
