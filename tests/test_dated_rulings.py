"""Dated rulings: the operator's quoted decisions reach `helicon ask`, newest first."""
import json

import pytest

from helicon import dated_rulings


@pytest.fixture
def log(tmp_path, monkeypatch):
    rows = [
        {"ts": "2026-10-02T17:40:00+02:00", "text": "Priority: the lunch stall ships for the fair deadline.",
         "quote": "lunch stall is prio", "source": "chat 2 Oct"},
        {"ts": "2026-10-06T22:30:00+02:00", "text": "The lunch stall is killed. No entry at the fair deadline.",
         "quote": "we kill it", "source": "chat 6 Oct"},
        {"ts": "2026-09-27T10:00:00+02:00", "text": "Videos are longer and cinematic, not vertical shorts.",
         "quote": "longer cinematic ones", "source": "chat 27 Sep"},
    ]
    path = tmp_path / "rulings.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n\n", encoding="utf-8")
    monkeypatch.setenv("HELICON_RULINGS_FILE", str(path))
    return path


def test_newest_matching_ruling_comes_first(log):
    found = dated_rulings.match_rulings("Is the lunch stall still shipping for the fair deadline?")
    assert [r["date"] for r in found] == ["2026-10-06", "2026-10-02"]
    assert found[0]["newest"] is True and found[1]["newest"] is False
    assert "killed" in found[0]["text"]


def test_unrelated_question_matches_nothing(log):
    assert dated_rulings.match_rulings("Which database engine stores the payments?") == []


def test_broken_line_is_skipped_not_guessed(log):
    assert len(dated_rulings.load_rulings()) == 3


def test_reader_off_or_file_absent_returns_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_RULINGS_FILE", "")
    assert dated_rulings.rulings_path() is None
    assert dated_rulings.match_rulings("Is the lunch stall still shipping?") == []
    monkeypatch.setenv("HELICON_RULINGS_FILE", str(tmp_path / "absent.jsonl"))
    assert dated_rulings.load_rulings() == []


def test_ask_output_names_the_current_ruling(log):
    from helicon.retrieve_guard import format_guarded_context

    res = {"task": "q", "trusted_answer": [], "flagged_context": [], "suppressed_count": 0, "safe_context": [],
           "dated_rulings": dated_rulings.match_rulings("Is the lunch stall still shipping for the fair deadline?")}
    text = format_guarded_context(res)
    assert "no ruling covers" not in text
    assert text.index("[CURRENT]") < text.index("[older")
