"""Serving-side hygiene + judged-on-evidence: the two fixes behind the
2026-07-28 DEGRADED exam (grounding_pass_rate 0.385, 1 BROKEN battery task,
2 regressed snapshots), root-caused against a copy of the real store.

What was actually wrong, and what these tests pin:

1. Retrieval served hard-stale context. An APPROVED cube decayed to
   confidence 0.02 ('Edited: MEMORY.md', 61 days old) was retrieved for
   'Bagel agent deployment and operations', so the battery's own Freshness
   test critical-failed the serving layer -> the exam's one BROKEN task.
   Retrieval filtered killed/superseded but had no confidence floor, i.e. it
   stopped at a different line than the exam grades against.

2. Retrieval flooded top-K with duplicate titles. Three distinct cubes all
   titled 'Created: closeout-2026-07-23-orchestrator.md' took 3 of 5 slots
   for 'Orchestrator Closeout' -> Redundancy FAIL on two tasks AND snapshot
   #21 "regressed" (live baselines crowded out, live_overlap 0.0).

3. The Grounding judge was shown only titles. It then failed 8/13 tasks with
   reasons like "vague titles without content" and "truncated text" — the
   truncation being the title's own cut. The exam graded evidence it withheld.
"""
import pytest

import helicon.qwen as qwen_mod
from helicon.battery import run_battery, run_llm_tests
from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube
from helicon.snapshots import STALE_CONF_FLOOR, _context_hygiene, _retrieve


def _cube(conn, cid, title, content, status="approved", confidence=1.0):
    insert_cube(conn, HeliconCube(
        id=cid, source="claude-code", source_ref=f"ref_{cid}", type="memory",
        title=title, content=content, content_hash=cid,
        created_at="2026-07-01T00:00:00", valid_from="2026-07-01T00:00:00",
        review_status=status, confidence=confidence))
    conn.commit()


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


# --- 1. the confidence floor -------------------------------------------------

def test_hygiene_drops_a_live_cube_decayed_below_the_freshness_line(conn):
    """The BROKEN task's cause: approved but decayed-to-0.02 context served."""
    _cube(conn, "gc_ok", "runbook", "deploy steps that still hold")
    _cube(conn, "gc_stale", "Edited: MEMORY.md", "sixty-one days stale",
          confidence=0.02)
    hits = [{"id": "gc_stale", "title": "Edited: MEMORY.md"},
            {"id": "gc_ok", "title": "runbook"}]
    out = _context_hygiene(conn, hits, k=2)
    assert [h["id"] for h in out] == ["gc_ok"], \
        "a cube below STALE_CONF_FLOOR was served as current context"


def test_hygiene_floor_is_the_same_line_the_battery_grades_against(conn):
    """Just above the floor stays served — retrieval must stop AT the exam's
    line, not below it (over-filtering) or above it (the original bug)."""
    _cube(conn, "gc_edge", "edge", "soft-stale but live",
          confidence=STALE_CONF_FLOOR)
    out = _context_hygiene(conn, [{"id": "gc_edge", "title": "edge"}], k=1)
    assert [h["id"] for h in out] == ["gc_edge"]


def test_retrieval_no_longer_critical_fails_its_own_freshness_test(conn):
    """End-to-end over FTS: the decayed cube matches the task terms best but
    must not reach the agent, so the battery stays un-BROKEN."""
    _cube(conn, "gc_dead", "bagel deployment notes",
          "bagel deployment agent operations, decayed", confidence=0.01)
    _cube(conn, "gc_live", "bagel runbook", "bagel deployment agent operations")
    hits = _retrieve(conn, "bagel deployment operations", k=5)
    assert "gc_dead" not in [h["id"] for h in hits]
    res = run_battery(conn, "bagel deployment operations", k=5)
    freshness = next(t for t in res["results"] if t["name"] == "Freshness")
    assert freshness["status"] == "PASS"
    assert res["verdict"] != "BROKEN"


# --- 2. duplicate-title flooding --------------------------------------------

