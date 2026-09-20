"""Review is the stranger front door — grade, exit code, and --json must stay stable."""
from __future__ import annotations

import json
import os
import tempfile

from helicon.review import format_review, main, review, review_summary


def _repo(files: dict[str, str]) -> str:
    d = tempfile.mkdtemp()
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def test_clean_repo_grades_a_and_exits_zero():
    d = _repo({
        "docs/SETUP.md": "# setup\n",
        "CLAUDE.md": "Read `docs/SETUP.md`.\n",
    })
    res = review(d)
    assert main([d]) == 0
    out = format_review(d, res)
    assert "GRADE A" in out
    assert "No contradictions found in the checks run" in out
    assert "Every path and command" not in out


def test_broken_pointer_grades_low_and_exits_one():
    d = _repo({
        "CLAUDE.md": "Always read `docs/MISSING.md` first.\n",
    })
    res = review(d)
    assert main([d]) == 1
    out = format_review(d, res)
    assert "GRADE" in out
    assert "MISSING" in out
    assert "re-run" in out


def test_no_instruction_file_exits_two():
    d = _repo({"README.md": "# hi\n"})
    assert main([d]) == 2
    out = format_review(d, review(d))
    assert "No agent instruction file" in out
    assert "Add AGENTS.md" in out


def test_json_shape_for_ci():
    d = _repo({
        "CLAUDE.md": "See `gone/missing.py`.\n",
    })
    res = review(d)
    summary = review_summary(d, res)
    assert summary["broken"] >= 1
    assert summary["clean"] is False
    assert summary["findings"]
    assert summary["findings"][0]["tier"] == "pointer"
    payload = json.loads(json.dumps(summary))
    assert payload["grade"] in ("C", "D", "F")


def test_unverified_external_path_is_visible_but_not_graded(monkeypatch, tmp_path):
    d = _repo({
        "docs/SETUP.md": "# setup\n",
        "AGENTS.md": "Read `docs/SETUP.md`. State is in `~/.agent-state/run.json`.\n",
    })
    monkeypatch.setenv("HOME", str(tmp_path))
    res = review(d)
    summary = review_summary(d, res)
    out = format_review(d, res)
    assert summary["grade"] == "A"
    assert summary["broken"] == 0
    assert len(summary["unverified_paths"]) == 1
    assert "external or generated path not graded" in out
    assert "tells its agent the truth" not in out


def test_instruction_file_with_only_external_paths_is_unmeasured_not_missing(monkeypatch, tmp_path):
    d = _repo({"AGENTS.md": "State is in `~/.agent-state/run.json`.\n"})
    monkeypatch.setenv("HOME", str(tmp_path))
    res = review(d)
    out = format_review(d, res)
    assert main([d]) == 2
    assert "No gradeable repo-local claim" in out
    assert "No agent instruction file" not in out
    assert "external or generated path not graded" in out
