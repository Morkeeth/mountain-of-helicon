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


def _history_db(tmp_path, rows):
    os.makedirs(tmp_path / ".trace")
    con = sqlite3.connect(tmp_path / ".trace" / "trace.db")
    con.execute("CREATE TABLE messages (session_id TEXT, ts TEXT, text TEXT, is_human INTEGER, harness TEXT)")
    con.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", rows)
    con.commit()
    con.close()


def test_work_counts_typed_turns_per_tool_and_never_reads_spend_in_a_test_home(tmp_path, monkeypatch):
    home = _empty_home(tmp_path, monkeypatch)
    _history_db(tmp_path, [
        ("s1", "2026-10-07T10:00:00Z", "fix it", 1, "claude"),
        ("s1", "2026-10-07T10:01:00Z", "tool output", 0, "claude"),
        ("s2", "2026-10-08T09:00:00Z", "ship", 1, "codex"),
        ("s3", "2026-08-01T09:00:00Z", "old", 1, "codex"),
    ])
    work = start.read_work(home, today="2026-10-08")
    assert work["typed"] == 2 and work["by_tool"] == {"claude": 1, "codex": 1} and work["sessions"] == 2
    assert work["last_14_days"][-2:] == [1, 1] and len(work["last_14_days"]) == 14
    assert work["spend"] is None  # a test home never starts the spend tool


def test_work_rows_say_at_least_when_replies_have_no_price_and_nothing_found_without_the_tool():
    work = {"found": True, "days": 30, "typed": 6119, "by_tool": {"codex": 4477, "claude": 1061},
            "sessions": 786, "last_14_days": [0] * 13 + [5], "spend": None}
    rows = start.work_plain(work)
    assert rows[-1]["label"] == "Spend" and "nothing found" in rows[-1]["text"]
    work["spend"] = {"usd": 2014.37, "typed": 1184, "agent_messages": 40344, "unpriced_messages": 28693,
                     "tokens": 100, "tokens_reread": 97}
    by_label = {row["label"]: row for row in start.work_plain(work)}
    assert by_label["Spend"]["number"] == "$2,014" and by_label["Spend"]["unit"] == "or more, at list price" and "71% of agent replies have no price" in by_label["Spend"]["text"]
    assert by_label["Per prompt"]["number"] == "$1.70" and by_label["Per prompt"]["unit"] == "or more, each" and "34 agent replies" in by_label["Per prompt"]["text"]
    assert by_label["Re-reading"]["number"] == "97%"
    work["spend"]["unpriced_messages"] = 0
    assert start.work_plain(work)[2]["unit"] == "at list price"


def test_share_carries_work_numbers_and_no_text(tmp_path, monkeypatch):
    card = start.build_card(str(tmp_path), home=_empty_home(tmp_path, monkeypatch))
    assert start.share(card)["work"] is None
    card["work"] = {"found": True, "read": "/secret/trace.db", "days": 30, "typed": 10, "by_tool": {"claude": 10},
                    "sessions": 2, "last_14_days": [0] * 14, "spend": None}
    out = start.share(card)
    assert out["work"]["typed"] == 10 and "secret" not in json.dumps(out)


def test_routines_counts_job_files_and_reads_a_saved_cloud_reading(tmp_path, monkeypatch):
    import plistlib

    home = _empty_home(tmp_path, monkeypatch)
    assert start.read_routines(home)["found"] is False
    folder = tmp_path / "Library" / "LaunchAgents"
    folder.mkdir(parents=True)
    plistlib.dump({"Label": "me.job", "ProgramArguments": ["/no/such/program"]}, open(folder / "me.job.plist", "wb"))
    plistlib.dump({"Label": "com.apple.x", "ProgramArguments": ["/bin/ls"]}, open(folder / "com.apple.x.plist", "wb"))
    (folder / "me.job.plist.bak-2026").write_text("x", encoding="utf-8")
    os.makedirs(tmp_path / ".helicon")
    (tmp_path / ".helicon" / "cloud-routines.json").write_text(json.dumps(
        {"read_at": "2026-10-08", "routines": [{"name": "a", "on": True}, {"name": "b", "on": False}]}), encoding="utf-8")
    part = start.read_routines(home)
    assert part["jobs"] == 1 and part["missing_program"] == 1 and part["backups"] == 1
    assert part["known"] is False  # a test home never asks the system which jobs run
    assert part["cloud"] == {"on": 1, "off": 1, "read_at": "2026-10-08"}
    rows = {row["label"]: row for row in start.system_plain({"routines": part})}
    assert "Which ones run is unknown here" in rows["Routines"]["text"]
    assert rows["Cloud"]["number"] == 1 and "cannot read the cloud by itself" in rows["Cloud"]["text"]


def test_system_rows_in_plain_words_and_a_step_for_broken_jobs():
    card = {
        "install": {}, "instructions": {"found": False, "why": "x"}, "memory": {"found": False, "why": "x"},
        "decisions": {"found": True, "rulings": 1, "newest": "2026-10-08"},
        "skills": {"found": False, "why": "x"}, "index": {"found": True, "sessions": 1, "newest": "2026-10-08"},
        "routines": {"found": True, "jobs": 97, "running": 58, "failed": 14, "missing_program": 7, "not_running": 39,
                     "backups": 10, "cron_lines": 13, "known": True, "cloud": None},
        "size": {"found": True, "always_loaded_chars": 12394, "always_loaded_files": 8, "notes": 390, "long_notes": 4},
        "stalled": {"found": True, "projects": 89, "stalled": 21, "days": 30},
    }
    view = start.plain(card)
    rows = {row["label"]: row for row in view["system"]}
    assert rows["Routines"]["text"].startswith("scheduled jobs are running. 14 failed their last run.")
    assert rows["Left behind"]["number"] == 49 and rows["Notes"]["text"].endswith("4 of them are longer than a chapter.")
    assert rows["Stalled"]["number"] == 21 and rows["Stalled"]["unit"] == "of 89"
    assert any("scheduled jobs that failed or point at nothing" in text for text, _ in view["steps"])
    text = start.format_card(card)
    for plumbing in ("launchd", "plist", "LaunchAgents", "crontab", "/Users"):
        assert plumbing not in text


def test_menu_line_names_problems_in_plain_words_or_says_all_in_order():
    card = {"install": {}, "instructions": {"found": True, "broken": 0}, "memory": {"found": True, "rotten": 1},
            "routines": {"found": True, "known": True, "failed": 14}}
    assert start.menu_line(card) == ("1 note out of date · 14 jobs failing", 2)
    card["memory"]["rotten"] = 0
    card["routines"]["failed"] = 0
    assert start.menu_line(card) == ("All in order", 0)
    card["install"] = {"behind_main": 38}
    assert start.menu_line(card)[0] == "Helicon is out of date"
