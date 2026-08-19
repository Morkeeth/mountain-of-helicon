"""Store truth — wrong-object ratios on a minimal store."""
import sqlite3

from helicon.store_truth import findings, render


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE helicon_cubes (review_status TEXT);
        CREATE TABLE retrieval_log (id INTEGER);
        CREATE TABLE reviews (session_id TEXT);
    """)
    for _ in range(100):
        conn.execute("INSERT INTO helicon_cubes (review_status) VALUES ('killed')")
    for _ in range(50):
        conn.execute("INSERT INTO helicon_cubes (review_status) VALUES ('approved')")
    for _ in range(3):
        conn.execute("INSERT INTO retrieval_log DEFAULT VALUES")
    for _ in range(1000):
        conn.execute("INSERT INTO reviews (session_id) VALUES ('auto-triage')")
    conn.execute("INSERT INTO reviews (session_id) VALUES ('cli-human-1')")
    conn.commit()
    return conn


def test_findings_surface_wrong_object_ratios():
    items = findings(_conn())
    assert len(items) == 2
    assert "barely read" in items[0]["title"]
    assert "150" in items[0]["lines"][0]
    assert "but only 3 logged retrievals ever." in items[0]["lines"][1]
    assert "machine" in items[1]["title"]


def test_render_includes_repro_and_footer():
    text = render(_conn(), ":memory:")
    assert "store truth" in text
    assert "SELECT COUNT(*) FROM helicon_cubes" in text
    assert "TRUE about one object" in text
