"""Witnessed staleness: instruction-file paths an agent FOLLOWED and failed on.

`helicon review` grades a pointer against the tree it can see. A path outside the
repo (`~/.local/state/...`, a vault page) is reported as "not graded", and a path
that resolves today says nothing about whether an agent could open it last week.
The transcript holds the missing half: a tool error of the shape "No such file or
directory" on that exact path is an agent following the instruction and failing.

Fixtures here are synthetic. No real transcript, no personal path.
"""
import json
import os

import pytest

from helicon.followed import (check_followed, extract_failed_paths, format_followed,
                              instruction_paths)


def _write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _tool(tid, name, inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def _result(tid, text, error=True):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "is_error": error, "content": text}]}}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "SETUP.md").write_text("# setup\n")
    (root / "AGENTS.md").write_text(
        "Read `docs/SETUP.md` first.\n"
        "The live board is `~/.local/state/board/CURRENT.md`.\n"
        "Older notes live in `Archive/old notes/log.md`.\n"
        "Never read `legacy/dead.md`, it is gone.\n"
    )
    return root


def test_extract_failed_paths_reads_every_error_shape(tmp_path):
    t = tmp_path / "s.jsonl"
    _write_jsonl(t, [
        _tool("a", "Bash", {"command": "cat /home/u/.local/state/board/CURRENT.md"}),
        _result("a", "cat: /home/u/.local/state/board/CURRENT.md: No such file or directory"),
        _tool("b", "Read", {"file_path": "/home/u/vault/Archive/old notes/log.md"}),
        _result("b", "File does not exist. Note: your current working directory is /home/u"),
        _tool("c", "Bash", {"command": "python3 x.py"}),
        _result("c", "FileNotFoundError: [Errno 2] No such file or directory: '/home/u/x.py'"),
        _tool("d", "Bash", {"command": "node y.js"}),
        _result("d", "Error: ENOENT: no such file or directory, open '/home/u/y.js'"),
        _tool("e", "Bash", {"command": "timeout 5 ls"}),
        _result("e", "(eval):1: command not found: timeout"),
        _tool("f", "Bash", {"command": "ls /home/u/ok.md"}),
        _result("f", "/home/u/ok.md", error=False),
    ])
    found = extract_failed_paths(str(t))
    paths = sorted(p["path"] for p in found)
    assert paths == [
        "/home/u/.local/state/board/CURRENT.md",
        "/home/u/vault/Archive/old notes/log.md",
        "/home/u/x.py",
        "/home/u/y.js",
    ]
    # a missing COMMAND is not a missing path, and a success is not a failure
    assert all("timeout" not in p["path"] for p in found)


def test_instruction_paths_keep_external_and_spaced_tokens(repo):
    rows = instruction_paths(str(repo))
    raws = {r["target"] for r in rows}
    assert "docs/SETUP.md" in raws                       # resolves, still a candidate
    assert "~/.local/state/board/CURRENT.md" in raws     # external, review leaves ungraded
    assert "Archive/old notes/log.md" in raws            # a space does not hide a path


