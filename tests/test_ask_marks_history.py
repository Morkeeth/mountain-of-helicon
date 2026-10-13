"""A note that `helicon truth` would flag retired or expired is labelled history in ask."""
import sqlite3
from datetime import date

from helicon.models import ConnectorResult


def _store(tmp_path, notes):
    from helicon.db import init_db, insert_cube
    from helicon.scanner import result_to_cube

    db = str(tmp_path / "store.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    for ref, title, content, meta in notes:
        insert_cube(conn, result_to_cube(ConnectorResult(
            source="obsidian", source_ref=ref, type="project", title=title, content=content,
            created_at="2026-10-01T00:00:00", metadata=meta)))
    conn.commit()
    return conn


def test_history_reason_uses_the_signals_of_truth():
    from helicon.truth import history_reason

    today = date(2026, 10, 13)
    assert history_reason("RETIRED 1 Sep. The kite stall moved.", today=today) == "retired marker (RETIRED)"
    assert history_reason("The kite stall plan.", status="PARKED", today=today) == "retired marker (PARKED)"
    assert history_reason("Kite stall: submit by Sep 3 at the fair.", today=today).startswith("expired dated claim (40d past")
    assert history_reason("---\nhistory: closed 2026-09-05\n---\nKite stall: submit by Sep 3.", today=today) == "closed by the operator"
    assert history_reason("The kite stall sells twelve kites a day. Deadline Dec 20.", today=today) == ""


def test_ask_labels_retired_and_expired_notes_as_history(tmp_path, monkeypatch):
    from helicon.retrieve_guard import format_guarded_context, guarded_context

    monkeypatch.setenv("HELICON_RULINGS_FILE", "")
    conn = _store(tmp_path, [
        ("a.md", "Kite stall price list", "The kite stall sells a kite for nine coins.", {}),
        ("b.md", "Kite stall old price list", "SUPERSEDED by the new list.\nThe kite stall sells a kite for four coins.", {}),
        ("c.md", "Kite stall fair entry", "Kite stall entry: submit by Sep 3 at the fair desk.", {}),
        ("d.md", "Kite stall parked plan", "The kite stall opens a second desk.", {"status": "PARKED"}),
    ])
    res = guarded_context(conn, "What does the kite stall sell a kite for?", today=date(2026, 10, 13))
    standing = {m["title"]: (m["standing"], m["history_reason"]) for m in res["safe_context"]}
    assert standing["Kite stall price list"] == ("current", "")
    assert standing["Kite stall old price list"] == ("history", "retired marker (SUPERSEDED)")
    assert standing["Kite stall fair entry"][0] == "history" and "expired dated claim" in standing["Kite stall fair entry"][1]
    assert standing["Kite stall parked plan"] == ("history", "retired marker (PARKED)")
    assert res["history_count"] == 3
    assert [m["standing"] for m in res["safe_context"]] == ["current", "history", "history", "history"]

    text = format_guarded_context(res)
    line = next(l for l in text.splitlines() if "Kite stall old price list" in l)
    assert "HISTORY, not a current claim" in line and "✓" not in line
    assert "✓" in next(l for l in text.splitlines() if l.rstrip().endswith("Kite stall price list"))
