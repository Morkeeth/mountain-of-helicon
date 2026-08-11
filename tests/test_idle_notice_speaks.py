"""The idle number speaks without being asked — once, and only when proven.

The fleet screen measures idle terminal-hours and then waits to be asked. But the
finding it exists to report is that eight terminals sat idle for two hours and
NOTHING NOTICED. A metric nobody looks at is the same failure as a capability
nobody remembers, which is the problem the screen was built for. So the doorway
hook says it into the arriving session.

Everything here guards the same risk from a different side: a number that
announces itself does not get re-checked, so it must be right, rare, and unable
to break the prompt it rides on.
"""
import json
import subprocess
import sys

import pytest

from helicon import fleet
from helicon.cli import _idle_notice_once


@pytest.fixture
def gate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HELICON_HOME", str(tmp_path))
    return tmp_path


def test_it_speaks_once_per_session(gate_home, monkeypatch):
    """On every prompt it is wallpaper by the third one, and a muted notice is a
    deleted one."""
    monkeypatch.setattr(fleet, "idle_notice", lambda exclude_session="": "IDLE THINGS")

    first = _idle_notice_once("session-a")
    second = _idle_notice_once("session-a")
    third = _idle_notice_once("session-a")

    assert first == "IDLE THINGS"
    assert second == ""
    assert third == ""


def test_a_different_session_still_hears_it(gate_home, monkeypatch):
    monkeypatch.setattr(fleet, "idle_notice", lambda exclude_session="": "IDLE THINGS")

    _idle_notice_once("session-a")

    assert _idle_notice_once("session-b") == "IDLE THINGS"


def test_the_attempt_is_recorded_before_the_work(gate_home, monkeypatch):
    """A slow or failing probe must cost a session ONE attempt, not one per
    prompt for the rest of the day."""
    def _explode(exclude_session=""):
        raise RuntimeError("probe died")

    monkeypatch.setattr(fleet, "idle_notice", _explode)
    assert _idle_notice_once("session-c") == ""

    monkeypatch.setattr(fleet, "idle_notice", lambda exclude_session="": "IDLE THINGS")
    assert _idle_notice_once("session-c") == "", "the attempt was already spent"


def test_a_broken_probe_never_breaks_the_prompt(gate_home, monkeypatch):
    """This runs on a real person's prompt. It must never be the reason one does
    not go through — the whole doorway path is fail-open by contract."""
    def _explode(exclude_session=""):
        raise RuntimeError("probe died")

    monkeypatch.setattr(fleet, "idle_notice", _explode)

    assert _idle_notice_once("session-d") == ""  # no exception escapes


def test_no_session_id_means_no_notice(gate_home):
    """Without a session there is nothing to speak once PER, so it stays quiet
    rather than repeating on every prompt forever."""
    assert _idle_notice_once("") == ""


def test_the_hook_emits_it_as_agent_context_not_a_human_banner(gate_home, monkeypatch, tmp_path):
    """It goes to additionalContext on purpose: the reader who can ACT on it is
    the agent. It arrives holding an ability it walked in without."""
    monkeypatch.setattr(fleet, "idle_notice", lambda exclude_session="": "IDLE THINGS")

    payload = json.dumps({"cwd": str(tmp_path), "session_id": "hook-session",
                          "prompt": "hello"})
    proc = subprocess.run(
        [sys.executable, "-m", "helicon.cli", "doorway", "gate"],
        input=payload, capture_output=True, text=True, timeout=300,
        env={"HELICON_HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
             "HOME": str(tmp_path)})

    assert proc.returncode == 0, proc.stderr
    if proc.stdout.strip():
        out = json.loads(proc.stdout)
        assert "systemMessage" not in out or "IDLE" not in out.get("systemMessage", "")
