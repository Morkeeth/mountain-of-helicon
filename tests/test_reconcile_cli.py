"""glaze reconcile CLI: dry-run reports orphans without writing; --apply retires
them as 'superseded'; human-reviewed (approved/killed) cubes are never touched.

Runs cmd_reconcile end-to-end against a temp SQLite DB with the connector
re-scan faked, so the hash-matching path (scanner.content_hash on raw connector
content, same as result_to_cube) is exercised exactly as production does it.
"""
import json
from types import SimpleNamespace

import pytest

from glaze import cli
from glaze.db import init_db, insert_cube
from glaze.models import ConnectorResult
from glaze.scanner import collect_present_hashes, content_hash, result_to_cube

SOURCE = "agent-rules"
SCOPE = "repo/CLAUDE.md"


def _result(content, heading):
    return ConnectorResult(
        source=SOURCE,
        source_ref=f"{SCOPE}#{heading}",
        type="memory",
        title=f"[rule] {heading}",
        content=content,
        created_at="2026-07-01T00:00:00",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temp DB seeded with 4 cubes; a fake re-scan that only still sees one.

    kept      - pending, content present in re-scan -> must survive
    stale     - pending, content gone -> the one reconcile should retire
    approved  - human-approved, content gone -> never touched
    killed    - human-killed, content gone -> never touched
    """
    db_path = str(tmp_path / "glaze.db")
    conn = init_db(db_path)

    results = {
        "kept": _result("keep this section", "keep"),
        "stale": _result("stale section that was edited away", "stale"),
        "approved": _result("approved but gone", "approved-gone"),
        "killed": _result("killed and gone", "killed-gone"),
    }
    ids = {}
    for name, r in results.items():
        cube = result_to_cube(r)  # ingestion path: hash computed by result_to_cube
        assert insert_cube(conn, cube)
        ids[name] = cube.id
    conn.execute("UPDATE glaze_cubes SET review_status='approved' WHERE id=?",
                 (ids["approved"],))
    conn.execute("UPDATE glaze_cubes SET review_status='killed' WHERE id=?",
                 (ids["killed"],))
    conn.commit()

    config = {"db_path": db_path, "connectors": {SOURCE: {"enabled": True}}}
    monkeypatch.setattr("glaze.config.load_config", lambda path=None: config)
    # fake re-scan: only the 'kept' section is still present
    monkeypatch.setattr("glaze.scanner.scan_all", lambda cfg: [results["kept"]])

    def status(name):
        return conn.execute("SELECT review_status FROM glaze_cubes WHERE id=?",
                            (ids[name],)).fetchone()["review_status"]

    return SimpleNamespace(conn=conn, ids=ids, results=results, status=status,
                           config=config)


def test_collect_present_hashes_matches_ingestion(env):
    scopes = collect_present_hashes(env.config)
    assert set(scopes) == {(SOURCE, SCOPE)}
    # the crux: the re-scan hash must equal the hash stored at ingestion
    stored = env.conn.execute(
        "SELECT content_hash FROM glaze_cubes WHERE id=?", (env.ids["kept"],)
    ).fetchone()["content_hash"]
    assert scopes[(SOURCE, SCOPE)] == {stored}
    assert stored == content_hash(env.results["kept"].content)


def test_dry_run_reports_orphan_and_writes_nothing(env, capsys):
    cli.cmd_reconcile(SimpleNamespace(apply=False, source=None))
    out = capsys.readouterr().out

    assert env.ids["stale"] in out
    assert "[rule] stale" in out
    assert f"{SCOPE}#stale" in out           # source_ref is printed
    assert "Would retire 1" in out
    assert env.ids["kept"] not in out
    # nothing written
    for name in ("kept", "stale"):
        assert env.status(name) == "pending"
    assert env.status("approved") == "approved"
    assert env.status("killed") == "killed"


def test_apply_retires_orphan_never_touches_reviewed(env, capsys):
    cli.cmd_reconcile(SimpleNamespace(apply=True, source=None))
    out = capsys.readouterr().out

    assert "Retired 1" in out
    assert env.status("stale") == "superseded"
    conf = env.conn.execute("SELECT confidence FROM glaze_cubes WHERE id=?",
                            (env.ids["stale"],)).fetchone()["confidence"]
    assert conf <= 0.05
    # present cube and human-reviewed cubes untouched
    assert env.status("kept") == "pending"
    assert env.status("approved") == "approved"
    assert env.status("killed") == "killed"

    # idempotent: a second apply retires nothing
    cli.cmd_reconcile(SimpleNamespace(apply=True, source=None))
    assert "Nothing to retire" in capsys.readouterr().out


def test_source_filter_skips_other_sources(env, capsys):
    cli.cmd_reconcile(SimpleNamespace(apply=True, source="obsidian"))
    out = capsys.readouterr().out
    assert "Not retiring anything" in out
    assert env.status("stale") == "pending"
