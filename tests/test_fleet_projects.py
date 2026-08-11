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
    _session(tmp_path / "a", "sess-alive", human=True, cwd="/x", age_min=120)
    for i in range(10):
        _session(tmp_path / "b", f"judge{i}", human=False,
                 cwd=f"/private/var/folders/cvfit-judge-{i}", age_min=120)
    # Pin liveness rather than consult the real process table. The first version
    # named this session "terminal" and asserted it was counted — which passed on
    # macOS because `ps` output contains "Terminal", and failed on Linux CI where
    # it does not. The test was reading the developer's desktop, not the code.
    monkeypatch.setattr(fleet, "alive_session_ids", lambda: {"sess-alive"})

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
    monkeypatch.setattr(fleet, "alive_session_ids", lambda: {"t"})

    basis = fleet.idle_terminals()["basis"]
    assert "a human typed there" in basis
    assert "process is still running" in basis
    assert "silent" in basis


# --- liveness: a closed terminal is not an idle one -------------------------

def test_a_quiet_session_with_no_process_is_not_counted(tmp_path, monkeypatch):
    """THE SECOND INFLATION. The human-typed gate removed dead judge processes.
    It did NOT remove terminals that were simply CLOSED — their transcripts sit
    at the same mtime forever and look identical to a terminal someone is
    ignoring. Counting a closed terminal as idle time is the same lie as counting
    a finished job, one step subtler, and it matters more now that the number
    announces itself: nobody re-checks something that speaks first."""
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    _session(tmp_path / "a", "ghost", human=True, cwd="/x", age_min=120)
    monkeypatch.setattr(fleet, "alive_session_ids", lambda: set())

    idle = fleet.idle_terminals()

    assert idle["count"] == 0
    assert idle["terminal_hours"] == 0
    assert idle["unprovable"] == 1, "not counted, but not hidden either"


def test_a_quiet_session_with_a_live_process_is_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    _session(tmp_path / "a", "live", human=True, cwd="/x", age_min=120)
    monkeypatch.setattr(fleet, "alive_session_ids", lambda: {"live"})

    idle = fleet.idle_terminals()

    assert idle["count"] == 1
    assert idle["unprovable"] == 0
    assert "process is still running" in idle["basis"]


# --- the notice: it speaks, but only when it should -------------------------

def _idle(tmp_path, monkeypatch, n, age_min):
    monkeypatch.setattr(fleet, "PROJECTS_DIR", str(tmp_path))
    names = [f"s{i}" for i in range(n)]
    for name in names:
        _session(tmp_path / "a", name, human=True, cwd="/Users/x/CODE/proj", age_min=age_min)
    monkeypatch.setattr(fleet, "alive_session_ids", lambda: set(names))


def test_the_notice_speaks_when_it_matters(tmp_path, monkeypatch):
    _idle(tmp_path, monkeypatch, n=3, age_min=60)

    notice = fleet.idle_notice()

    assert "3 other terminal(s)" in notice
    assert "ListAgents" in notice, "it must hand over the CAPABILITY, not only the number"


def test_one_idle_terminal_is_not_worth_interrupting_for(tmp_path, monkeypatch):
    """This fires on a real person's prompt, uninvited. A notice that arrives
    when it does not matter is a notice that gets muted, after which it may as
    well not exist."""
    _idle(tmp_path, monkeypatch, n=1, age_min=300)
    assert fleet.idle_notice() == ""


def test_quiet_shorter_than_the_per_session_floor_counts_for_nothing(tmp_path, monkeypatch):
    """Two floors, and they mean different things. Each session must be silent
    IDLE_AFTER_MIN before it counts at all — below that it is someone thinking,
    not someone idle. The hours floor is then about AGGREGATE waste, so three
    terminals quiet for 21 minutes each is a real idle hour and does fire; that
    is the metric working, not a leak."""
    _idle(tmp_path, monkeypatch, n=5, age_min=fleet.IDLE_AFTER_MIN - 5)
    assert fleet.idle_notice() == ""

    _idle(tmp_path, monkeypatch, n=3, age_min=21)
    assert fleet.idle_notice() != "", "3 x 21m is an hour of real idle terminal time"


def test_the_notice_excludes_the_session_it_is_speaking_to(tmp_path, monkeypatch):
    """The terminal receiving this is, by definition, the one that is not idle."""
    _idle(tmp_path, monkeypatch, n=2, age_min=60)
    assert fleet.idle_notice() != ""
    assert fleet.idle_notice(exclude_session="s0") == "", "2 - 1 is below the floor"


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


# --- steps: derived from repo state, never typed ----------------------------

def _entry(**over):
    e = {"name": "p", "unreviewed": 0, "complaints": [], "sessions": 0,
         "git": {"branch": "main", "dirty": 0, "unpushed": 0, "commits_24h": 3}}
    e["git"].update(over.pop("git", {}))
    e.update(over)
    return e


def test_a_clean_project_gets_no_invented_step():
    """Empty is a legal answer. A screen that always has advice is a screen that
    makes advice up, and then the next-step field is stale within a week."""
    assert fleet.next_steps(_entry()) == []


def test_work_on_a_non_default_branch_is_named():
    """His own settled lesson: 109 commits on a branch, 2 on main, fifteen
    minutes from a submission deadline. The repo knows this and never said it."""
    steps = fleet.next_steps(_entry(git={"branch": "build/thing"}))
    assert any("not the default branch" in s for s in steps)


def test_unpushed_commits_are_named():
    assert any("never pushed" in s for s in fleet.next_steps(_entry(git={"unpushed": 4})))


def test_a_big_dirty_tree_is_named():
    assert any("uncommitted" in s for s in fleet.next_steps(_entry(git={"dirty": 23})))


def test_a_small_dirty_tree_is_not_nagged_about():
    assert not any("uncommitted" in s for s in fleet.next_steps(_entry(git={"dirty": 1})))


def test_unreviewed_runs_become_a_step():
    assert any("no verdict" in s for s in fleet.next_steps(_entry(unreviewed=3)))


def test_pushbacks_become_a_step_naming_the_kind():
    steps = fleet.next_steps(_entry(complaints=[("wrong-plan", 4)]))
    assert any("wrong-plan" in s and "4" in s for s in steps)


def test_an_open_terminal_with_nothing_landed_is_named():
    steps = fleet.next_steps(_entry(sessions=2, git={"commits_24h": 0}))
    assert any("stuck or the work is unscoped" in s for s in steps)


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
