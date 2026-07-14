"""helicon runs, slice 1.1 - the cost side of run scoring.

Hermetic: synthetic .jsonl files in tmp_path, no real transcripts. The invariants:
usage sums come from the top-level fields (not the double-counting `iterations`),
duration is the timestamp span, and a file with no assistant/usage lines yields no
record (never a fabricated zero-cost run).
"""
import json

import pytest

from helicon.db import init_db
from helicon.runs import (parse_session_cost, scan_session_costs, group_runs,
                          run_yield, score_run, build_run_card,
                          persist_run_card, latest_run_cards, suggest_runs)


def _write(path, lines):
    with open(path, "w") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")


def _assistant(ts, out, inp=0, cc=0, cr=0, model="claude-opus-4-8"):
    return {"type": "assistant", "timestamp": ts,
            "message": {"model": model, "usage": {
                "output_tokens": out, "input_tokens": inp,
                "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr,
                # iterations repeats the same numbers; must NOT be summed again
                "iterations": [{"output_tokens": out, "input_tokens": inp}]}}}


def test_sums_usage_and_span(tmp_path):
    p = tmp_path / "sess-a.jsonl"
    _write(p, [
        {"type": "user", "timestamp": "2026-07-14T10:00:00.000Z"},
        _assistant("2026-07-14T10:05:00.000Z", out=100, inp=500, cc=200, cr=50),
        _assistant("2026-07-14T10:20:00.000Z", out=300, inp=700, cc=0, cr=1000),
    ])
    r = parse_session_cost(str(p))
    assert r["output_tokens"] == 400            # 100 + 300, NOT doubled by iterations
    assert r["input_tokens"] == 1200
    assert r["cache_creation_tokens"] == 200
    assert r["cache_read_tokens"] == 1050
    assert r["total_tokens"] == 400 + 1200 + 200 + 1050
    assert r["assistant_msgs"] == 2
    assert r["duration_min"] == 20.0            # 10:00 -> 10:20
    assert r["model"] == "claude-opus-4-8"


def test_dominant_model_wins(tmp_path):
    p = tmp_path / "sess-b.jsonl"
    _write(p, [
        _assistant("2026-07-14T10:00:00.000Z", out=10, model="claude-opus-4-8"),
        _assistant("2026-07-14T10:01:00.000Z", out=10, model="claude-opus-4-8"),
        _assistant("2026-07-14T10:02:00.000Z", out=10, model="claude-fable-5"),
    ])
    assert parse_session_cost(str(p))["model"] == "claude-opus-4-8"


def test_no_usage_file_is_no_record(tmp_path):
    p = tmp_path / "empty.jsonl"
    _write(p, [
        {"type": "user", "timestamp": "2026-07-14T10:00:00.000Z"},
        {"type": "system", "timestamp": "2026-07-14T10:01:00.000Z"},
    ])
    assert parse_session_cost(str(p)) is None   # never a fabricated zero-cost run


def test_scan_sorts_newest_first_and_since_filters(tmp_path):
    _write(tmp_path / "old.jsonl", [_assistant("2026-07-01T10:00:00.000Z", out=10)])
    _write(tmp_path / "new.jsonl", [_assistant("2026-07-14T10:00:00.000Z", out=10)])
    recs = scan_session_costs(str(tmp_path))
    assert [r["session_id"] for r in recs] == ["new", "old"]     # newest first
    recent = scan_session_costs(str(tmp_path), since="2026-07-10")
    assert [r["session_id"] for r in recent] == ["new"]         # since drops old


# --- slice 1.2: run identity --------------------------------------------------

def _rec(sid, start, last, out=10, model="claude-opus-4-8"):
    return {"session_id": sid, "first_ts": start, "last_ts": last,
            "output_tokens": out, "total_tokens": out * 10,
            "models": {model: 1}}


def test_parallel_terminals_are_one_run(tmp_path):
    # three sessions started within minutes = one run (a 3-terminal burst)
    recs = [
        _rec("a", "2026-07-14T07:40:00", "2026-07-14T09:30:00"),
        _rec("b", "2026-07-14T07:45:00", "2026-07-14T09:10:00"),
        _rec("c", "2026-07-14T07:55:00", "2026-07-14T08:50:00"),
    ]
    runs = group_runs(recs, gap_min=300)
    assert len(runs) == 1
    assert runs[0]["session_count"] == 3
    assert set(runs[0]["session_ids"]) == {"a", "b", "c"}
    assert runs[0]["output_tokens"] == 30


def test_quiet_gap_splits_runs(tmp_path):
    # a full day apart = two runs, even though the first session ran long
    recs = [
        _rec("day1", "2026-07-13T09:00:00", "2026-07-13T20:00:00"),
        _rec("day2", "2026-07-14T09:00:00", "2026-07-14T10:00:00"),
    ]
    runs = group_runs(recs, gap_min=300)
    assert len(runs) == 2
    assert runs[0]["session_ids"] == ["day2"]        # newest first


