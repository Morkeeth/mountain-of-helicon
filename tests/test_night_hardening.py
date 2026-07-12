"""Hardening for the Jul 8 build:
- the empty-DB compute_score guard (MCP helicon_health used to KeyError on a
  fresh clone with zero cubes),
- the rot-exam contract that `helicon ci` / the GitHub Action depend on.

(The Focus faithfulness guard — dropping next-moves whose citations don't
resolve — is verified live via /api/focus/moves; a unit test for it awaits
extracting the finding builders out of the api layer into a core module, which
is tracked tech-debt, not done here to avoid churning the api.findings tests.)
"""
from helicon.db import init_db
from helicon.score import compute_score
from helicon.rot import run_rot_exam


def test_compute_score_empty_db_has_full_shape(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    s = compute_score(conn)
    for k in ("score", "total", "reviewed", "pending", "by_source", "by_type", "by_decision"):
        assert k in s, f"empty-DB score missing key {k}"
    assert s["total"] == 0 and s["pending"] == 0


def test_rot_exam_contract(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    res = run_rot_exam(conn)
    assert res["classes"] == 11
    assert "rot_found" in res and isinstance(res["checks"], list)
    assert len(res["checks"]) == 11
    for c in res["checks"]:
        assert {"id", "name", "coverage", "verdict", "receipt"} <= set(c)
        assert c["verdict"] in ("ROT FOUND", "CLEAN", "UNMEASURED")
