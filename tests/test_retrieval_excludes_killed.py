"""Retrieval must not serve retired memory (regression guard for the FTS leak).

The bug (fix/degraded-eval, d8b9156): the semantic path already loaded only
approved/pending cubes, but the FTS path (db.search_cubes) filtered nothing, so
hybrid_search re-introduced 'killed'/'superseded' cubes the semantic branch had
excluded — and the agent-facing MCP helicon_context served that retired memory.
That directly contradicts Helicon's "timely forgetting" thesis and produced the
3 BROKEN battery tasks.

This test pins the fix at the source: search_cubes excludes killed+superseded by
default, and only surfaces them when a review/browse caller opts in with
include_retired=True. On pre-fix main this FAILS (the killed cube leaks in).
"""
import pytest

from helicon.db import init_db, insert_cube, rebuild_fts, search_cubes
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube


def _cube(conn, content, ref, status="pending"):
    r = ConnectorResult(source="obsidian", source_ref=ref, type="memory",
                        title=ref, content=content,
                        created_at="2026-07-01T00:00:00")
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    if status != "pending":
        conn.execute("UPDATE helicon_cubes SET review_status=? WHERE id=?",
                     (status, cube.id))
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


# A distinctive term so FTS MATCH is unambiguous across both cubes.
QUERY = "zebrafish"


def test_search_cubes_excludes_killed_by_default(conn):
    live = _cube(conn, "the zebrafish protocol is approved", "live", status="approved")
    dead = _cube(conn, "the zebrafish protocol was wrong", "dead", status="killed")
    rebuild_fts(conn)

    ids = {c["id"] for c in search_cubes(conn, QUERY)}
    assert live in ids, "approved memory must still be retrievable"
    assert dead not in ids, "killed memory must not surface in retrieval"


def test_search_cubes_excludes_superseded_by_default(conn):
    live = _cube(conn, "zebrafish notes current", "live", status="approved")
    old = _cube(conn, "zebrafish notes stale", "old", status="superseded")
    rebuild_fts(conn)

    ids = {c["id"] for c in search_cubes(conn, QUERY)}
    assert live in ids
    assert old not in ids, "reconcile-retired memory must not surface in retrieval"


def test_include_retired_opt_in_still_sees_killed(conn):
    live = _cube(conn, "zebrafish approved row", "live", status="approved")
    dead = _cube(conn, "zebrafish killed row", "dead", status="killed")
    rebuild_fts(conn)

    ids = {c["id"] for c in search_cubes(conn, QUERY, include_retired=True)}
    assert live in ids and dead in ids, \
        "review/browse surfaces opt in with include_retired=True and see everything"
