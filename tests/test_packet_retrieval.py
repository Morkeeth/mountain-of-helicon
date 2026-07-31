"""A governed run's packet must actually contain memory.

Found by dogfooding the live doorway: `helicon run open` reported a clean gate,
froze a packet, hashed it, verified it — and the packet had ZERO items, so the
delivery hook had nothing to inject and `helicon receipt` could only ever say
UNVERIFIABLE.

The cause was the candidate query: `lower(content) LIKE '%<query>%'`, where the
query is the objective's first 40 characters. Real objectives are sentences
("wire the doorway gate into a live Claude Code session") and no memory contains
one verbatim, so the match returned nothing — for every governed run ever opened.
It was invisible precisely because every downstream check still passed on an
empty packet.

These pin the property that matters: a run whose objective has relevant memory
gets a packet with that memory in it.
"""
import pytest

from helicon import taskrun
from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube
from helicon.scanner import make_id, content_hash


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _cube(conn, title, content, status="approved"):
    c = HeliconCube(
        id=make_id(), source="obsidian", source_ref="vault/note.md", type="memory",
        title=title, content=content, summary="", content_hash=content_hash(content),
        created_at="2026-07-01T00:00:00", valid_from="2026-07-01T00:00:00",
        last_reinforced="2026-07-01T00:00:00", confidence=0.9, review_status=status)
    insert_cube(conn, c)
    conn.commit()
    return c.id


def test_a_sentence_objective_still_retrieves_its_memory(conn):
    """The exact failure: the objective is a sentence, the memory is about the
    same subject, and no memory contains the sentence verbatim."""
    wanted = _cube(conn, "Doorway gate",
                   "The doorway gate blocks a session against a contradicted repo.")
    _cube(conn, "Unrelated", "Notes about a football scraper and its cron.")

    rows = taskrun._candidates(
        conn, "wire the doorway gate into a live Claude Code session")
    assert wanted in [r["id"] for r in rows], \
        "a sentence objective retrieved nothing — the substring bug is back"


def test_the_packet_built_from_it_is_not_empty(conn):
    _cube(conn, "Doorway gate",
          "The doorway gate blocks a session against a contradicted repo.")
    rid = taskrun.open_run(conn, "wire the doorway gate into a live session",
                           "the gate blocks", repo_ref="/tmp/x@abc")
    packet = taskrun.build_packet(conn, rid, query="wire the doorway gate")
    assert packet["included"], "a governed run froze an empty packet"
    assert taskrun.render_packet(conn, rid)["items"] > 0


def test_a_literal_token_query_still_works(conn):
    """The substring path stays as the fallback — callers that pass a literal
    token rather than a sentence must not regress."""
    wanted = _cube(conn, "Zephyr", "The zephyr-widget ships on Tuesday.")
    rows = taskrun._candidates(conn, "zephyr-widget")
    assert wanted in [r["id"] for r in rows]


def test_retired_memory_never_reaches_a_packet_on_either_path(conn):
    """Retired means retired on EVERY path — the ranked path must honour it too,
    not just the substring fallback it replaced."""
    for status in ("killed", "superseded"):
        dead = _cube(conn, f"Doorway {status}",
                     "The doorway gate blocks a contradicted repo.", status=status)
        rows = taskrun._candidates(conn, "doorway gate blocks a contradicted repo")
        assert dead not in [r["id"] for r in rows], f"{status} memory reached a packet"


def test_no_query_still_returns_live_memory(conn):
    wanted = _cube(conn, "Anything", "Some live memory.")
    assert wanted in [r["id"] for r in taskrun._candidates(conn, "")]
