import sqlite3

from helicon.checkin import (memory_candidates, read_state, score_answer,
                             transcript_index)
from helicon.db import init_db, insert_cube
from helicon.models import HeliconCube


def _state(tmp_path):
    p = tmp_path / "CURRENT.md"
    p.write_text(
        "## SHARED WORK STATE · revision abcdef123456 · rendered 2026-10-02\n"
        "### CLOSED. Not open work.\n"
        "- **OLD-DONE** · old · **COMPLETED**.\n"
        "### OPEN\n"
        "- **ONE-OPEN** · one · owner codex\n"
        "  - next: Inspect the real production result.\n"
        "- **TWO-OPEN** · two · owner claude\n"
        "- **THREE-OPEN** · three · owner cursor\n"
        "- **FOUR-OPEN** · four · owner oscar\n"
        "- **FIVE-OPEN** · five · owner agent\n"
        "### RULINGS AND FACTS, each with the object it was read from\n",
        encoding="utf-8",
    )
    return p


def test_checkin_score_has_fixed_denominator_and_can_go_red(tmp_path):
    state = read_state(str(_state(tmp_path)))
    good = score_answer(
        state,
        "abcdef123456 ONE-OPEN TWO-OPEN THREE-OPEN FOUR-OPEN FIVE-OPEN. "
        "For ONE-OPEN, inspect the real production result.",
    )
    assert good["score"] == 100

    stale = score_answer(
        state,
        "000000000000 OLD-DONE ONE-OPEN TWO-OPEN THREE-OPEN FOUR-OPEN. "
        "The old task is done.",
    )
    assert stale["score"] < 50
    assert stale["closed_ids"]["found"] == ["OLD-DONE"]


def test_transcript_index_reads_stable_views_without_writing(tmp_path):
    db = tmp_path / "trace.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE messages(session_id, project, harness, ts, cwd);"
        "CREATE VIEW v_messages AS SELECT * FROM messages;"
        "CREATE TABLE health(session_file, mtime, warnings);"
        "CREATE VIEW v_index_health AS SELECT * FROM health;"
    )
    con.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", [
        ("s1", "demo", "codex", "2026-10-02T09:00:00", "/x"),
        ("s1", "demo", "codex", "2026-10-02T10:00:00", "/x"),
    ])
    con.execute("INSERT INTO health VALUES (?,?,?)", ("one.jsonl", 1, "[]"))
    con.commit()
    con.close()

    before = db.stat().st_mtime_ns
    report = transcript_index(str(db))
    assert report["harnesses"]["codex"]["sessions"] == 1
    assert report["harnesses"]["codex"]["freshness"] in ("current", "stale")
    assert report["latest_sessions"][0]["session_id"] == "s1"
    assert db.stat().st_mtime_ns == before


def test_codex_memories_are_candidates_not_silent_merges(tmp_path):
    conn = init_db(str(tmp_path / "helicon.db"))
    insert_cube(conn, HeliconCube(
        id="codex-one", source="codex", source_ref="rollout.jsonl", type="memory",
        title="candidate", content="lesson", summary="lesson", content_hash="h",
        created_at="2026-10-02T10:00:00", valid_from="2026-10-02T10:00:00",
        review_status="pending",
    ))
    conn.commit()
    report = memory_candidates(conn)
    assert report["merge_policy"] == "human-review-only"
    assert report["by_status"]["pending"]["count"] == 1
