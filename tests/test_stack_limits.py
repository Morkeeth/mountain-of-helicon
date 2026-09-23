"""`helicon stack` must go red on the setup that broke on 22 Sep 2026.

That night the SessionStart hook printed 98,921 characters. Claude Code keeps
10,000 and shows the model a 2,000 character preview, so the open tasks and the
rulings never reached the session. The old command printed "Stack completeness:
100%" on that machine. These tests build a throwaway home with the same shape of
output and require exit 1, plus a control home that must stay green.
"""
import json
import os
import subprocess
import sys

import pytest

from helicon.stacklimits import audit_stack

OLD_HOOK_CHARS = 98_921  # wc -c of state-read.sh stdout, 22 Sep 2026


def _hook_output(n):
    """Synthetic state-shaped text of exactly n characters (no real state is copied)."""
    block = ("## CLOSED\n- T001 closed row\n## OPEN\n- T100 open row that never reached "
             "the model\n## RULINGS AND FACTS\n- R1 a ruling past the preview\n")
    return (block * (n // len(block) + 1))[:n]


def _home(tmp_path, hook_chars=500, claude_md="# me\n", skills=3, model_invocable=True,
          memory_text="- [Paper Lantern](project_paper_lantern.md)\n", registry=True):
    home = tmp_path / "home"
    cd = home / ".claude"
    cd.mkdir(parents=True)
    out = tmp_path / "hook-output.txt"
    out.write_text(_hook_output(hook_chars), encoding="utf-8")
    cd.joinpath("settings.json").write_text(json.dumps({"hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": f"cat '{out}'"}]}],
        "PostCompact": [{"hooks": [{"type": "command", "command": "echo compacted"}]}],
    }}))
    cd.joinpath("CLAUDE.md").write_text(claude_md, encoding="utf-8")
    for i in range(skills):
        s = cd / "skills" / f"skill-{i:02d}"
        s.mkdir(parents=True)
        extra = "" if model_invocable else "disable-model-invocation: true\n"
        s.joinpath("SKILL.md").write_text(f"---\nname: skill-{i:02d}\ndescription: d\n{extra}---\nbody\n")
    mem = cd / "projects" / "-home" / "memory"
    mem.mkdir(parents=True)
    mem.joinpath("MEMORY.md").write_text("# MEMORY\n" + memory_text, encoding="utf-8")
    reg = None
    if registry:
        reg = tmp_path / "registry.md"
        reg.write_text("## PROJECTS, one line each (2)\n\n"
                       "- Paper Lantern: Lights old notes · Morkeeth/paper-lantern · none · live\n"
                       "- Old Kite: Retired thing · Morkeeth/old-kite · none · parked\n",
                       encoding="utf-8")
    return str(home), (str(reg) if reg else None), str(mem)


def _by(res, cid, event=None):
    return [c for c in res["checks"] if c["id"] == cid and (event is None or event in c["name"])]


def test_the_old_99kb_hook_output_is_red(tmp_path):
    home, reg, mem = _home(tmp_path, hook_chars=OLD_HOOK_CHARS)
    res = audit_stack(home, reg, mem)
    s1 = _by(res, "S1", "SessionStart")[0]
    assert s1["status"] == "FAIL" and s1["value"] == OLD_HOOK_CHARS
    assert "2,000 character preview" in s1["detail"]
    assert not res["ok"]


def test_a_setup_inside_every_limit_is_green(tmp_path):
    # The control: without it, a check that is always red would pass the test above.
    home, reg, mem = _home(tmp_path, hook_chars=7_000)
    res = audit_stack(home, reg, mem)
    assert res["ok"], [c for c in res["checks"] if c["status"] != "PASS"]
    assert res["skipped"] == 0


def test_hook_output_just_over_the_margin_is_red(tmp_path):
    home, reg, mem = _home(tmp_path, hook_chars=8_001)
    assert _by(audit_stack(home, reg, mem), "S1", "SessionStart")[0]["status"] == "FAIL"


def test_a_large_claude_md_is_red(tmp_path):
    home, reg, mem = _home(tmp_path, claude_md="x" * 4_001)
    assert _by(audit_stack(home, reg, mem), "S2")[0]["status"] == "FAIL"
    home2, reg2, mem2 = _home(tmp_path / "b", claude_md="line\n" * 61)
    assert _by(audit_stack(home2, reg2, mem2), "S2")[0]["status"] == "FAIL"


def test_too_many_model_invocable_skills_is_red(tmp_path):
    home, reg, mem = _home(tmp_path, skills=16)
    assert _by(audit_stack(home, reg, mem), "S3")[0]["status"] == "FAIL"
    home2, reg2, mem2 = _home(tmp_path / "b", skills=16, model_invocable=False)
    assert _by(audit_stack(home2, reg2, mem2), "S3")[0]["status"] == "PASS"


def test_a_live_project_missing_from_the_memory_index_is_red(tmp_path):
    home, reg, mem = _home(tmp_path, memory_text="- nothing about projects\n")
    s4 = _by(audit_stack(home, reg, mem), "S4")[0]
    assert s4["status"] == "FAIL" and "Paper Lantern" in s4["detail"]
    assert "Old Kite" not in s4["detail"]  # parked, not live


def test_a_project_named_only_in_the_archive_index_is_missing(tmp_path):
    home, reg, mem = _home(tmp_path, memory_text="- nothing\n")
    idx = os.path.join(mem, "index")
    os.makedirs(idx)
    open(os.path.join(idx, "ARCHIVE-MEMORY.md"), "w").write("paper-lantern\n")
    assert _by(audit_stack(home, reg, mem), "S4")[0]["status"] == "FAIL"
    open(os.path.join(idx, "project.md"), "w").write("- [paper lantern](p.md)\n")
    assert _by(audit_stack(home, reg, mem), "S4")[0]["status"] == "PASS"


def test_no_registry_is_a_skip_never_a_pass(tmp_path):
    home, reg, mem = _home(tmp_path, registry=False)
    s4 = _by(audit_stack(home, None, mem), "S4")[0]
    assert s4["status"] == "SKIP"


def test_the_command_exits_1_and_never_prints_completeness(tmp_path):
    home, reg, mem = _home(tmp_path, hook_chars=OLD_HOOK_CHARS)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""))
    r = subprocess.run([sys.executable, "-m", "helicon.cli", "stack", "--home", home,
                        "--registry", reg, "--memory-dir", mem],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL  S1" in r.stdout
    assert "Stack completeness" not in r.stdout


def test_a_home_with_no_claude_setup_is_unmeasured_not_green(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=root + os.pathsep + os.environ.get("PYTHONPATH", ""))
    r = subprocess.run([sys.executable, "-m", "helicon.cli", "stack", "--home", str(tmp_path)],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "UNMEASURED" in r.stdout
