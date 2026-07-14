"""Live guard: the agent consults the law before it writes.

Hermetic: seed a rename + an identity ruling, assert the guard blocks a
ruled-against claim and a dead-name claim, and passes clean output. This is
rulings-become-law made enforceable at write time.
"""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.aliases import add_alias
from helicon.identity import identity_scan, resolve_identity
from helicon.guard import guard_output


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "h.db"))


def _cube(conn, content, ref):
    r = ConnectorResult(source="obsidian", source_ref=ref, type="memory",
                        title=ref, content=content, created_at="2026-07-01T00:00:00")
    insert_cube(conn, result_to_cube(r))
    conn.commit()


def test_dead_name_is_flagged(conn):
    add_alias(conn, "RELAY", "FAVOUR", "2026-07-02T00:00:00", note="rebrand executed")
    res = guard_output(conn, "RELAY just shipped its points sink this week.")
    assert res["clean"] is False
    assert any(v["rule"] == "rename" and "FAVOUR" in v["message"] for v in res["violations"])


def test_ruled_identity_is_blocked(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    resolve_identity(conn, aid, "a yield treasury")     # canonical = treasury
    res = guard_output(conn, "Yieldbound is a wallet tracker that reads balances.")
    assert res["verdict"] == "blocked"                  # a critical ruling contradicts it
    assert any(v["rule"] == "identity-ruling" for v in res["violations"])


def test_clean_output_passes(conn):
    add_alias(conn, "RELAY", "FAVOUR", "2026-07-02T00:00:00")
    res = guard_output(conn, "FAVOUR is live with real money.")
    assert res["clean"] is True and res["verdict"] == "clean"


def test_reasserting_the_ruled_truth_is_clean(conn):
    _cube(conn, "Yieldbound is a yield treasury.", "a.md")
    _cube(conn, "Yieldbound is a wallet tracker.", "b.md")
    identity_scan(conn, semantic=False)
    aid = conn.execute("SELECT id FROM audit_log WHERE audit_type='identity'").fetchone()[0]
    resolve_identity(conn, aid, "a yield treasury")
    res = guard_output(conn, "Yieldbound is a yield treasury.")
    assert res["clean"] is True                         # the canonical definition passes
