"""Review 2.0 phase A: helicon_flag, regret ledger, human-evidence guard."""
import json
from datetime import datetime, timedelta

import pytest

from helicon.db import init_db, insert_cube, rebuild_fts
from helicon.models import HeliconCube, Review
from helicon.db import insert_review


def _cube(cid: str, title: str, content: str, status: str = "pending") -> HeliconCube:
    now = datetime.utcnow().isoformat()
    return HeliconCube(
        id=cid, source="test", source_ref=f"test/{cid}", type="memory",
        title=title, content=content, content_hash=cid, created_at=now,
        valid_from=now, last_reinforced=now, confidence=0.8,
        tags=[], metadata={}, review_status=status,
    )


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "t.db"))
    assert insert_cube(c, _cube("gc_live1", "Deploy target decision",
                                "The deploy target is Alibaba Cloud Shell for the final proof run"))
    assert insert_cube(c, _cube("gc_dead1", "ECS deployment plan",
                                "Deploy Mount Helicon to Alibaba ECS instance for the hackathon demo"))
    c.commit()
    rebuild_fts(c)
    # kill the ghost 10 days ago
    insert_review(c, Review(id=None, cube_id="gc_dead1", decision="killed", notes="",
                            time_to_review_seconds=1, cube_age_days=1, cube_type="memory",
                            cube_source="test",
                            reviewed_at=(datetime.utcnow() - timedelta(days=10)).isoformat(),
                            session_id="cli-review"))
    c.commit()
    return c


# ------------------------------------------------------------- helicon_flag
def test_flag_stale_creates_pending_finding_not_a_kill(conn):
    from helicon.mcp_server import handle_tool_call
    res = json.loads(handle_tool_call(
        "helicon_flag", {"memory_id": "gc_live1", "verdict": "stale", "reason": "outdated"}, conn))
    assert res["ok"]
    row = conn.execute("SELECT * FROM audit_log WHERE audit_type='agent-flag'").fetchone()
    assert row["human_decision"] is None  # pending: the human decides
    assert "stale" in row["finding"]
    status = conn.execute("SELECT review_status FROM helicon_cubes WHERE id='gc_live1'").fetchone()[0]
    assert status == "pending"  # the flag did NOT kill anything


def test_flag_useful_rewards_and_marks_acted_on(conn):
    from helicon.mcp_server import handle_tool_call
    conn.execute("INSERT INTO retrieval_log (cube_id, context, was_surfaced, was_acted_on, retrieved_at) "
                 "VALUES ('gc_live1', 't', 1, 0, ?)", (datetime.utcnow().isoformat(),))
    res = json.loads(handle_tool_call("helicon_flag", {"memory_id": "gc_live1", "verdict": "useful"}, conn))
    assert res["ok"]
    assert conn.execute("SELECT was_acted_on FROM retrieval_log WHERE cube_id='gc_live1'").fetchone()[0] == 1
    q = conn.execute("SELECT q_value FROM memory_utility WHERE cube_id='gc_live1'").fetchone()
    assert q is not None and q[0] > 0.5


def test_flag_unknown_id_errors_cleanly(conn):
    from helicon.mcp_server import handle_tool_call
    res = json.loads(handle_tool_call("helicon_flag", {"memory_id": "gc_nope", "verdict": "stale"}, conn))
    assert not res["ok"]


# ------------------------------------------------------------- regret ledger
def test_ghost_hit_records_time_decayed_regret(conn):
    from helicon.regret import record_ghost_hits
    hits = record_ghost_hits(conn, "Alibaba ECS deployment plan for the hackathon", source="test")
    assert len(hits) == 1 and hits[0]["cube_id"] == "gc_dead1"
    row = conn.execute("SELECT * FROM regret_events").fetchone()
    assert row["kill_review_id"] is not None  # blame lands on the decision
    assert 0 < row["weight"] < 1  # killed 10d ago -> decayed but nonzero


def test_ghost_hit_dedupes_within_a_day(conn):
    from helicon.regret import record_ghost_hits
    task = "Alibaba ECS deployment plan for the hackathon"
    record_ghost_hits(conn, task, source="test")
    again = record_ghost_hits(conn, task, source="test")
    assert again == []
    assert conn.execute("SELECT COUNT(*) FROM regret_events").fetchone()[0] == 1


def test_live_cubes_never_regret(conn):
    from helicon.regret import record_ghost_hits
    record_ghost_hits(conn, "deploy target decision Alibaba Cloud Shell proof", source="test")
    rows = conn.execute("SELECT cube_id FROM regret_events").fetchall()
    assert all(r["cube_id"] != "gc_live1" for r in rows)


# ------------------------------------------------- human-evidence guard
def test_agent_and_rule_sessions_are_not_human_evidence(conn):
    from helicon.triage import _get_type_kill_rates
    for sid in ("agent-flag", "rule:7", "auto-triage"):
        for i in range(30):
            insert_review(conn, Review(id=None, cube_id="gc_live1", decision="killed", notes="",
                                       time_to_review_seconds=1, cube_age_days=1,
                                       cube_type="synthetic", cube_source="test",
                                       reviewed_at=datetime.utcnow().isoformat(), session_id=sid))
    conn.commit()
    rates = _get_type_kill_rates(conn)
    # 90 non-human kills of type 'synthetic' must contribute zero evidence
    assert "synthetic" not in rates


# ------------------------------------------------------------- prompted rules
def test_predicate_grammar_is_a_whitelist():
    from helicon.rules import validate_predicate
    ok = validate_predicate({"action": "kill", "match": {"type": "code", "age_days_gt": 30}})
    assert "error" not in ok
    bad = validate_predicate({"action": "kill", "match": {"sql": "DROP TABLE"}})
    assert "error" in bad
    bad2 = validate_predicate({"action": "purge", "match": {"type": "code"}})
    assert "error" in bad2


def test_rule_preview_precision_vs_history(conn):
    from helicon.rules import preview, save_rule, approve_rule, apply_rules
    pred = {"action": "kill", "match": {"type": "memory", "title_contains": "ECS"}}
    prev = preview(conn, pred)
    # gc_dead1 (killed) matches -> history agrees with kill 1/1
    assert prev["history_n"] == 1 and prev["history_agree"] == 1
    assert prev["precision_vs_history"] == 1.0

    rid = save_rule(conn, "kill ECS memories", pred, "test-model", prev)
    assert approve_rule(conn, rid)

    dry = apply_rules(conn, dry_run=True)
    assert dry["dry_run"] and dry["total"] == 0  # gc_dead1 already killed, gc_live1 no match

    # a matching pending cube gets acted on with session rule:<id>
    from datetime import datetime as _dt
    assert insert_cube(conn, _cube("gc_p1", "ECS follow-up note", "old ECS deploy note"))
    conn.commit()
    res = apply_rules(conn, dry_run=False)
    assert res["total"] == 1
    row = conn.execute("SELECT review_status FROM helicon_cubes WHERE id='gc_p1'").fetchone()
    assert row[0] == "killed"
    sess = conn.execute("SELECT session_id FROM reviews WHERE cube_id='gc_p1'").fetchone()[0]
    assert sess == f"rule:{rid}"
