"""Taste-verdict memory — Helicon remembers Taste Machine's rulings so a ruled
output shape never wastes a human ruling twice (never-twice applied to taste)."""
import json

import pytest

from helicon.db import init_db
from helicon.taste import ingest_verdict, ingest_file, taste_guard


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


def _v(h, verdict, move="lived-example", kind="x-reply", reason=""):
    return {"artifact_hash": h, "human_verdict": verdict, "move": move,
            "kind": kind, "reason": reason, "content": f"draft {h}",
            "scores": {"relevance": 0.2}}


def test_ingest_and_exact_guard(conn):
    r = ingest_verdict(conn, _v("abc", "kill", reason="shoehorn"))
    assert r["ok"] and not r.get("skipped")
    g = taste_guard(conn, artifact_hash="abc")
    assert g["already_ruled"] and g["match"] == "exact" and g["prior_verdict"] == "kill"
    assert "shoehorn" in g["reason"]
    assert taste_guard(conn, artifact_hash="zzz")["already_ruled"] is False


def test_ingest_is_idempotent(conn):
    ingest_verdict(conn, _v("abc", "kill"))
    assert ingest_verdict(conn, _v("abc", "kill"))["skipped"] is True
    n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE audit_type='taste'").fetchone()[0]
    assert n == 1


def test_shape_guard_predicts_kill(conn):
    # the same move killed 3x -> shape guard fires even for a brand-new hash
    for h in ("a", "b", "c"):
        ingest_verdict(conn, _v(h, "kill", move="lived-example"))
    g = taste_guard(conn, move="lived-example")
    assert g["already_ruled"] and g["match"] == "shape" and g["kills"] == 3


def test_shape_guard_quiet_when_mostly_sent(conn):
    ingest_verdict(conn, _v("a", "kill", move="question"))
    for h in ("b", "c", "d"):
        ingest_verdict(conn, _v(h, "send", move="question"))
    assert taste_guard(conn, move="question")["already_ruled"] is False


def test_ingest_file(conn, tmp_path):
    p = tmp_path / "verdicts.json"
    p.write_text(json.dumps([_v("x", "kill"), _v("y", "send")]))
    res = ingest_file(conn, str(p))
    assert res["ingested"] == 2
    assert taste_guard(conn, artifact_hash="x")["prior_verdict"] == "kill"
    assert taste_guard(conn, artifact_hash="y")["prior_verdict"] == "send"
