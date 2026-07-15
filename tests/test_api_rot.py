"""The exam and judge surfaces: /api/rot and /api/judge.

The rule these tests exist to defend: the judge tab may never invent a number.
An unrun bench must render as unrun, and a saved bench must round-trip exactly
what was measured (including the notes naming what was NOT measured).
"""
import sqlite3

import pytest

from helicon.judge_bench import init_judge_table, latest_judge_run, save_judge_run
from helicon.rot import run_rot_exam


@pytest.fixture
def conn(tmp_path):
    from helicon.db import init_db
    return init_db(str(tmp_path / "t.db"))


# --- the exam ---------------------------------------------------------------

def test_rot_exam_shape_is_renderable(conn):
    """Every field the EXAM tab renders is present on an empty store."""
    res = run_rot_exam(conn)
    assert res["classes"] == 12
    assert res["rot_found"] + res["unmeasured"] <= 12
    ids = [c["id"] for c in res["checks"]]
    assert ids == [f"R{i}" for i in range(1, 13)]
    for c in res["checks"]:
        assert c["verdict"] in ("CLEAN", "ROT FOUND", "UNMEASURED")
        assert c["coverage"] in ("TESTED", "PARTIAL")
        assert c["name"] and c["receipt"]          # a verdict always carries evidence


def test_unmeasured_is_not_counted_as_clean(conn):
    """UNMEASURED must never be summed into the 'clean' story. The headline
    counts rot and tested separately precisely so a gap can't read as a pass."""
    res = run_rot_exam(conn)
    clean = sum(1 for c in res["checks"] if c["verdict"] == "CLEAN")
    assert clean + res["rot_found"] + res["unmeasured"] == res["classes"]


# --- the judge bench --------------------------------------------------------

def test_latest_judge_run_is_none_when_never_run(conn):
    assert latest_judge_run(conn) is None


def test_save_and_read_back_a_run(conn):
    res = {
        "probes": [{"is_contradiction": True}, {"is_contradiction": False}],
        "notes": ["set OPENROUTER_API_KEY to compare Qwen vs GPT/Claude"],
        "scored": {
            "probes": 2, "inter_tier_agreement": 1.0,
            "rows": {"qwen3.6-flash": {"model": "qwen3.6-flash", "accuracy": 0.962,
                                       "cost_usd": 0.00166, "recall": 1.0,
                                       "specificity": 1.0, "latency_s": 32.9,
                                       "errors": 0, "misses": []}},
        },
    }
    rid = save_judge_run(conn, res, which="all")
    assert rid == 1
    got = latest_judge_run(conn)
    assert got["probe_set"] == "all"
    assert got["positives"] == 1 and got["negatives"] == 1
    assert got["rows"]["qwen3.6-flash"]["accuracy"] == 0.962
    assert got["rows"]["qwen3.6-flash"]["cost_usd"] == 0.00166
    # the notes are the honesty channel: what was NOT measured survives the trip
    assert "OPENROUTER_API_KEY" in got["notes"][0]


def test_latest_returns_the_most_recent_run(conn):
    def r(acc):
        return {"probes": [{"is_contradiction": True}], "notes": [],
                "scored": {"probes": 1, "inter_tier_agreement": None,
                           "rows": {"m": {"model": "m", "accuracy": acc}}}}
    save_judge_run(conn, r(0.5), which="ruled")
    save_judge_run(conn, r(0.9), which="hard")
    got = latest_judge_run(conn)
    assert got["probe_set"] == "hard" and got["rows"]["m"]["accuracy"] == 0.9


def test_init_judge_table_is_idempotent(conn):
    init_judge_table(conn)
    init_judge_table(conn)          # a second serve must not blow up


# --- the endpoints ----------------------------------------------------------

def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from helicon.api import app as app_mod
    monkeypatch.setattr(app_mod, "load_config",
                        lambda: {"db_path": str(tmp_path / "api.db")})
    return TestClient(app_mod.create_app())


def test_api_rot_runs_live(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        res = c.get("/api/rot")
        assert res.status_code == 200
        assert res.json()["classes"] == 12


def test_api_judge_says_so_when_no_run_exists(tmp_path, monkeypatch):
    """The load-bearing test. No saved run -> ran:false + the command to make
    one. Never a fabricated row, never a zero dressed as a measurement."""
    with _client(tmp_path, monkeypatch) as c:
        body = c.get("/api/judge").json()
        assert body["ran"] is False
        assert "judge-bench" in body["command"]
        assert "rows" not in body


def test_api_judge_serves_a_saved_run(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        conn = sqlite3.connect(str(tmp_path / "api.db"))
        conn.row_factory = sqlite3.Row
        save_judge_run(conn, {
            "probes": [{"is_contradiction": True}], "notes": ["no competitor"],
            "scored": {"probes": 1, "inter_tier_agreement": None,
                       "rows": {"qwen3.6-flash": {"model": "qwen3.6-flash",
                                                  "accuracy": 0.962,
                                                  "cost_usd": 0.00166}}},
        }, which="all")
        conn.close()
        body = c.get("/api/judge").json()
        assert body["ran"] is True
        assert body["rows"]["qwen3.6-flash"]["cost_usd"] == 0.00166
        assert body["notes"] == ["no competitor"]
