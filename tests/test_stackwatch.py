"""Stackwatch: routines, dead paths, context weight — the harness under the exam."""
import pytest

from helicon.db import init_db, insert_cube
from helicon.models import ConnectorResult
from helicon.scanner import result_to_cube
from helicon.stackwatch import (
    _cron_interval_minutes, output_findings, stack_scan,
)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "helicon.db"))


def _claim_cube(conn, path, when="now"):
    r = ConnectorResult(
        source="claude-code", source_ref="session_x", type="file_created",
        title=f"Created: {path.split('/')[-1]}",
        content=f"File: {path}\nsome body",
        created_at=__import__("datetime").datetime.utcnow().isoformat())
    cube = result_to_cube(r)
    assert insert_cube(conn, cube)
    conn.commit()
    return cube.id


def test_cron_interval_parsing():
    assert _cron_interval_minutes("*/30 * * * * x") == 30
    assert _cron_interval_minutes("0 */6 * * * x") == 360
    assert _cron_interval_minutes("15 * * * * x") == 60
    assert _cron_interval_minutes("bad") is None


def test_dead_path_is_a_finding_ephemeral_is_not(conn, tmp_path):
    real = tmp_path / "exists.md"
    real.write_text("hi")
    _claim_cube(conn, str(real))                      # exists -> no finding
    _claim_cube(conn, str(tmp_path / "gone.md"))      # missing -> finding
    _claim_cube(conn, "/tmp/ephemeral/scratch.md")    # ephemeral -> excluded
    got = output_findings(conn, ephemeral=('/tmp/',))
    assert len(got) == 1
    assert "gone.md" in got[0]["finding"]
    assert "dead path" in got[0]["finding"]


def test_stack_scan_files_once(conn, tmp_path):
    import helicon.stackwatch as SW
    _claim_cube(conn, str(tmp_path / "vanished.md"))
    orig = SW.EPHEMERAL
    SW.EPHEMERAL = ("/tmp/",)
    try:
        first = stack_scan(conn)
        assert first["output"] == 1
        assert stack_scan(conn)["output"] == 0  # idempotent
    finally:
        SW.EPHEMERAL = orig
    n = conn.execute("SELECT COUNT(*) FROM audit_log "
                     "WHERE audit_type='output'").fetchone()[0]
    assert n == 1


def test_cron_interval_skips_dow_dom_restricted_jobs():
    """P1: weekly/monthly jobs were being called daily -> false dead-limb
    findings every Thursday."""
    assert _cron_interval_minutes("0 0 * * 0 job") is None       # weekly
    assert _cron_interval_minutes("0 0 1 * * job") is None       # monthly
    assert _cron_interval_minutes("15 3 * * 1-5 job") is None    # weekdays
    assert _cron_interval_minutes("*/30 * * * * job") == 30      # still works


def test_concurrent_double_file_blocked_by_unique_index(conn, tmp_path):
    """P1: watch cron + evolve racing the same selector must not double-file.
    The read-then-insert dedup loses the race; the unique index wins it."""
    import sqlite3 as s3
    from helicon.db import insert_audit
    from helicon.models import AuditResult
    a = AuditResult(audit_type="output", target_type="stack", target_id="k",
                    finding="x", severity="warning",
                    details={"key": "output|/race"}, audited_at="2026-07-06")
    assert insert_audit(conn, a) is not None
    assert insert_audit(conn, a) is None  # second filer rejected, no raise
