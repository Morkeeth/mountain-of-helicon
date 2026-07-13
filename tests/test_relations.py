"""R12 phantom association — a relation asserted by a single speculative source
that nothing else grounds. Deterministic; precision from a narrow conceptual-verb
list + the single-speculative-source + no-corroboration filter."""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.relations import extract_relations, find_phantom_relations, relation_scan


def _cube(conn, content, ref, source="obsidian", ctype="memory",
          created_at="2026-07-01T00:00:00"):
    r = ConnectorResult(source=source, source_ref=ref, type=ctype,
                        title=ref, content=content, created_at=created_at)
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


# --- extraction: conceptual verbs only, both endpoints capitalized -----------

def test_extract_conceptual_relation():
    got = extract_relations("Yieldbound rides the wave to World.")
    assert [(r["subj"], r["predicate"], r["obj"]) for r in got] == \
        [("yieldbound", "rides the wave to", "world")]


def test_code_keyword_is_not_a_relation():
    # 'extends' is a programming keyword, not a business relation
    assert extract_relations("SpeechRecognitionEvent extends Event.") == []
    assert extract_relations("SimNode extends GraphNode.") == []


# --- the phantom signal ------------------------------------------------------

def test_phantom_fires_single_speculative_uncorroborated(conn):
    _cube(conn, "Yieldbound rides the wave to World.", "idea.md", ctype="idea")
    p = find_phantom_relations(conn)
    assert len(p) == 1
    assert (p[0]["subj"], p[0]["obj"]) == ("yieldbound", "world")


def test_grounded_source_is_not_a_phantom(conn):
    # a project doc (not speculative) asserting it = a grounded claim, not a phantom
    _cube(conn, "Yieldbound rides the wave to World.", "proj.md", ctype="project")
    assert find_phantom_relations(conn) == []


def test_corroborated_relation_is_not_a_phantom(conn):
    _cube(conn, "Yieldbound rides the wave to World.", "idea.md", ctype="idea")
    # another source independently co-mentions both entities → grounded enough
    _cube(conn, "Notes on the Yieldbound and World partnership.", "proj.md", ctype="project")
    assert find_phantom_relations(conn) == []


def test_two_speculative_sources_is_not_a_phantom(conn):
    _cube(conn, "Yieldbound rides the wave to World.", "idea1.md", ctype="idea")
    _cube(conn, "As I noted, Yieldbound rides the wave to World.", "idea2.md", ctype="idea")
    assert find_phantom_relations(conn) == []


# --- filing ------------------------------------------------------------------

def test_resolve_relation_phantom_settles_and_records(conn):
    from helicon.relations import resolve_relation
    _cube(conn, "Yieldbound rides the wave to World.", "idea.md", ctype="idea")
    relation_scan(conn)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='provenance'").fetchone()[0]
    r = resolve_relation(conn, aid, "phantom")
    assert r["ok"] and r["correction_cube"]
    cube = conn.execute("SELECT review_status, content FROM helicon_cubes WHERE id=?",
                        (r["correction_cube"],)).fetchone()
    assert cube["review_status"] == "approved" and "PHANTOM" in cube["content"]
    # settled: no re-fire, no re-file
    assert find_phantom_relations(conn) == []
    assert relation_scan(conn)["filed"] == []


def test_resolve_relation_real_closes_without_cube(conn):
    from helicon.relations import resolve_relation
    _cube(conn, "Yieldbound rides the wave to World.", "idea.md", ctype="idea")
    relation_scan(conn)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='provenance'").fetchone()[0]
    r = resolve_relation(conn, aid, "real")
    assert r["ok"] and r["correction_cube"] is None
    assert find_phantom_relations(conn) == []          # ruled real → stays settled


def test_resolve_relation_rejects_bad(conn):
    from helicon.relations import resolve_relation
    assert not resolve_relation(conn, 99999)["ok"]


def test_relation_scan_files_once(conn):
    _cube(conn, "Yieldbound rides the wave to World.", "idea.md", ctype="idea")
    r1 = relation_scan(conn)
    assert len(r1["filed"]) == 1
    assert r1["filed"][0]["pair_key"] == "relation|yieldbound|world"
    assert relation_scan(conn)["filed"] == []            # idempotent
    n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE audit_type='provenance'").fetchone()[0]
    assert n == 1
