"""A note marked as a closed record of the past is not rotten for holding old dates."""
from datetime import date

from helicon.truth import scan_store

BODY = "The run closed. Submit before the deadline Aug 13 and freeze by Aug 18.\n"


def _score(tmp_path, front):
    (tmp_path / "note.md").write_text(f"---\nname: note\n{front}---\n\n{BODY}", encoding="utf-8")
    res = scan_store(str(tmp_path), today=date(2026, 10, 8))
    return [reason for item in res["items"] for reason in item["reasons"]]


def test_old_deadlines_count_in_a_live_note(tmp_path):
    assert any("expired dated claim" in r[1] for r in _score(tmp_path, ""))


def test_old_deadlines_do_not_count_in_a_closed_history_note(tmp_path):
    assert not any("expired dated claim" in r[1] for r in _score(tmp_path, "history: closed 2026-10-08\n"))
