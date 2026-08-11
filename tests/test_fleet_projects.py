"""The fleet screen, project-first and fully derived.

What this pins is not the layout. It is the two claims the screen makes that a
person would act on and could not check by eye: that the idle number counts
TERMINALS, and that no field on the screen was typed by a human.
"""
import json
import os
import subprocess
import time

import pytest

from helicon import fleet
from helicon.db import init_db


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _session(dirpath, name, *, human, cwd, age_min):
    """A transcript shaped like the real thing, aged by mtime."""
    path = dirpath / f"{name}.jsonl"
    dirpath.mkdir(parents=True, exist_ok=True)
    entries = [{"type": "user", "cwd": cwd, "message": {"content": "hi"},
                "promptSource": "typed" if human else "sdk"}]
    path.write_text("\n".join(json.dumps(e) for e in entries))
    old = time.time() - age_min * 60
    os.utime(path, (old, old))
    return path


# --- the idle number, which is the screen's proof ---------------------------

def test_idle_counts_terminals_not_finished_jobs(tmp_path, monkeypatch):
    """THE BUG THIS PINS. The first version counted every transcript and reported
    241 idle hours across 74 "terminals". 68 were ephemeral cvfit-judge-*
    processes that had run to completion and exited. A finished job is not an
    idle terminal, and a proof number inflated fifteenfold is not a proof."""
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    _session(tmp_path / "a", "terminal", human=True, cwd="/x", age_min=120)
    for i in range(10):
        _session(tmp_path / "b", f"judge{i}", human=False,
                 cwd=f"/private/var/folders/cvfit-judge-{i}", age_min=120)

    idle = fleet.idle_terminals()

    assert idle["count"] == 1, "headless judge runs are not idle terminals"
    assert idle["terminal_hours"] == pytest.approx(2.0, abs=0.2)


def test_a_busy_terminal_is_not_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    _session(tmp_path / "a", "busy", human=True, cwd="/x", age_min=1)

    assert fleet.idle_terminals()["count"] == 0


def test_a_long_dead_session_is_history_not_an_idle_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    _session(tmp_path / "a", "yesterday", human=True, cwd="/x",
             age_min=(fleet.STALE_AFTER_H + 2) * 60)

    assert fleet.idle_terminals()["count"] == 0


def test_the_idle_number_says_it_is_a_floor(tmp_path, monkeypatch):
    """A session thinking hard writes nothing and reads as idle. Publishing the
    number without that caveat would overclaim, and this screen's whole argument
    is that an unmeasured waste is one nobody argues with."""
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    _session(tmp_path / "a", "t", human=True, cwd="/x", age_min=120)

    assert "silent for" in fleet.idle_terminals()["basis"]


# --- projects, derived ------------------------------------------------------

def _repo(tmp_path, name):
    repo = tmp_path / name
    repo.mkdir(parents=True)
    for args in (["init", "-q"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "the real subject"],
                   check=True, capture_output=True)
    return repo


def test_a_project_is_found_by_its_commits_not_only_by_a_terminals_cwd(
        tmp_path, monkeypatch, conn):
    """Oscar drives repos from $HOME, so keying on cwd alone printed "no project
    had a live session" on a day with four commits in the repo being read."""
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path / "sessions"))
    (tmp_path / "sessions").mkdir()
    repo = _repo(tmp_path / "code", "proj")

    rows = fleet.projects(conn, roots=(str(tmp_path / "code"),))

    assert [r["name"] for r in rows] == ["proj"]
    assert rows[0]["git"]["subject"] == "the real subject"
    assert rows[0]["sessions"] == 0, "no terminal was in it; that is a fact, not a blank"


def test_git_state_is_read_from_git(tmp_path):
    repo = _repo(tmp_path, "proj")
    (repo / "dirty.txt").write_text("y")

    state = fleet.git_state(str(repo))

    assert state["dirty"] == 1
    assert state["commits_24h"] == 1
    assert state["subject"] == "the real subject"


def test_no_matching_accepted_prompt_says_unmeasured(tmp_path, monkeypatch, conn):
    """THE BUG THIS PINS. The first version took the newest accepted prompt
    globally and printed it under every project, so four unrelated projects were
    all told to reuse "wire the doorway gate into a live Claude Code session".
    That is a hand-typed field wearing a derived field's clothes."""
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path / "sessions"))
    (tmp_path / "sessions").mkdir()
    _repo(tmp_path / "code", "proj")
    conn.execute(
        "INSERT INTO prompt_library (id, task_run_id, prompt, objective, task_class, "
        "model, harness, outcome, promoted_at, promoted_by) VALUES "
        "('p1','tr1','do the thing','something entirely unrelated to this repo',"
        "'x','m','h','accepted','2026-08-01','test')")
    conn.commit()

    rows = fleet.projects(conn, roots=(str(tmp_path / "code"),))

    assert rows[0]["next_prompt"] is None
    assert "unmeasured" in fleet.format_projects(rows, fleet.idle_terminals(), [], [], [], {})


# --- the capability section -------------------------------------------------

def test_the_screen_tells_an_agent_what_it_can_do(conn):
    """Eight terminals idled for two hours because no instance remembered that
    ListAgents addresses them. A capability nobody recalls is not a capability,
    so the screen states it rather than assuming it is known."""
    caps = fleet.capabilities(conn)

    assert any("ListAgents" in c and "SendMessage" in c for c in caps)


def test_open_work_cards_are_named_in_the_capabilities(conn):
    conn.execute(
        "INSERT INTO work_wagers (id, intent, beneficiary, observable_change, "
        "evidence_contract, kill_condition, opened_at, status) VALUES "
        "('wg1','i','b','o','e','k','2026-08-01','open')")
    conn.commit()

    assert any("Work Card" in c for c in fleet.capabilities(conn))
