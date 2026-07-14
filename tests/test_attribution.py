"""Auto-attribution: output failure -> the memory that caused it.

Hermetic: seed cubes + a review finding, assert the causal trace finds the cube
that asserts the false claim, and that ruling with --retire supersedes it so
retrieval stops serving it. This is the edge SUBMISSION.md flags as not airtight.
"""
import pytest

from helicon.db import init_db, insert_cube, rebuild_fts
from helicon.models import ConnectorResult, AuditResult
from helicon.scanner import result_to_cube
from helicon.claims import insert_audit
from helicon.attribution import attribute_finding, retire_cube, _keywords


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


def _cube(conn, content, ref, source="obsidian"):
    r = ConnectorResult(source=source, source_ref=ref, type="memory",
                        title=ref, content=content, created_at="2026-07-01T00:00:00")
    cube = result_to_cube(r)
    insert_cube(conn, cube)
    return cube.id


def _finding(conn, text):
    res = AuditResult(audit_type="review", target_type="terminal", target_id="Yieldbound",
                      finding=text, severity="critical", proposed_action="rule",
                      details={"kind": "claim"}, audited_at="2026-07-14T00:00:00")
    return insert_audit(conn, res)


def test_keywords_drop_stopwords_and_punctuation():
    kw = _keywords("[Yieldbound] CONTRADICTED: Yieldbound is a wallet tracker.")
    assert "yieldbound" in kw and "wallet" in kw and "tracker" in kw
    assert "is" not in kw and "contradicted" not in kw


def test_attribute_finds_the_causing_cube(conn):
    good = _cube(conn, "Yieldbound is a yield treasury that compounds positions.", "a.md")
    cause = _cube(conn, "Yieldbound is a wallet tracker that reads balances.", "b.md")
    rebuild_fts(conn)
    fid = _finding(conn, "[Yieldbound] CONTRADICTED: Yieldbound is a wallet tracker")
    row = conn.execute("SELECT * FROM audit_log WHERE id=?", (fid,)).fetchone()
    res = attribute_finding(conn, row)
    ids = [c["id"] for c in res["candidates"]]
    assert cause in ids                       # the memory that asserts the false claim surfaces
    assert res["claim"].startswith("Yieldbound is a wallet tracker")


def test_attribution_excludes_output_review_cubes(conn):
    _cube(conn, "Output review of terminal 'X': the claim was checked. Yieldbound tracker.",
          "audit:1", source="output-review")
    rebuild_fts(conn)
    fid = _finding(conn, "[X] CONTRADICTED: Yieldbound is a wallet tracker")
    row = conn.execute("SELECT * FROM audit_log WHERE id=?", (fid,)).fetchone()
    res = attribute_finding(conn, row)
    assert all(c["source"] != "output-review" for c in res["candidates"])   # our own corrections aren't "causes"


def test_retire_cube_supersedes_and_hides_from_retrieval(conn):
    cause = _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    rebuild_fts(conn)
    assert retire_cube(conn, cause, superseded_by="correction-1") is True
    row = conn.execute("SELECT review_status, merged_into FROM helicon_cubes WHERE id=?",
                       (cause,)).fetchone()
    assert row["review_status"] == "superseded" and row["merged_into"] == "correction-1"
    # retrieval excludes superseded memory
    from helicon.db import search_cubes
    rebuild_fts(conn)
    hits = [h["id"] for h in search_cubes(conn, "wallet tracker")]
    assert cause not in hits
    assert retire_cube(conn, "no-such-cube", superseded_by="x") is False