def test_followed_and_failed_joins_pointer_to_transcript_error(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/u")
    t1 = tmp_path / "one.jsonl"
    _write_jsonl(t1, [
        _tool("a", "Bash", {"command": "cat ~/.local/state/board/CURRENT.md"}),
        _result("a", "cat: /home/u/.local/state/board/CURRENT.md: No such file or directory"),
        _tool("b", "Read", {"file_path": "/home/u/vault/Archive/old notes/log.md"}),
        _result("b", "File does not exist."),
        _tool("c", "Bash", {"command": "cat /home/u/unrelated/thing.md"}),
        _result("c", "cat: /home/u/unrelated/thing.md: No such file or directory"),
    ])
    t2 = tmp_path / "two.jsonl"
    _write_jsonl(t2, [
        _tool("a", "Bash", {"command": "cat ~/.local/state/board/CURRENT.md"}),
        _result("a", "cat: /home/u/.local/state/board/CURRENT.md: No such file or directory"),
    ])
    res = check_followed(str(repo), transcripts=[str(t1), str(t2)])
    assert res["verdict"] == "ROT FOUND"
    assert res["sessions"] == 2
    by_target = {r["target"]: r for r in res["witnessed"]}
    cur = by_target["~/.local/state/board/CURRENT.md"]
    assert cur["file"] == "AGENTS.md" and cur["line_no"] == 2
    assert cur["failures"] == 2 and cur["session_count"] == 2
    assert cur["match"] == "by path"
    log = by_target["Archive/old notes/log.md"]
    assert log["failures"] == 1 and log["match"] == "by path"
    # the path that resolves today was never followed-and-failed, so it is not a finding
    assert "docs/SETUP.md" not in by_target
    # the described absence is not an instruction to follow, so it is not a finding
    assert "legacy/dead.md" not in by_target
    # an error on a path no instruction names is counted, not joined
    assert res["unmatched_failures"] == 1
    out = format_followed(res)
    assert "AGENTS.md:2" in out and "2 failures in 2 sessions" in out


def test_clean_when_errors_match_no_instruction_path(repo, tmp_path):
    t = tmp_path / "s.jsonl"
    _write_jsonl(t, [
        _tool("a", "Bash", {"command": "cat /nowhere/x.md"}),
        _result("a", "cat: /nowhere/x.md: No such file or directory"),
    ])
    res = check_followed(str(repo), transcripts=[str(t)])
    assert res["verdict"] == "CLEAN"
    assert res["witnessed"] == []
    assert res["unmatched_failures"] == 1


def test_no_transcript_is_unmeasured_not_clean(repo):
    res = check_followed(str(repo), transcripts=[])
    assert res["verdict"] == "UNMEASURED"
    assert "no transcript" in format_followed(res).lower()


def test_basename_join_is_labelled_weaker_than_a_path_join(repo, tmp_path):
    t = tmp_path / "s.jsonl"
    _write_jsonl(t, [
        _tool("a", "Read", {"file_path": "/elsewhere/vault/CURRENT.md"}),
        _result("a", "File does not exist."),
    ])
    res = check_followed(str(repo), transcripts=[str(t)])
    by_target = {r["target"]: r for r in res["witnessed"]}
    assert by_target["~/.local/state/board/CURRENT.md"]["match"] == "by name"


def test_cli_wires_followed(tmp_path, repo, capsys):
    from helicon.cli import cmd_followed
    import argparse
    t = tmp_path / "s.jsonl"
    _write_jsonl(t, [
        _tool("a", "Bash", {"command": "cat x"}),
        _result("a", "cat: /home/u/.local/state/board/CURRENT.md: No such file or directory"),
    ])
    args = argparse.Namespace(repo=str(repo), transcripts=[str(t)], files=None,
                              limit=50, json=True)
    with pytest.raises(SystemExit) as ex:
        cmd_followed(args)
    assert ex.value.code == 1
    rep = json.loads(capsys.readouterr().out)
    assert rep["verdict"] == "ROT FOUND"
    assert rep["witnessed"][0]["target"] == "~/.local/state/board/CURRENT.md"


def test_conventional_basename_never_joins_by_name(tmp_path):
    """Every repo has a CLAUDE.md. A missing one somewhere else is not evidence
    about the one this instruction names. Measured on the real corpus before this
    guard: 15 of the top join was `~/.claude/CLAUDE.md` matched by name to other
    repos' missing CLAUDE.md files."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text(
        "Global rules are in `~/.claude/CLAUDE.md`; settings in `~/.claude/board/config.json`.\n"
        "Daily notes: `~/vault/00 Dashboard/record.md`.\n"
    )
    t = tmp_path / "s.jsonl"
    _write_jsonl(t, [
        _tool("a", "Read", {"file_path": "/other/repo/CLAUDE.md"}),
        _result("a", "File does not exist."),
        _tool("b", "Read", {"file_path": "/other/app/config.json"}),
        _result("b", "File does not exist."),
        _tool("c", "Read", {"file_path": "/elsewhere/record.md"}),
        _result("c", "File does not exist."),
    ])
    res = check_followed(str(root), transcripts=[str(t)])
    targets = {r["target"]: r["match"] for r in res["witnessed"]}
    assert "~/.claude/CLAUDE.md" not in targets
    assert "~/.claude/board/config.json" not in targets
    assert targets == {"~/vault/00 Dashboard/record.md": "by name"}
    assert res["unmatched_failures"] == 2


def test_bare_basename_pointer_joins_by_name_at_most(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text("Copy `.env` first, then append to `state-log.md`.\n")
    t = tmp_path / "s.jsonl"
    _write_jsonl(t, [
        _tool("a", "Bash", {"command": "cat .env"}),
        _result("a", "cat: .env: No such file or directory"),
        _tool("b", "Bash", {"command": "cat state-log.md"}),
        _result("b", "cat: /vault/00 Dashboard/state-log.md: No such file or directory"),
    ])
    res = check_followed(str(root), transcripts=[str(t)])
    targets = {r["target"]: r["match"] for r in res["witnessed"]}
    assert targets == {"state-log.md": "by name"}
