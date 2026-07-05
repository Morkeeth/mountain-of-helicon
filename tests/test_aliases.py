"""R4 supersession aliases: dead-name refs triage by written rule.

The class under test (ROT.md R4): an entity is renamed, the old name lives on.
The rule is deterministic and dated: pre-rename refs are history (kept),
post-rename refs naming both names are rename-aware (fine), post-rename refs
speaking only the dead name are current-claims (the rot). One audit finding
per alias, idempotent.
"""
import pytest

from helicon.aliases import add_alias, alias_rot, alias_scan, triage_alias
from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.rot import run_rot_exam
from helicon.scanner import result_to_cube

RENAME = "2026-07-04T17:05:45"


def _cube(conn, content, ref, created_at, status="pending"):
    r = ConnectorResult(source="claude-code", source_ref=ref, type="memory",
                        title=ref, content=content, created_at=created_at)
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    if status != "pending":
        conn.execute("UPDATE helicon_cubes SET review_status=? WHERE id=?",
                     (status, cube.id))
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "helicon.db"))
    add_alias(c, "glaze", "helicon", RENAME, note="test rename")
    return c


def test_add_alias_is_unique(conn):
    assert not add_alias(conn, "glaze", "helicon", RENAME)


def test_triage_splits_history_aware_and_current_claims(conn):
    _cube(conn, "glaze dashboard shipped, 8 commits", "old.md",
          "2026-07-01T10:00:00")                       # pre-rename -> history
    _cube(conn, "rename: glaze -> helicon everywhere", "rename.md",
          "2026-07-04T18:00:00")                       # post, both -> aware
    _cube(conn, "polish the glaze demo video tonight", "stale.md",
          "2026-07-05T09:00:00")                       # post, old only -> rot
    t = alias_rot(conn)[0]
    assert (t["history"], t["rename_aware"], t["current_claims"]) == (1, 1, 1)
    assert t["live_refs"] == 3
    assert t["current_claim_samples"][0]["title"] == "stale.md"


def test_word_boundary_not_substring(conn):
    _cube(conn, "the glazed donut incident", "donut.md", "2026-07-05T09:00:00")
    t = alias_rot(conn)[0]
    assert t["live_refs"] == 0  # 'glazed' is not the project


def test_retired_cubes_do_not_count(conn):
    _cube(conn, "glaze demo plan", "gone.md", "2026-07-05T09:00:00",
          status="superseded")
    assert alias_rot(conn)[0]["live_refs"] == 0


def test_scan_files_once_and_is_idempotent(conn):
    _cube(conn, "polish the glaze demo video", "stale.md", "2026-07-05T09:00:00")
    first = alias_scan(conn)
    assert len(first["filed"]) == 1
    assert "written AFTER the rename" in first["filed"][0]["finding"]
    second = alias_scan(conn)
    assert second["filed"] == [] and second["already_filed"] == ["glaze->helicon"]
    n = conn.execute("SELECT COUNT(*) FROM audit_log "
                     "WHERE audit_type='supersession'").fetchone()[0]
    assert n == 1


def test_clean_alias_files_nothing(conn):
    _cube(conn, "glaze won nothing but taught plenty", "history.md",
          "2026-06-20T10:00:00")
    res = alias_scan(conn)
    assert res["filed"] == [] and res["clean"] == ["glaze->helicon"]


def test_triage_handles_z_and_offset_stamps_vs_naive_renamed_at(conn):
    """P1 from the audit: raw string compare misfiled the ±2h band around
    the rename for the store's 2,309 'Z' and 500 '+HH:MM' stamps. All
    comparisons now happen in UTC-naive space (naive renamed_at = UTC)."""
    # RENAME is 2026-07-04T17:05:45 (UTC). This Z-stamp is 24 min AFTER.
    _cube(conn, "ship the glaze fix tonight", "z-after.md",
          "2026-07-04T17:30:00.000Z")
    # This +02:00 stamp is 18:00 local = 16:00 UTC — BEFORE the rename.
    _cube(conn, "glaze notes from the afternoon", "local-before.md",
          "2026-07-04T18:00:00+02:00")
    t = alias_rot(conn)[0]
    assert t["current_claims"] == 1   # the Z-stamped post-rename cube
    assert t["history"] == 1          # the +02:00 pre-rename cube


def test_template_created_at_is_history_not_current_claim(conn):
    """The live store has a literal '{{date}}' created_at (an ingested
    Obsidian template). '{' sorts after digits, so string compare filed it
    as the future forever; unparseable now normalizes to oldest = history."""
    _cube(conn, "glaze template mention", "template.md", "{{date}}")
    t = alias_rot(conn)[0]
    assert t["current_claims"] == 0 and t["history"] == 1


def test_alias_name_with_nonword_edge_still_matches(conn):
    add_alias(conn, "glaze++", "helicon", RENAME)
    _cube(conn, "the glaze++ pipeline is live", "cpp.md", "2026-07-05T09:00:00")
    t = next(x for x in alias_rot(conn) if x["old_name"] == "glaze++")
    assert t["live_refs"] == 1 and t["current_claims"] == 1


def test_rot_r4_tested_and_reads_the_triage(conn):
    _cube(conn, "polish the glaze demo video", "stale.md", "2026-07-05T09:00:00")
    r4 = next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R4")
    assert r4["coverage"] == "TESTED"
    assert r4["verdict"] == "ROT FOUND"
    assert "1 current-claim(s)" in r4["receipt"]


def test_rot_r4_unmeasured_without_aliases(tmp_path):
    conn = init_db(str(tmp_path / "bare.db"))
    r4 = next(c for c in run_rot_exam(conn)["checks"] if c["id"] == "R4")
    assert r4["coverage"] == "TESTED"
    assert r4["verdict"] == "UNMEASURED"
    assert "no renames declared" in r4["receipt"]