def test_hygiene_dedupes_identical_titles_keeping_the_best_ranked(conn):
    """Snapshot #21's cause: three same-title cubes ate 3 of 5 slots."""
    for i in range(3):
        _cube(conn, f"gc_dup{i}", "Created: closeout-2026-07-23-orchestrator.md",
              f"scan pass {i} of the same file event")
    _cube(conn, "gc_other", "Orchestrator Closeout - May 15", "the real content")
    hits = ([{"id": f"gc_dup{i}", "title": "Created: closeout-2026-07-23-orchestrator.md"}
             for i in range(3)]
            + [{"id": "gc_other", "title": "Orchestrator Closeout - May 15"}])
    out = _context_hygiene(conn, hits, k=3)
    assert [h["id"] for h in out] == ["gc_dup0", "gc_other"], \
        "duplicate titles must collapse to the best-ranked one"


def test_deduped_slots_refill_from_the_overfetch(conn):
    """Dropping a duplicate frees its slot for the next live memory — that is
    why _retrieve over-fetches 3x."""
    for i in range(2):
        _cube(conn, f"gc_dup{i}", "same title", f"body {i}")
    _cube(conn, "gc_a", "distinct a", "body a")
    _cube(conn, "gc_b", "distinct b", "body b")
    hits = [{"id": "gc_dup0", "title": "same title"},
            {"id": "gc_dup1", "title": "same title"},
            {"id": "gc_a", "title": "distinct a"},
            {"id": "gc_b", "title": "distinct b"}]
    out = _context_hygiene(conn, hits, k=3)
    assert [h["id"] for h in out] == ["gc_dup0", "gc_a", "gc_b"]


def test_hygiene_still_drops_retired_cubes(conn):
    """The original belt-and-suspenders must survive the generalization."""
    _cube(conn, "gc_live", "live", "x")
    _cube(conn, "gc_sup", "sup", "x", status="superseded")
    _cube(conn, "gc_kill", "kill", "x", status="killed")
    hits = [{"id": "gc_sup", "title": "sup"}, {"id": "gc_kill", "title": "kill"},
            {"id": "gc_live", "title": "live"}]
    out = _context_hygiene(conn, hits, k=3)
    assert [h["id"] for h in out] == ["gc_live"]


# --- 3. the judge sees the claims it grades ----------------------------------

def test_grounding_judge_receives_content_not_just_titles(conn, monkeypatch):
    """grounding_pass_rate 0.385 root cause: the judge prompt listed titles
    only, then the judge (correctly, given its evidence) called them 'vague
    titles without content'. The prompt must carry each memory's content."""
    captured = {}

    def fake_complete_json(client, system, user, model="m", operation=""):
        captured["user"] = user
        return {"Contradiction": {"status": "PASS", "reason": "ok"},
                "Grounding": {"status": "PASS", "reason": "concrete"}}

    monkeypatch.setattr(qwen_mod, "complete_json", fake_complete_json)
    hits = [{"id": "gc_1", "title": "FAVOUR decision log",
             "content": "FAVOUR fee switched to 2.5% on 2026-07-02 after audit"}]
    out = run_llm_tests(object(), "FAVOUR fee status", hits, model="m")
    assert "FAVOUR fee switched to 2.5% on 2026-07-02" in captured["user"], \
        "judge prompt must include memory content, not only the title"
    assert {t["name"] for t in out} == {"Contradiction", "Grounding"}


def test_run_battery_feeds_the_judge_content_from_the_store(conn, monkeypatch):
    """Integration: run_battery must enrich the retrieved hits with content
    before judging — _retrieve itself only returns ids and titles."""
    _cube(conn, "gc_c", "portfolio design",
          "portfolio uses three.js models and a dark hero section")
    captured = {}

    def fake_complete_json(client, system, user, model="m", operation=""):
        captured["user"] = user
        return {"Contradiction": {"status": "PASS", "reason": "ok"},
                "Grounding": {"status": "PASS", "reason": "ok"}}

    monkeypatch.setattr(qwen_mod, "complete_json", fake_complete_json)
    res = run_battery(conn, "portfolio design", k=3, client=object())
    assert res["llm_ran"] is True
    assert "three.js models and a dark hero section" in captured["user"]