def test_long_open_session_does_not_bridge_days(tmp_path):
    # start-based clustering: a session left open across the gap cannot merge the
    # next day's burst into it (the bug that made every week one blob)
    recs = [
        _rec("long", "2026-07-13T09:00:00", "2026-07-14T23:00:00"),   # 38h open
        _rec("next", "2026-07-14T09:00:00", "2026-07-14T09:30:00"),
    ]
    runs = group_runs(recs, gap_min=300)
    assert len(runs) == 2       # 'next' started 24h after 'long', so separate runs


# --- slices 1.3 + 1.5: yield join and score ----------------------------------

def _evrow(conn, verdict, i):
    conn.execute(
        "INSERT INTO route_evidence "
        "(model,harness,task_class,verdict,created_at,pair_key) VALUES "
        "('Opus 4.8','claude-code','testing',?, '2026-07-14', ?)", (verdict, f"e{i}"))


def test_run_yield_ratio_excludes_uncheckable(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    for i in range(4):
        _evrow(conn, "verified", i)
    _evrow(conn, "contradicted", 98)
    _evrow(conn, "unverified", 99)          # uncheckable, must not enter the ratio
    conn.commit()
    y = run_yield(conn)
    assert y["verified"] == 4 and y["contradicted"] == 1
    assert y["checkable"] == 5              # 4 + 1, not 6
    assert y["verified_ratio"] == 0.8
    assert y["uncheckable"] == 1


def test_score_formula_terms_are_real_and_damage_subtracts():
    run = {"output_tokens": 2_000_000, "duration_min": 120}   # 2 Mtok, 2.0h
    yld = {"verified": 4}
    s = score_run(run, yld, damage=0.3)
    assert s["out_mtok"] == 2.0 and s["hours"] == 2.0
    assert s["cost"] == 4.0                 # 2.0 * 2.0
    assert s["raw"] == 1.0                  # 4 / 4.0
    assert s["score"] == 0.7                # 1.0 - 0.3 damage


def test_build_run_card_joins_cost_and_yield(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    for i in range(4):
        _evrow(conn, "verified", i)
    _evrow(conn, "contradicted", 98)
    _evrow(conn, "contradicted", 97)
    conn.commit()
    run = group_runs([_rec("s1", "2026-07-14T07:40:00", "2026-07-14T09:40:00",
                           out=1_000_000)], gap_min=300)[0]
    card = build_run_card(conn, run, damage=0.0)
    assert card["verified"] == 4 and card["checkable"] == 6
    assert card["verified_ratio"] == 0.667
    assert card["output_tokens"] == 1_000_000
    assert "score" in card and isinstance(card["score"], float)


# --- slice 1.6/1.7: persist + Latest + suggest -------------------------------

def _card(run_id, start, sess, score):
    return {"run_id": run_id, "start": start, "end": start, "duration_min": 60.0,
            "model": "claude-opus-4-8", "session_count": sess, "output_tokens": 1000,
            "total_tokens": 5000, "verified": 2, "checkable": 3, "verified_ratio": 0.667,
            "cost": 1.0, "damage": 0.0, "score": score}


def test_persist_is_idempotent_and_latest_orders_newest_first(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    persist_run_card(conn, _card("run-A", "2026-07-10T09:00", 1, 0.5))
    persist_run_card(conn, _card("run-B", "2026-07-14T09:00", 4, 0.9))
    persist_run_card(conn, _card("run-A", "2026-07-10T09:00", 1, 0.7))  # re-score, upsert
    cards = latest_run_cards(conn)
    assert [c["run_id"] for c in cards] == ["run-B", "run-A"]   # newest start first
    assert len(cards) == 2                                       # upsert, not duplicate
    assert cards[1]["score"] == 0.7                              # re-score took effect


def test_suggest_shape_insufficient_below_min(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    persist_run_card(conn, _card("run-A", "2026-07-10T09:00", 1, 0.5))
    s = suggest_runs(conn, min_runs=3)
    assert s["best_shape"] is None                # 1 < 3, no fabricated comparison
    assert s["scored_runs"] == 1


def test_suggest_shape_compares_focused_vs_fleet(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    persist_run_card(conn, _card("r1", "2026-07-10T09:00", 1, 0.9))   # focused
    persist_run_card(conn, _card("r2", "2026-07-11T09:00", 2, 0.8))   # focused
    persist_run_card(conn, _card("r3", "2026-07-12T09:00", 5, 0.3))   # fleet
    s = suggest_runs(conn, min_runs=3)
    assert s["best_shape"]["focused (<=2 sess)"] == 0.85
    assert s["best_shape"]["fleet (3+ sess)"] == 0.3
