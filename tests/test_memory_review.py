import sqlite3
import asyncio

from helicon.db import init_db
from helicon.embeddings import init_embedding_table
from helicon.memory_review import memory_review


def test_live_vector_denominator_and_search_use_real_store(tmp_path):
    conn = init_db(str(tmp_path / "review.db"))
    init_embedding_table(conn)
    for rid, status in (("live", "pending"), ("dead", "killed")):
        conn.execute("INSERT INTO helicon_cubes (id,source,source_ref,type,title,content,content_hash,created_at,valid_from,review_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (rid, "test", "local", "fact", "ZUP", "ZUP memory", rid, "2026-09-04", "2026-09-04", status))
        conn.execute("INSERT INTO cube_embeddings(cube_id,embedding,embedded_at,model,dim) VALUES (?,?,?,?,?)",
                     (rid, b"abcd", "2026-09-04", "test", 1))
    conn.commit()
    before = conn.total_changes
    report = memory_review(conn, trace_db=tmp_path / "absent.db")
    checks = {c["id"]: c for c in report["checks"]}
    assert checks["embeddings"]["rows"] == [{"live_memories": 1, "with_embeddings": 1}]
    assert checks["search"]["rows"][0]["ids"] == ["live"]
    assert checks["retrieval"]["rows"][0]["recorded_events"] == 0
    assert checks["correctness"]["status"] == "unmeasured"
    assert conn.total_changes == before
    conn.close()


def test_missing_instruments_are_not_green(tmp_path):
    report = memory_review(sqlite3.connect(":memory:"), trace_db=tmp_path / "absent.db")
    assert all(c["status"] == "unmeasured" for c in report["checks"])
    assert all(stage['state'] == 'unavailable' for stage in report['stages'])
    assert report['findings'][0]['kind'] == 'source-unavailable'


def test_empty_is_not_unavailable_or_useful(tmp_path):
    conn = init_db(str(tmp_path / 'memory.db'))
    init_embedding_table(conn)
    path = tmp_path / 'trace.db'
    with sqlite3.connect(path) as index:
        index.execute('CREATE TABLE messages(session_id TEXT, cwd TEXT, ts TEXT)')
    before = conn.total_changes
    report = memory_review(conn, trace_db=path)
    assert all(stage['state'] == 'empty' for stage in report['stages'])
    assert report['stages'][2]['summary'] == '0 of 0 live memories have vectors'
    assert conn.total_changes == before


def test_bad_transcript_fields_are_actionable_without_freshness_claim(tmp_path):
    conn = init_db(str(tmp_path / 'memory.db'))
    init_embedding_table(conn)
    path = tmp_path / 'trace.db'
    with sqlite3.connect(path) as index:
        index.execute('CREATE TABLE messages(session_id TEXT, cwd TEXT, ts TEXT)')
        index.execute("INSERT INTO messages VALUES ('a', NULL, 'invalid')")
    report = memory_review(conn, trace_db=path)
    assert report['stages'][0]['watermark'] is None
    assert any(f['kind'] == 'incomplete-transcript-fields' for f in report['findings'])


def test_operating_endpoint_does_not_run_census_or_write_snapshot(tmp_path, monkeypatch):
    import helicon.api.app  # app owns router registration; initialise it first
    from helicon.api import setup
    conn = init_db(str(tmp_path / 'memory.db'))
    init_embedding_table(conn)
    monkeypatch.setattr(setup, 'get_conn', lambda: conn)
    monkeypatch.setattr(setup, 'memory_review', lambda c: memory_review(c, trace_db=tmp_path / 'missing.db'))
    monkeypatch.setattr(setup, 'project_review', lambda: {'status': 'unmeasured'})
    def forbidden(*args):
        raise AssertionError('A quiet evidence read must not run census or snapshots')
    monkeypatch.setattr(setup, 'census', forbidden)
    monkeypatch.setattr(setup, '_snapshots', forbidden)
    before = conn.total_changes
    result = asyncio.run(setup.operating_review())
    assert result['memory_review']['stages'][0]['state'] == 'unavailable'
    assert conn.total_changes == before
