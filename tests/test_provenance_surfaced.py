"""The agent-facing tools must name the OBJECT, not just the ingester.

The bug, found 2026-09-04 by probing the store rather than the docs: every cube
carries source_ref, and it points at a real thing you can open. A vault path
(`01 Projects/Job Hunt/templates/company-research.md`), a repo and commit
(`waveradio-archive/c2576533`), a skill file (`skills/design-taste/SKILL.md`).
Measured on Oscar's live store at the time of the fix: 17,465 rows, 0 empty.

Both agent-facing read tools dropped that field on the way out and returned only
`source`, which is the name of the connector that ingested it. So an agent was
told a claim came from "obsidian" and could never open the file it came from.
A served memory that cannot be traced to its object is a claim with no author,
which is the exact failure mode Helicon exists to catch.

This pins the fix at both surfaces. On pre-fix main both tests FAIL.
"""
import json

import pytest

from helicon.db import init_db, insert_cube, search_cubes
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.mcp_server import cube_provenance, search_payload
from helicon.utility import init_utility_table

REF = "01 Projects/Job Hunt/where-this-came-from.md"
QUERY = "zebrafish"


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


@pytest.fixture
def cube_id(conn):
    r = ConnectorResult(source="obsidian", source_ref=REF, type="memory",
                        title="a note with a real address",
                        content="the zebrafish protocol lives here",
                        created_at="2026-09-04T00:00:00")
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


def test_search_rows_carry_the_object_reference(conn, cube_id):
    """helicon_search returns exactly search_payload(). Call that, not a copy.

    Asserting on rows from search_cubes would only prove the database layer
    carries source_ref. The bug was one level up, in the handler that dropped it.
    """
    rows = search_cubes(conn, QUERY, 5)
    assert rows, "fixture cube not found by FTS"
    payload = search_payload(rows)
    hit = next(p for p in payload if p["id"] == cube_id)
    assert hit["source"] == "obsidian", "the ingester name is still reported"
    assert hit["source_ref"] == REF, (
        "helicon_search returned the ingester but not the object. A reader told "
        "'obsidian' cannot open the file the claim came from."
    )
    json.dumps(payload)  # the tool serialises this, so it must stay JSON-safe


def test_context_provenance_query_selects_the_object_reference(conn, cube_id):
    """helicon_context builds its payload from cube_provenance(). Call THAT.

    The first version of this test retyped the SELECT inside the test body. It
    passed, and it would have gone on passing with source_ref deleted from
    mcp_server.py, because it was asserting against its own copy of the query.
    A guard for a wrong-object bug that is itself correct about the wrong object.
    Caught before it was relied on. The query now lives in one named function
    and this test calls it.
    """
    init_utility_table(conn)  # created by utility.py at runtime, not by init_db
    prov = cube_provenance(conn, cube_id)
    assert prov is not None
    assert prov["source_ref"] == REF, (
        "helicon_context's provenance lookup no longer carries the object "
        "reference, so the tool can only name the connector again."
    )


def test_the_column_is_populated_not_merely_present(conn, cube_id):
    """NOT NULL is not the same as useful. An empty string satisfies the schema.

    This is the check that would have caught the whole thing being cosmetic.
    """
    empty = conn.execute(
        "SELECT COUNT(*) FROM helicon_cubes "
        "WHERE source_ref IS NULL OR source_ref = ''"
    ).fetchone()[0]
    assert empty == 0
