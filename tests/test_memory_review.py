import sqlite3

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
