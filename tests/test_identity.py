"""R11 identity coherence — the deterministic genus tier.

Tests run with semantic=False (no embeddings/torch): the genus-mismatch core is
what must be provably correct. A definition that forks across sources fires; status
prose, same-genus, and single-source do not.
"""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.identity import extract_glosses, find_identity_forks, identity_scan


def _cube(conn, content, ref, source="obsidian"):
    r = ConnectorResult(source=source, source_ref=ref, type="memory",
                        title=ref, content=content, created_at="2026-07-01T00:00:00")
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


# --- extraction: the article gate is the precision core --------------------

def test_article_gate_keeps_definitions_drops_status():
    got = {g["genus"] for g in extract_glosses("Yieldbound is a yield treasury.")}
    assert "treasury" in got
    # no article => status/adjective prose, not an identity definition
    assert extract_glosses("Relay is live and shipped.") == []
    assert extract_glosses("node is old now.") == []
    assert extract_glosses("the commit is feat not fix.") == []


def test_genus_is_the_head_noun():
    # head-final compound; the clause is cut at the preposition
    g = extract_glosses("Bagel is a remote automation bot on the VPS.")
    assert any(x["genus"] == "bot" for x in g)


# --- forks: the cross-source, incompatible-genus signal --------------------

def test_cross_source_fork_fires(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "mindmap.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "trades.md")
    forks = find_identity_forks(conn, semantic=False)
    assert len(forks) == 1
    f = forks[0]
    assert f["name"] == "yieldbound"
    assert {f["genus_a"], f["genus_b"]} == {"treasury", "tracker"}
    assert len(f["scopes"]) == 2


def test_same_genus_is_not_a_fork(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a treasury.", "b.md")
    assert find_identity_forks(conn, semantic=False) == []


def test_single_source_is_not_a_fork(conn):
    # two genera but one source scope — not cross-source, so not a fork
    _cube(conn, "Yieldbound is a treasury. Later: Yieldbound is a tracker.", "one.md")
    assert find_identity_forks(conn, semantic=False) == []


def test_status_prose_does_not_fork(conn):
    _cube(conn, "Relay is live.", "a.md")
    _cube(conn, "Relay is shipped.", "b.md")
    assert find_identity_forks(conn, semantic=False) == []


# --- filing: same audit_log plumbing, idempotent ---------------------------

def test_identity_scan_files_once(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    r1 = identity_scan(conn, semantic=False)
    assert len(r1["filed"]) == 1
    assert r1["filed"][0]["pair_key"] == "identity|yieldbound"

    r2 = identity_scan(conn, semantic=False)         # idempotent by pair_key
    assert r2["filed"] == []

    n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    assert n == 1


def test_rot_exam_reports_r11(conn):
    from helicon.rot import run_rot_exam
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    res = run_rot_exam(conn)
    r11 = next((c for c in res["checks"] if c["id"] == "R11"), None)
    assert r11 is not None and r11["verdict"] == "ROT FOUND"
