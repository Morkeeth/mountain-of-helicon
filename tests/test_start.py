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
    assert len(steps) == 3 and steps[0].startswith("Fix 2 instruction")


def test_a_stale_install_is_the_first_next_step():
    card = {
        "install": {"found": True, "read": "/tree", "git": True, "branch": "old", "behind_main": 38, "changed_files": 2},
        "instructions": {"found": False, "why": "x"}, "memory": {"found": False, "why": "x"},
        "decisions": {"found": True, "rulings": 1, "newest": "2026-10-07"},
        "skills": {"found": False, "why": "x"}, "index": {"found": True, "sessions": 1, "newest": "2026-10-07"},
    }
    card["next"] = start.next_steps(card)
    assert card["next"][0].startswith("This Helicon is 38 commit(s) behind main")
    assert "STALE: 38 commit(s) behind main" in start.format_card(card)


def test_install_row_reads_the_tree_this_code_runs_from():
    part = start.read_install()
    assert part["found"] is True and os.path.isdir(part["read"])
