"""A private ruling that is newer on the subject must not leave an older public one as current."""
import json
import sqlite3

import pytest

from helicon import dated_rulings

QUESTION = "Which day does the Kite Workshop run?"
PRIVATE = {"ts": "2026-10-09T08:15:00+02:00", "title": "Xylophone clause",
           "text": "The Kite Workshop run day moves to Wednesday under the quokka plan.",
           "quote": "wombat says wednesday", "source": "ledger-of-narwhals", "private": True}
# Every word here must be absent from an agent answer. The date and the time are in it too.
SECRETS = ["xylophone", "wednesday", "quokka", "wombat", "narwhal", "2026-10-09", "08:15"]


def _log(tmp_path, monkeypatch, extra):
    rows = [
        {"ts": "2026-09-16T10:00:00+02:00", "title": "Kite Workshop day",
         "text": "The Kite Workshop run day is Saturday.", "quote": "saturday kites", "source": "chat 16 Sep"},
        {"ts": "2026-09-10T10:00:00+02:00", "title": "Kite Workshop day",
         "text": "The Kite Workshop run day is Sunday.", "quote": "sunday kites", "source": "chat 10 Sep"},
        {"ts": "2026-10-01T09:00:00+02:00", "text": "The bakery orders flour on Monday.", "quote": "flour", "source": "chat 1 Oct"},
    ] + extra
    path = tmp_path / "rulings.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("HELICON_RULINGS_FILE", str(path))
    return path


def _conn(tmp_path):
    from helicon.db import init_db

    db = str(tmp_path / "store.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def test_older_public_ruling_is_not_current_when_a_newer_private_one_exists(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [PRIVATE])
    found = dated_rulings.match_rulings(QUESTION, limit=5)
    kite = [r for r in found if "Kite" in r["text"]]
    assert len(kite) == 2
    assert all(r["standing"] == "possibly_superseded" for r in kite)
    assert all(r["newer_hidden"] is True and r["newest"] is False for r in kite)
    assert not [r for r in found if r["standing"] == "current"]
    assert dated_rulings.hidden_notice(found).startswith("A newer ruling on this subject exists")


def test_agent_answer_holds_nothing_of_the_private_row(tmp_path, monkeypatch):
    from helicon.mcp_server import handle_tool_call
    from helicon.retrieve_guard import format_guarded_context, guarded_context

    _log(tmp_path, monkeypatch, [PRIVATE])
    conn = _conn(tmp_path)
    out = handle_tool_call("helicon_ask", {"question": QUESTION, "limit": 5}, conn)
    answer = json.loads(out)
    assert answer["rulings_notice"]
    assert {r["standing"] for r in answer["dated_rulings"]} == {"possibly_superseded"}
    text = format_guarded_context(guarded_context(conn, QUESTION))
    assert "POSSIBLY SUPERSEDED" in text and "[CURRENT]" not in text
    for surface in (out.lower(), text.lower()):
        for secret in SECRETS:
            assert secret not in surface, secret
    # The count of hidden rows does not leave either: two private rows give the same answer as one.
    _log(tmp_path, monkeypatch, [PRIVATE, {**PRIVATE, "ts": "2026-10-11T08:15:00+02:00"}])
    again = json.loads(handle_tool_call("helicon_ask", {"question": QUESTION, "limit": 5}, conn))
    assert again["dated_rulings"] == answer["dated_rulings"] and again["rulings_notice"] == answer["rulings_notice"]


@pytest.mark.parametrize("private_row", [
    {**PRIVATE, "ts": "2026-09-12T08:15:00+02:00"},                                   # older than the public one
    {**PRIVATE, "ts": "2026-09-16T23:00:00+02:00"},                                   # the same day
    {"ts": "2026-10-09T08:15:00+02:00", "text": "The quokka budget is the zebra envelope.", "private": True},  # another subject
])
def test_a_private_row_that_is_not_newer_on_the_subject_changes_nothing(tmp_path, monkeypatch, private_row):
    _log(tmp_path, monkeypatch, [private_row])
    with_row = dated_rulings.match_rulings(QUESTION, limit=5)
    _log(tmp_path, monkeypatch, [])
    without = dated_rulings.match_rulings(QUESTION, limit=5)
    assert with_row == without
    assert with_row[0]["standing"] == "current" and "Saturday" in with_row[0]["text"]
    assert dated_rulings.hidden_notice(with_row) == ""


def test_operator_opt_in_reads_the_private_row_as_current(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [PRIVATE])
    found = dated_rulings.match_rulings(QUESTION, limit=5, include_private=True)
    assert found[0]["standing"] == "current" and "Wednesday" in found[0]["text"]
    assert all("newer_hidden" not in r for r in found)
