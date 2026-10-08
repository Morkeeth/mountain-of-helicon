"""`helicon start`: one card, read only, honest about what it could not read."""
import json
import os
import sqlite3

from helicon import start


def _empty_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_RULINGS_FILE", "")
    return str(tmp_path)


def test_empty_machine_says_nothing_found_not_zero(tmp_path, monkeypatch):
    home = _empty_home(tmp_path, monkeypatch)
    card = start.build_card(str(tmp_path), home=home)
    assert all(card[k]["found"] is False for k in ("instructions", "memory", "decisions", "skills", "index"))
    text = start.format_card(card)
    assert text.count("nothing found") == 5
    assert "0 of" not in text
    assert "not added up" in text


def test_decisions_row_reads_the_ruling_log(tmp_path, monkeypatch):
    log = tmp_path / "rulings.jsonl"
    log.write_text(json.dumps({"ts": "2026-10-06T10:00:00", "text": "The stall is closed."}) + "\n", encoding="utf-8")
    monkeypatch.setenv("HELICON_RULINGS_FILE", str(log))
    part = start.read_decisions()
    assert part == {"found": True, "read": str(log), "rulings": 1, "newest": "2026-10-06"}


def test_skills_never_opened_comes_from_the_transcript_index(tmp_path, monkeypatch):
    home = _empty_home(tmp_path, monkeypatch)
    for name in ("used", "unused"):
        folder = tmp_path / ".claude" / "skills" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("x", encoding="utf-8")
    assert start.read_skills(home)["opened_known"] is False
    os.makedirs(tmp_path / ".trace")
    con = sqlite3.connect(tmp_path / ".trace" / "trace.db")
    con.execute("CREATE TABLE messages (session_id TEXT, ts TEXT, text TEXT)")
    con.execute("INSERT INTO messages VALUES ('s1', '2026-10-07T10:00:00Z', 'Launching skill: used')")
    con.commit()
    con.close()
    part = start.read_skills(home)
    assert part["never_opened"] == 1 and part["never_opened_names"] == ["unused"]
    index = start.read_index(home)
    assert index["sessions"] == 1 and index["newest"] == "2026-10-07"


def test_next_steps_are_capped_at_three_and_worst_first():
    card = {
        "instructions": {"found": True, "read": "/r", "broken": 2, "checked": 2},
        "memory": {"found": True, "read": ["/m"], "rotten": 4, "files": 9},
        "decisions": {"found": False, "why": "x"},
        "skills": {"found": True, "opened_known": True, "never_opened": 3, "installed": 8},
        "index": {"found": False, "why": "x"},
    }
    steps = start.next_steps(card)
    assert len(steps) == 3
    assert steps[0] == "Fix the 2 things your instructions point to that are missing or wrong."


def test_a_stale_install_is_the_first_next_step():
    card = {
        "install": {"found": True, "read": "/tree", "git": True, "branch": "old", "behind_main": 38, "changed_files": 2},
        "instructions": {"found": False, "why": "x"}, "memory": {"found": False, "why": "x"},
        "decisions": {"found": True, "rulings": 1, "newest": "2026-10-07"},
        "skills": {"found": False, "why": "x"}, "index": {"found": True, "sessions": 1, "newest": "2026-10-07"},
    }
    card["next"] = start.next_steps(card)
    assert card["next"][0] == "Update Helicon first. It is out of date."
    text = start.format_card(card)
    assert "out of date, 38 updates behind" in text
    assert "commit" not in text and "/tree" not in text.split("Do next")[0]  # no plumbing in the readings


def test_install_row_reads_the_tree_this_code_runs_from():
    part = start.read_install()
    assert part["found"] is True and os.path.isdir(part["read"])


def test_page_draws_the_card_and_refuses_a_total(tmp_path, monkeypatch):
    from helicon.start_html import render

    card = start.build_card(str(tmp_path), home=_empty_home(tmp_path, monkeypatch))
    card["memory"] = {"found": True, "read": ["/m"], "files": 390, "rotten": 0}
    card["index"] = {"found": True, "read": "/t", "sessions": 3649, "newest": "2026-10-07", "files_with_warnings": 0}
    from datetime import datetime

    page = render(card, when=datetime(2026, 10, 9, 8, 30))  # a fixed clock: the page must not depend on today
    assert "No total." in page and page.count("nothing found") == 3
    assert "3,649" in page and "The latest is from 7 Oct." in page and "9 Oct 2026, 08:30" in page
    assert 'aria-label="0 of 390"></div>' in page  # zero of something draws no fill
    assert "http://" not in page and "https://" not in page  # one local file, no network


def test_history_keeps_one_reading_per_day_and_gives_a_trend(tmp_path):
    path = str(tmp_path / "h.jsonl")
    card = {"instructions": {"found": True, "read": "/r", "broken": 2}, "memory": {"found": True, "rotten": 9},
            "decisions": {"found": False}, "skills": {"opened_known": True, "never_opened": 7},
            "index": {"found": True, "sessions": 10}}
    start.record_reading(card, "2026-10-07T10:00:00+02:00", path)
    card["memory"]["rotten"] = 6
    start.record_reading(card, "2026-10-07T22:00:00+02:00", path)
    card["memory"]["rotten"] = 4
    start.record_reading(card, "2026-10-08T09:00:00+02:00", path)
    history = start.load_history(path)
    assert [row["at"][:10] for row in history] == ["2026-10-07", "2026-10-08"]
    assert start.trend(history, "memory_rotten") == -2
    assert start.trend(history, "rulings") is None  # a reading that was never found has no trend
    assert start.trend(history[:1], "memory_rotten") is None


def test_readings_are_sentences_without_paths_or_tool_words(tmp_path, monkeypatch):
    card = start.build_card(str(tmp_path), home=_empty_home(tmp_path, monkeypatch))
    card["install"] = {"found": True, "read": "/tree", "git": True, "branch": "b", "behind_main": 0}
    card["instructions"] = {"found": True, "read": "/r", "checked": 11, "broken": 0, "grade": "A"}
    card["memory"] = {"found": True, "read": ["/m"], "files": 390, "rotten": 1}
    text = start.format_card(card)
    assert "11 of 11 things your agent instructions point to exist. Nothing is wrong." in text
    assert "1 of 390 notes your agents remember are out of date." in text
    assert "Look at the 1 out-of-date note and fix or delete it." in text
    for plumbing in ("/tree", "branch", "grade", "repo", "checked lines", "(s)"):
        assert plumbing not in text


def test_share_holds_numbers_only_and_null_for_what_was_not_found(tmp_path, monkeypatch):
    card = start.build_card(str(tmp_path), home=_empty_home(tmp_path, monkeypatch))
    assert start.share(card)["readings_found"] == 0 and start.share(card)["memory"] is None
    card["install"] = {"read": "/secret/tree", "behind_main": 0}
    card["instructions"] = {"found": True, "read": "/secret/repo", "checked": 10, "broken": 1}
    card["memory"] = {"found": True, "read": ["/secret/memory"], "files": 400, "rotten": 4}
    card["skills"] = {"found": True, "opened_known": True, "installed": 40, "never_opened": 10,
                      "never_opened_names": ["private-skill"], "read": "/secret/trace.db"}
    out = start.share(card)
    assert out["instructions"]["true_rate"] == 0.9 and out["memory"]["fresh_rate"] == 0.99
    assert out["skills"]["used_rate"] == 0.75 and out["readings_found"] == 3
    text = json.dumps(out)
    assert "secret" not in text and "private-skill" not in text and "/" not in text
